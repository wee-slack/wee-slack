from __future__ import annotations

from typing import Any, Awaitable, Coroutine, Dict, Generator, List, Tuple, TypeVar
from uuid import uuid4

import weechat

from slack.shared import shared
from slack.util import get_callback_name

T = TypeVar("T")


class Future(Awaitable[T]):
    def __init__(self):
        self.id = str(uuid4())

    def __await__(self) -> Generator[Future[T], T, T]:
        return (yield self)


class FutureProcess(Future[Tuple[str, int, str, str]]):
    pass


class FutureTimer(Future[Tuple[int]]):
    pass


class Task(Future[T]):
    def __init__(self, coroutine: Coroutine[Future[Any], Any, T], final: bool):
        super().__init__()
        self.coroutine = coroutine
        self.final = final


def weechat_task_cb(data: str, *args: Any) -> int:
    task = shared.active_tasks.pop(data)
    task_runner(task, args)
    return weechat.WEECHAT_RC_OK


def task_runner(task: Task[Any], response: Any):
    while True:
        try:
            future = task.coroutine.send(response)
            if future.id in shared.active_responses:
                response = shared.active_responses.pop(future.id)
            else:
                if future.id in shared.active_tasks:
                    raise Exception(
                        f"future.id in active_tasks, {future.id}, {shared.active_tasks}"
                    )
                shared.active_tasks[future.id] = task
                break
        except StopIteration as e:
            if task.id in shared.active_tasks:
                task = shared.active_tasks.pop(task.id)
                response = e.value
            else:
                if task.id in shared.active_responses:
                    raise Exception(  # pylint: disable=raise-missing-from
                        f"task.id in active_responses, {task.id}, {shared.active_responses}"
                    )
                if not task.final:
                    shared.active_responses[task.id] = e.value
                break


def create_task(
    coroutine: Coroutine[Future[Any], Any, T], final: bool = False
) -> Task[T]:
    task = Task(coroutine, final)
    task_runner(task, None)
    return task


async def await_all_concurrent(requests: List[Coroutine[Any, Any, T]]) -> List[T]:
    tasks = [create_task(request) for request in requests]
    return [await task for task in tasks]


async def await_all_concurrent_dict(
    requests: Dict[str, Coroutine[Any, Any, T]]
) -> Dict[str, T]:
    tasks = {key: create_task(request) for key, request in requests.items()}
    return {key: await task for key, task in tasks.items()}


async def sleep(milliseconds: int):
    future = FutureTimer()
    weechat.hook_timer(
        milliseconds, 0, 1, get_callback_name(weechat_task_cb), future.id
    )
    return await future
