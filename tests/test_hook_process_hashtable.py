from unittest.mock import MagicMock, patch

import pytest
import weechat

from slack import (
    FutureProcess,
    FutureTimer,
    hook_process_hashtable,
    weechat_task_cb,
)
import slack


@patch.object(weechat, "hook_process_hashtable")
def test_hook_process_hashtable(mock_method: MagicMock):
    command = "command"
    options = {"option": "1"}
    timeout = 123
    coroutine = hook_process_hashtable(command, options, timeout)
    future = coroutine.send(None)
    assert isinstance(future, FutureProcess)

    mock_method.assert_called_once_with(
        command, options, timeout, weechat_task_cb.__name__, future.id
    )

    with pytest.raises(StopIteration) as excinfo:
        coroutine.send((command, 0, "out", "err"))
    assert excinfo.value.value == (command, 0, "out", "err")


@patch.object(weechat, "hook_process_hashtable")
def test_hook_process_hashtable_chunked(mock_method: MagicMock):
    command = "command"
    options = {"option": "1"}
    timeout = 123
    coroutine = hook_process_hashtable(command, options, timeout)
    future = coroutine.send(None)
    assert isinstance(future, FutureProcess)

    mock_method.assert_called_once_with(
        command, options, timeout, weechat_task_cb.__name__, future.id
    )

    assert isinstance(coroutine.send((command, -1, "o1", "e1")), FutureProcess)
    assert isinstance(coroutine.send((command, -1, "o2", "e2")), FutureProcess)

    with pytest.raises(StopIteration) as excinfo:
        coroutine.send((command, 0, "o3", "e3"))
    assert excinfo.value.value == (command, 0, "o1o2o3", "e1e2e3")


@patch.object(slack, "available_file_descriptors")
def test_hook_process_hashtable_wait_on_max_file_descriptors(
    mock_available_file_descriptors: MagicMock,
):
    mock_available_file_descriptors.return_value = 0
    coroutine = hook_process_hashtable("", {}, 0)
    future = coroutine.send(None)
    assert isinstance(future, FutureTimer)

    mock_available_file_descriptors.return_value = 9
    assert isinstance(coroutine.send((0,)), FutureTimer)

    mock_available_file_descriptors.return_value = 10
    assert isinstance(coroutine.send((0,)), FutureProcess)
