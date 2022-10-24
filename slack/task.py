from __future__ import annotations

from typing import Any, Awaitable, Coroutine, Generator, Tuple, TypeVar
from uuid import uuid4

import globals as G
import weechat
from util import get_callback_name

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
    task = G.active_tasks.pop(data)
    task_runner(task, args)
    return weechat.WEECHAT_RC_OK


def task_runner(task: Task[Any], response: Any):
    while True:
        try:
            future = task.coroutine.send(response)
            if future.id in G.active_responses:
                response = G.active_responses.pop(future.id)
            else:
                if future.id in G.active_tasks:
                    raise Exception(
                        f"future.id in active_tasks, {future.id}, {G.active_tasks}"
                    )
                G.active_tasks[future.id] = task
                break
        except StopIteration as e:
            if task.id in G.active_tasks:
                task = G.active_tasks.pop(task.id)
                response = e.value
            else:
                if task.id in G.active_responses:
                    raise Exception(  # pylint: disable=raise-missing-from
                        f"task.id in active_responses, {task.id}, {G.active_responses}"
                    )
                if not task.final:
                    G.active_responses[task.id] = e.value
                break


def create_task(
    coroutine: Coroutine[Future[Any], Any, T], final: bool = False
) -> Task[T]:
    task = Task(coroutine, final)
    task_runner(task, None)
    return task


async def sleep(milliseconds: int):
    future = FutureTimer()
    weechat.hook_timer(
        milliseconds, 0, 1, get_callback_name(weechat_task_cb), future.id
    )
    return await future
