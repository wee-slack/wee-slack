from __future__ import annotations

from typing import (
    Any,
    Awaitable,
    Coroutine,
    Dict,
    Generator,
    List,
    Literal,
    Optional,
    Sequence,
    Tuple,
    TypeVar,
    Union,
    overload,
)
from uuid import uuid4

import weechat

from slack.error import HttpError, SlackApiError
from slack.log import print_error
from slack.shared import shared
from slack.util import get_callback_name

T = TypeVar("T")


class Future(Awaitable[T]):
    def __init__(self, future_id: Optional[str] = None):
        if future_id is None:
            self.id = str(uuid4())
        else:
            self.id = future_id
        self._finished = False
        self._result: Optional[T] = None

    def __await__(self) -> Generator[Future[T], T, T]:
        result = yield self
        if isinstance(result, Exception):
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


def weechat_task_cb(data: str, *args: Any) -> int:
    future = shared.active_futures.pop(data)
    future.set_result(args)
    tasks = shared.active_tasks.pop(data)
    for task in tasks:
        task_runner(task, args)
    return weechat.WEECHAT_RC_OK


def process_ended_task(task: Task[Any], response: Any):
    task.set_result(response)
    if task.id in shared.active_tasks:
        tasks = shared.active_tasks.pop(task.id)
        for active_task in tasks:
            task_runner(active_task, response)
    if task.id in shared.active_futures:
        del shared.active_futures[task.id]


def task_runner(task: Task[Any], response: Any):
    while True:
        try:
            future = task.coroutine.send(response)
        except Exception as e:
            result = e.value if isinstance(e, StopIteration) else e
            process_ended_task(task, result)
            if isinstance(e, HttpError):
                print_error(
                    f"Error calling URL {e.url}: return code: {e.return_code}, "
                    f"http status code: {e.http_status_code}, error: {e.error}"
                )
            elif isinstance(e, SlackApiError):
                print_error(
                    f"Error from Slack API method {e.method} for workspace "
                    f"{e.workspace.name}: {e.response}"
                )
            elif not isinstance(e, StopIteration):
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
