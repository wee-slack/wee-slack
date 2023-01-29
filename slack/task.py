from __future__ import annotations

import traceback
from typing import (
    TYPE_CHECKING,
    Any,
    Awaitable,
    Coroutine,
    Dict,
    Generator,
    List,
    Optional,
    Sequence,
    Tuple,
    TypeVar,
    Union,
    overload,
)
from uuid import uuid4

import weechat

from slack.error import HttpError, SlackApiError, SlackError, format_exception
from slack.log import print_error
from slack.shared import shared
from slack.util import get_callback_name

if TYPE_CHECKING:
    from typing_extensions import Literal

T = TypeVar("T")


class Future(Awaitable[T]):
    def __init__(self, future_id: Optional[str] = None):
        if future_id is None:
            self.id = str(uuid4())
        else:
            self.id = future_id
        self._finished = False
        self._result: Optional[T] = None

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}('{self.id}')"

    def __await__(self) -> Generator[Future[T], T, T]:
        result = yield self
        if isinstance(result, BaseException):
            raise result
        self.set_result(result)
        return result

    @property
    def finished(self):
        return self._finished

    @property
    def result(self):
        return self._result

    def set_result(self, result: T):
        self._result = result
        self._finished = True


class FutureProcess(Future[Tuple[str, int, str, str]]):
    pass


class FutureTimer(Future[Tuple[int]]):
    pass


class Task(Future[T]):
    def __init__(self, coroutine: Coroutine[Future[Any], Any, T]):
        super().__init__()
        self.coroutine = coroutine
        self._cancelled = False

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}('{self.id}', coroutine={self.coroutine.__qualname__})"

    def __await__(self) -> Generator[Future[T], T, T]:
        if self.cancelled():
            raise RuntimeError("cannot await a cancelled task")
        return super().__await__()

    def cancel(self):
        self._cancelled = True
        self.coroutine.close()

    def cancelled(self):
        return self._cancelled


def weechat_task_cb(data: str, *args: object) -> int:
    future = shared.active_futures.pop(data)
    future.set_result(args)
    tasks = shared.active_tasks.pop(data)
    for task in tasks:
        task_runner(task, args)
    return weechat.WEECHAT_RC_OK


def process_ended_task(task: Task[Any], response: object):
    task.set_result(response)
    if task.id in shared.active_tasks:
        tasks = shared.active_tasks.pop(task.id)
        for active_task in tasks:
            task_runner(active_task, response)
    if task.id in shared.active_futures:
        del shared.active_futures[task.id]


def task_runner(task: Task[Any], response: object):
    while True:
        if task.cancelled():
            return
        try:
            future = task.coroutine.send(response)
        except BaseException as e:
            result = e.value if isinstance(e, StopIteration) else e
            in_active_tasks = task.id in shared.active_tasks
            process_ended_task(task, result)

            if isinstance(result, BaseException):
                weechat_task_cb_in_stack = "weechat_task_cb" in [
                    stack.name for stack in traceback.extract_stack()
                ]
                create_task_in_stack = [
                    stack.name for stack in traceback.extract_stack()
                ].count("create_task")
                if not in_active_tasks and (
                    create_task_in_stack == 0
                    or not weechat_task_cb_in_stack
                    and create_task_in_stack == 1
                ):
                    if (
                        isinstance(e, HttpError)
                        or isinstance(e, SlackApiError)
                        or isinstance(e, SlackError)
                    ):
                        exception_str = format_exception(e)
                        print_error(f"{exception_str}, task: {task}")
                    else:
                        raise e

            return

        if future.finished:
            response = future.result
        else:
            shared.active_tasks[future.id].append(task)
            shared.active_futures[future.id] = future
            break


def create_task(coroutine: Coroutine[Future[Any], Any, T]) -> Task[T]:
    task = Task(coroutine)
    task_runner(task, None)
    return task


@overload
async def gather(
    *requests: Union[Future[T], Coroutine[Any, Any, T]],
    return_exceptions: Literal[False] = False,
) -> List[T]:
    ...


@overload
async def gather(
    *requests: Union[Future[T], Coroutine[Any, Any, T]],
    return_exceptions: Literal[True],
) -> List[Union[T, BaseException]]:
    ...


async def gather(
    *requests: Union[Future[T], Coroutine[Any, Any, T]], return_exceptions: bool = False
) -> Sequence[Union[T, BaseException]]:
    # TODO: Should probably propagate first exception

    tasks_map: Dict[int, Future[T]] = {}
    results_map: Dict[int, Union[T, BaseException]] = {}

    for i, request in enumerate(requests):
        if isinstance(request, Coroutine):
            try:
                tasks_map[i] = create_task(request)
            except BaseException as e:
                results_map[i] = e
        else:
            tasks_map[i] = request

    for i, task in tasks_map.items():
        try:
            # print(f"waiting for {task}")
            results_map[i] = await task
        except BaseException as e:
            results_map[i] = e

    results = [results_map[i] for i in sorted(results_map.keys())]

    if not return_exceptions:
        for result in results:
            if isinstance(result, BaseException):
                raise result

    return results


async def sleep(milliseconds: int):
    future = FutureTimer()
    weechat.hook_timer(
        milliseconds, 0, 1, get_callback_name(weechat_task_cb), future.id
    )
    return await future
