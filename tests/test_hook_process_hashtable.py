from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import weechat

import slack.http
from slack.http import hook_process_hashtable
from slack.task import FutureProcess, FutureTimer, weechat_task_cb
from slack.util import get_callback_name


@patch.object(weechat, "hook_process_hashtable")
def test_hook_process_hashtable(mock_method: MagicMock):
    command = "command"
    options = {"option": "1"}
    timeout = 123
    coroutine = hook_process_hashtable(command, options, timeout)
    future = coroutine.send(None)
    assert isinstance(future, FutureProcess)
    future.set_result((command, 0, "out", "err"))

    mock_method.assert_called_once_with(
        command, options, timeout, get_callback_name(weechat_task_cb), future.id
    )

    with pytest.raises(StopIteration) as excinfo:
        coroutine.send(None)
    assert excinfo.value.value == (command, 0, "out", "err")


@patch.object(weechat, "hook_process_hashtable")
def test_hook_process_hashtable_chunked(mock_method: MagicMock):
    command = "command"
    options = {"option": "1"}
    timeout = 123
    coroutine = hook_process_hashtable(command, options, timeout)
    future_1 = coroutine.send(None)
    assert isinstance(future_1, FutureProcess)
    future_1.set_result((command, -1, "o1", "e1"))

    mock_method.assert_called_once_with(
        command, options, timeout, get_callback_name(weechat_task_cb), future_1.id
    )

    future_2 = coroutine.send(None)
    assert isinstance(future_2, FutureProcess)
    future_2.set_result((command, -1, "o2", "e2"))

    future_3 = coroutine.send(None)
    assert isinstance(future_3, FutureProcess)
    future_3.set_result((command, 0, "o3", "e3"))

    with pytest.raises(StopIteration) as excinfo:
        coroutine.send(None)
    assert excinfo.value.value == (command, 0, "o1o2o3", "e1e2e3")


@patch.object(slack.http, "available_file_descriptors")
def test_hook_process_hashtable_wait_on_max_file_descriptors(
    mock_available_file_descriptors: MagicMock,
):
    mock_available_file_descriptors.return_value = 0
    coroutine = hook_process_hashtable("", {}, 0)
    future_1 = coroutine.send(None)
    assert isinstance(future_1, FutureTimer)
    future_1.set_result((0,))

    mock_available_file_descriptors.return_value = 9
    future_2 = coroutine.send(None)
    assert isinstance(future_2, FutureTimer)
    future_2.set_result((0,))

    mock_available_file_descriptors.return_value = 10
    assert isinstance(coroutine.send(None), FutureProcess)
