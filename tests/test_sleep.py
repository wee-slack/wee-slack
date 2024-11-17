from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import weechat

from slack.task import FutureTimer, sleep, weechat_task_cb
from slack.util import get_callback_name


@patch.object(weechat, "hook_timer")
def test_sleep(mock_method: MagicMock):
    milliseconds = 123
    coroutine = sleep(milliseconds)
    future = coroutine.send(None)
    assert isinstance(future, FutureTimer)
    future.set_result((0,))

    mock_method.assert_called_once_with(
        milliseconds, 0, 1, get_callback_name(weechat_task_cb), future.id
    )

    with pytest.raises(StopIteration) as excinfo:
        coroutine.send(None)
    assert excinfo.value.value == (0,)  # TODO: Will probably change to None
