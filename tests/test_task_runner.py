from __future__ import annotations

from collections import defaultdict

from slack.shared import shared
from slack.task import Future, create_task, weechat_task_cb


def test_run_single_task():
    shared.active_tasks = defaultdict(list)
    shared.active_futures = {}
    future = Future[str]()

    async def awaitable():
        result = await future
        return "awaitable", result

    task = create_task(awaitable())
    weechat_task_cb(future.id, "data")

    assert not shared.active_tasks
    assert not shared.active_futures
    assert task.result() == ("awaitable", ("data",))


def test_run_nested_task():
    shared.active_tasks = defaultdict(list)
    shared.active_futures = {}
    future = Future[str]()

    async def awaitable1():
        result = await future
        return "awaitable1", result

    async def awaitable2():
        result = await create_task(awaitable1())
        return "awaitable2", result

    task = create_task(awaitable2())
    weechat_task_cb(future.id, "data")

    assert not shared.active_tasks
    assert not shared.active_futures
    assert task.result() == ("awaitable2", ("awaitable1", ("data",)))


def test_run_two_tasks_concurrently():
    shared.active_tasks = defaultdict(list)
    shared.active_futures = {}
    future1 = Future[str]()
    future2 = Future[str]()

    async def awaitable(future: Future[str]):
        result = await future
        return "awaitable", result

    task1 = create_task(awaitable(future1))
    task2 = create_task(awaitable(future2))
    weechat_task_cb(future1.id, "data1")
    weechat_task_cb(future2.id, "data2")

    assert not shared.active_tasks
    assert not shared.active_futures
    assert task1.result() == ("awaitable", ("data1",))
    assert task2.result() == ("awaitable", ("data2",))


def test_task_without_await():
    shared.active_tasks = defaultdict(list)
    shared.active_futures = {}

    async def fun_without_await():
        pass

    async def run():
        await create_task(fun_without_await())

    create_task(run())

    assert not shared.active_tasks
    assert not shared.active_futures
