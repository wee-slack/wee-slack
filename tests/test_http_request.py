from __future__ import annotations

from textwrap import dedent
from unittest.mock import MagicMock, patch

import pytest
import weechat

from slack.http import HttpError, http_request, http_request_process, http_request_url
from slack.task import FutureProcess, FutureTimer, FutureUrl, weechat_task_cb
from slack.util import get_callback_name


@patch.object(weechat, "hook_url")
def test_http_request_success(mock_method: MagicMock):
    url = "http://example.com"
    options = {"option": "1"}
    timeout = 123
    coroutine = http_request(url, options, timeout)

    future = coroutine.send(None)
    assert isinstance(future, FutureUrl)

    mock_method.assert_called_once_with(
        url,
        options,
        timeout,
        get_callback_name(weechat_task_cb),
        future.id,
    )

    future.set_result(
        (url, options, {"response_code": "200", "headers": "", "output": "response"})
    )

    with pytest.raises(StopIteration) as excinfo:
        coroutine.send(None)
    assert excinfo.value.value == "response"


@patch.object(weechat, "hook_process_hashtable")
def test_http_request_process_success(mock_method: MagicMock):
    url = "http://example.com"
    options = {"option": "1"}
    timeout = 123
    coroutine = http_request_process(url, options, timeout)

    future = coroutine.send(None)
    assert isinstance(future, FutureProcess)

    mock_method.assert_called_once_with(
        f"url:{url}",
        {**options, "header": "1"},
        timeout,
        get_callback_name(weechat_task_cb),
        future.id,
    )

    body = "HTTP/2 200\r\n\r\nresponse"
    future.set_result(("", 0, body, ""))

    with pytest.raises(StopIteration) as excinfo:
        coroutine.send(None)
    assert excinfo.value.value == (200, "HTTP/2 200", "response")


def test_http_request_url_error():
    url = "http://example.com"
    coroutine = http_request_url(url, {}, 0)

    future = coroutine.send(None)
    assert isinstance(future, FutureUrl)
    future.set_result((url, {}, {"error": "error"}))

    with pytest.raises(HttpError) as excinfo:
        coroutine.send(None)

    assert excinfo.value.url == url
    assert excinfo.value.return_code is None
    assert excinfo.value.http_status_code is None
    assert excinfo.value.error == "error"


def test_http_request_process_error_return_code():
    url = "http://example.com"
    coroutine = http_request_process(url, {}, 0)

    future = coroutine.send(None)
    assert isinstance(future, FutureProcess)
    future.set_result(("", -2, "", ""))

    with pytest.raises(HttpError) as excinfo:
        coroutine.send(None)

    assert excinfo.value.url == url
    assert excinfo.value.return_code == -2
    assert excinfo.value.http_status_code is None
    assert excinfo.value.error == ""


def test_http_request_process_error_stderr():
    url = "http://example.com"
    coroutine = http_request_process(url, {}, 0)

    future = coroutine.send(None)
    assert isinstance(future, FutureProcess)
    future.set_result(("", 0, "", "err"))

    with pytest.raises(HttpError) as excinfo:
        coroutine.send(None)

    assert excinfo.value.url == url
    assert excinfo.value.return_code == 0
    assert excinfo.value.http_status_code is None
    assert excinfo.value.error == "err"


def test_http_request_error_http_status():
    url = "http://example.com"
    coroutine = http_request(url, {}, 0)

    future = coroutine.send(None)
    assert isinstance(future, FutureUrl)

    future.set_result(
        (url, {}, {"response_code": "400", "headers": "", "output": "response"})
    )

    with pytest.raises(HttpError) as excinfo:
        coroutine.send(None)

    assert excinfo.value.url == url
    assert excinfo.value.return_code is None
    assert excinfo.value.http_status_code == 400
    assert excinfo.value.error == "response"


