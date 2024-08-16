from __future__ import annotations

from types import TracebackType
from typing import (
    TYPE_CHECKING,
    Any,
    Awaitable,
    Callable,
    Coroutine,
    Dict,
    Generator,
    List,
    Optional,
    Sequence,
    Set,
    Tuple,
    TypeVar,
    Union,
    overload,
)
from uuid import uuid4

import weechat

from slack.error import store_and_format_exception
from slack.log import print_error
from slack.shared import shared
from slack.util import get_callback_name

if TYPE_CHECKING:
    from typing_extensions import Literal, Self

T = TypeVar("T")

running_tasks: Set[Task[object]] = set()
failed_tasks: List[Tuple[Task[object], BaseException]] = []


class CancelledError(Exception):
    pass


class InvalidStateError(Exception):
    pass


# Heavily inspired by https://github.com/python/cpython/blob/3.11/Lib/asyncio/futures.py
class Future(Awaitable[T]):
    def __init__(self, future_id: Optional[str] = None):
        self.id = future_id or str(uuid4())
        self._state: Literal["PENDING", "CANCELLED", "FINISHED"] = "PENDING"
        self._result: T
        self._exception: Optional[BaseException] = None
        self._exception_tb: Optional[TracebackType] = None
        self._cancel_message = None
        self._callbacks: List[Callable[[Self], object]] = []
        self._exception_read = False

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}('{self.id}')"

    def __await__(self) -> Generator[Future[T], None, T]:
        if not self.done():
            yield self  # This tells Task to wait for completion.
        if not self.done():
            raise RuntimeError("await wasn't used with future")
        return self.result()  # May raise too.

    def _make_cancelled_error(self):
        if self._cancel_message is None:
            return CancelledError()
        else:
            return CancelledError(self._cancel_message)

    def __schedule_callbacks(self):
        callbacks = self._callbacks[:]
        if not callbacks:
            return

        self._callbacks[:] = []
        for callback in callbacks:
            callback(self)

    def result(self):
        exc = self.exception()
        if exc is not None:
            raise exc.with_traceback(self._exception_tb)
        return self._result

    def set_result(self, result: T):
        if self.done():
            raise InvalidStateError(f"{self._state}: {self!r}")
        self._result = result
        self._state = "FINISHED"
        self.__schedule_callbacks()

    def set_exception(self, exception: BaseException):
        if self.done():
            raise InvalidStateError(f"{self._state}: {self!r}")
        if isinstance(exception, type):
            exception = exception()
        if type(exception) is StopIteration:
            raise TypeError(
                "StopIteration interacts badly with generators "
                "and cannot be raised into a Future"
            )
        self._exception = exception
        self._exception_tb = exception.__traceback__
        self._state = "FINISHED"
        self.__schedule_callbacks()

    def done(self):
        return self._state != "PENDING"

    def done_with_result(self):
        return self._state == "FINISHED" and self._exception is None

    def cancelled(self):
        return self._state == "CANCELLED"

    def add_done_callback(self, callback: Callable[[Self], object]) -> None:
        if self.done():
            callback(self)
        else:
            self._callbacks.append(callback)

    def remove_done_callback(self, callback: Callable[[Self], object]) -> int:
        filtered_callbacks = [cb for cb in self._callbacks if cb != callback]
        removed_count = len(self._callbacks) - len(filtered_callbacks)
        if removed_count:
            self._callbacks[:] = filtered_callbacks
        return removed_count

    def cancel(self, msg: Optional[str] = None):
        if self._state != "PENDING":
            return False
        self._state = "CANCELLED"
        self._cancel_message = msg
        self.__schedule_callbacks()
        return True

    def exception(self):
        if self.cancelled():
            raise self._make_cancelled_error()
        elif not self.done():
            raise InvalidStateError("Exception is not set.")
        self._exception_read = True
        return self._exception

    def exception_read(self):
        return self._exception_read


class FutureProcess(Future[Tuple[str, int, str, str]]):
    pass


class FutureUrl(Future[Tuple[str, Dict[str, str], Dict[str, str]]]):
    pass


class FutureTimer(Future[Tuple[int]]):
    pass


class Task(Future[T]):
    def __init__(self, coroutine: Coroutine[Future[T], None, T]):
        super().__init__()
        self.coroutine = coroutine

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}('{self.id}', coroutine={self.coroutine.__qualname__})"

    def cancel(self, msg: Optional[str] = None):
        if not super().cancel(msg):
            return False
        self.coroutine.close()
        return True


def weechat_task_cb(data: str, *args: object) -> int:
    future = shared.active_futures.pop(data)
    future.set_result(args)
    tasks = shared.active_tasks.pop(data)
    for task in tasks:
        task_runner(task)
    return weechat.WEECHAT_RC_OK


def process_ended_task(task: Task[Any]):
    if task.id in shared.active_tasks:
        tasks = shared.active_tasks.pop(task.id)
        for active_task in tasks:
            task_runner(active_task)
    if task.id in shared.active_futures:
        del shared.active_futures[task.id]


def task_runner(task: Task[Any]):
    running_tasks.add(task)
    while True:
        if task.cancelled():
            break
        try:
            future = task.coroutine.send(None)
        except BaseException as e:
            if isinstance(e, StopIteration):
                task.set_result(e.value)
            else:
                task.set_exception(e)
                failed_tasks.append((task, e))
            process_ended_task(task)
            break

        if not future.done():
            shared.active_tasks[future.id].append(task)
            shared.active_futures[future.id] = future
            break

    running_tasks.remove(task)
    if not running_tasks and not shared.active_tasks:
        for task, exception in failed_tasks:
            if not task.exception_read():
                print_error(
                    f"{task} was never awaited and failed with: "
                    f"{store_and_format_exception(exception)}"
                )
        failed_tasks.clear()


def create_task(coroutine: Coroutine[Future[Any], None, T]) -> Task[T]:
    task = Task(coroutine)
    task_runner(task)
    return task


def _async_task_done(task: Task[object]):
    exception = task.exception()
    if exception:
        print_error(f"{task} failed with: {store_and_format_exception(exception)}")


def run_async(coroutine: Coroutine[Future[Any], None, Any]) -> None:
    task = Task(coroutine)
    task.add_done_callback(_async_task_done)
    task_runner(task)


@overload
async def gather(
    *requests: Union[Future[T], Coroutine[Any, None, T]],
    return_exceptions: Literal[False] = False,
) -> List[T]: ...


@overload
async def gather(
    *requests: Union[Future[T], Coroutine[Any, None, T]],
    return_exceptions: Literal[True],
) -> List[Union[T, BaseException]]: ...


async def gather(
    *requests: Union[Future[T], Coroutine[Any, None, T]],
    return_exceptions: bool = False,
) -> Sequence[Union[T, BaseException]]:
    tasks = [
        create_task(request) if isinstance(request, Coroutine) else request
        for request in requests
    ]

    results: List[Union[T, BaseException]] = []
    for task in tasks:
        if return_exceptions:
            try:
                results.append(await task)
            except BaseException as e:
                results.append(e)
        else:
            results.append(await task)

    return results


async def sleep(milliseconds: int):
    future = FutureTimer()
    sleep_ms = milliseconds if milliseconds > 0 else 1
    weechat.hook_timer(sleep_ms, 0, 1, get_callback_name(weechat_task_cb), future.id)
    return await future
