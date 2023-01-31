from textwrap import dedent
from unittest.mock import MagicMock, patch

import pytest
import weechat

from slack.http import HttpError, http_request
from slack.task import FutureProcess, FutureTimer, weechat_task_cb
from slack.util import get_callback_name


@patch.object(weechat, "hook_process_hashtable")
def test_http_request_success(mock_method: MagicMock):
    url = "http://example.com"
    options = {"option": "1"}
    timeout = 123
    coroutine = http_request(url, options, timeout)

    future = coroutine.send(None)
    assert isinstance(future, FutureProcess)

    mock_method.assert_called_once_with(
        f"url:{url}",
        {**options, "header": "1"},
        timeout,
        get_callback_name(weechat_task_cb),
        future.id,
    )

    response = "response"
    body = f"HTTP/2 200\r\n\r\n{response}"
    future.set_result(("", 0, body, ""))

    with pytest.raises(StopIteration) as excinfo:
        coroutine.send(None)
    assert excinfo.value.value == response


def test_http_request_error_process_return_code():
    url = "http://example.com"
    coroutine = http_request(url, {}, 0, max_retries=0)

    future = coroutine.send(None)
    assert isinstance(future, FutureProcess)
    future.set_result(("", -2, "", ""))

    with pytest.raises(HttpError) as excinfo:
        coroutine.send(None)

    assert excinfo.value.url == url
    assert excinfo.value.return_code == -2
    assert excinfo.value.http_status_code == 0
    assert excinfo.value.error == ""


def test_http_request_error_process_stderr():
    url = "http://example.com"
    coroutine = http_request(url, {}, 0, max_retries=0)

    future = coroutine.send(None)
    assert isinstance(future, FutureProcess)
    future.set_result(("", 0, "", "err"))

    with pytest.raises(HttpError) as excinfo:
        coroutine.send(None)

    assert excinfo.value.url == url
    assert excinfo.value.return_code == 0
    assert excinfo.value.http_status_code == 0
    assert excinfo.value.error == "err"


def test_http_request_error_process_http():
    url = "http://example.com"
    coroutine = http_request(url, {}, 0, max_retries=0)

    future = coroutine.send(None)
    assert isinstance(future, FutureProcess)

    response = "response"
    body = f"HTTP/2 400\r\n\r\n{response}"
    future.set_result(("", 0, body, ""))

    with pytest.raises(HttpError) as excinfo:
        coroutine.send(None)

    assert excinfo.value.url == url
    assert excinfo.value.return_code == 0
    assert excinfo.value.http_status_code == 400
    assert excinfo.value.error == response


def test_http_request_error_retry_success():
    url = "http://example.com"
    coroutine = http_request(url, {}, 0, max_retries=2)

    future_1 = coroutine.send(None)
    assert isinstance(future_1, FutureProcess)
    future_1.set_result(("", -2, "", ""))

    future_2 = coroutine.send(None)
    assert isinstance(future_2, FutureTimer)
    future_2.set_result((0,))

    future_3 = coroutine.send(None)
    assert isinstance(future_3, FutureProcess)

    response = "response"
    body = f"HTTP/2 200\r\n\r\n{response}"
    future_3.set_result(("", 0, body, ""))

    with pytest.raises(StopIteration) as excinfo:
        coroutine.send(None)
    assert excinfo.value.value == response


def test_http_request_error_retry_error():
    url = "http://example.com"
    coroutine = http_request(url, {}, 0, max_retries=2)

    future_1 = coroutine.send(None)
    assert isinstance(future_1, FutureProcess)
    future_1.set_result(("", -2, "", ""))

    future_2 = coroutine.send(None)
    assert isinstance(future_2, FutureTimer)
    future_2.set_result((0,))

    future_3 = coroutine.send(None)
    assert isinstance(future_3, FutureProcess)
    future_3.set_result(("", -2, "", ""))

    future_4 = coroutine.send(None)
    assert isinstance(future_4, FutureTimer)
    future_4.set_result((0,))

    future_5 = coroutine.send(None)
    assert isinstance(future_5, FutureProcess)
    future_5.set_result(("", -2, "", ""))

    with pytest.raises(HttpError) as excinfo:
        coroutine.send(None)

    assert excinfo.value.url == url
    assert excinfo.value.return_code == -2
    assert excinfo.value.http_status_code == 0
    assert excinfo.value.error == ""


def test_http_request_multiple_headers():
    url = "http://example.com"
    coroutine = http_request(url, {}, 0)
    future = coroutine.send(None)
    assert isinstance(future, FutureProcess)

    response = "response"
    body = (
        dedent(
            f"""
            HTTP/1.1 200 Connection established

            HTTP/2 200
            content-type: application/json; charset=utf-8

            {response}
            """
        )
        .strip()
        .replace("\n", "\r\n")
    )
    future.set_result(("", 0, body, ""))

    with pytest.raises(StopIteration) as excinfo:
        coroutine.send(future)
    assert excinfo.value.value == response


@patch.object(weechat, "hook_timer")
def test_http_request_ratelimit(mock_method: MagicMock):
    url = "http://example.com"
    coroutine = http_request(url, {}, 0)

    future_1 = coroutine.send(None)
    assert isinstance(future_1, FutureProcess)

    body = "HTTP/2 429\r\nRetry-After: 12\r\n\r\n"
    future_1.set_result(("", 0, body, ""))

    future_2 = coroutine.send(None)
    assert isinstance(future_2, FutureTimer)
    future_2.set_result((0,))

    mock_method.assert_called_once_with(
        12000, 0, 1, get_callback_name(weechat_task_cb), future_2.id
    )

    future_3 = coroutine.send(None)
    assert isinstance(future_3, FutureProcess)

    response = "response"
    future_3.set_result(("", 0, f"HTTP/2 200\r\n\r\n{response}", ""))

    with pytest.raises(StopIteration) as excinfo:
        coroutine.send(None)
    assert excinfo.value.value == response