def test_http_request_error_retry_success():
    url = "http://example.com"
    coroutine = http_request(url, {}, 0, max_retries=2)

    future_1 = coroutine.send(None)
    assert isinstance(future_1, FutureUrl)
    future_1.set_result((url, {}, {"error": "error"}))

    future_2 = coroutine.send(None)
    assert isinstance(future_2, FutureTimer)
    future_2.set_result((0,))

    future_3 = coroutine.send(None)
    assert isinstance(future_3, FutureUrl)

    future_3.set_result(
        (url, {}, {"response_code": "200", "headers": "", "output": "response"})
    )

    with pytest.raises(StopIteration) as excinfo:
        coroutine.send(None)
    assert excinfo.value.value == "response"


def test_http_request_error_retry_error():
    url = "http://example.com"
    coroutine = http_request(url, {}, 0, max_retries=2)

    future_1 = coroutine.send(None)
    assert isinstance(future_1, FutureUrl)
    future_1.set_result((url, {}, {"error": "error"}))

    future_2 = coroutine.send(None)
    assert isinstance(future_2, FutureTimer)
    future_2.set_result((0,))

    future_3 = coroutine.send(None)
    assert isinstance(future_3, FutureUrl)
    future_3.set_result((url, {}, {"error": "error"}))

    future_4 = coroutine.send(None)
    assert isinstance(future_4, FutureTimer)
    future_4.set_result((0,))

    future_5 = coroutine.send(None)
    assert isinstance(future_5, FutureUrl)
    future_5.set_result((url, {}, {"error": "error"}))

    with pytest.raises(HttpError) as excinfo:
        coroutine.send(None)

    assert excinfo.value.url == url
    assert excinfo.value.return_code is None
    assert excinfo.value.http_status_code is None
    assert excinfo.value.error == "error"


def test_http_request_url_multiple_headers():
    url = "http://example.com"
    coroutine = http_request_url(url, {}, 0)
    future = coroutine.send(None)
    assert isinstance(future, FutureUrl)

    headers = (
        dedent(
            """
            HTTP/1.1 200 Connection established

            HTTP/2 200
            content-type: application/json; charset=utf-8
            """
        )
        .strip()
        .replace("\n", "\r\n")
    )
    future.set_result(
        (url, {}, {"response_code": "200", "headers": headers, "output": "response"})
    )

    with pytest.raises(StopIteration) as excinfo:
        coroutine.send(future)
    assert excinfo.value.value == (
        200,
        "2 200\r\ncontent-type: application/json; charset=utf-8",
        "response",
    )


def test_http_request_process_multiple_headers():
    url = "http://example.com"
    coroutine = http_request_process(url, {}, 0)
    future = coroutine.send(None)
    assert isinstance(future, FutureProcess)

    body = (
        dedent(
            """
            HTTP/1.1 200 Connection established

            HTTP/2 200
            content-type: application/json; charset=utf-8

            response
            """
        )
        .strip()
        .replace("\n", "\r\n")
    )
    future.set_result(("", 0, body, ""))

    with pytest.raises(StopIteration) as excinfo:
        coroutine.send(future)
    assert excinfo.value.value == (
        200,
        "2 200\r\ncontent-type: application/json; charset=utf-8",
        "response",
    )


@patch.object(weechat, "hook_timer")
def test_http_request_ratelimit(mock_method: MagicMock):
    url = "http://example.com"
    coroutine = http_request(url, {}, 0)

    future_1 = coroutine.send(None)
    assert isinstance(future_1, FutureUrl)

    future_1.set_result(
        (
            url,
            {},
            {
                "response_code": "429",
                "headers": "HTTP/2 429\r\nRetry-After: 12",
                "output": "response",
            },
        )
    )

    future_2 = coroutine.send(None)
    assert isinstance(future_2, FutureTimer)
    future_2.set_result((0,))

    mock_method.assert_called_once_with(
        12000, 0, 1, get_callback_name(weechat_task_cb), future_2.id
    )

    future_3 = coroutine.send(None)
    assert isinstance(future_3, FutureUrl)

    future_3.set_result(
        (url, {}, {"response_code": "200", "headers": "", "output": "response"})
    )

    with pytest.raises(StopIteration) as excinfo:
        coroutine.send(None)
    assert excinfo.value.value == "response"
