# -*- coding: utf-8 -*-

from __future__ import print_function, unicode_literals
from textwrap import dedent

from wee_slack import SlackRequest


def test_http_check_ratelimited_supports_multiple_headers(realish_eventrouter):
    response = (
        dedent(
            """
            HTTP/1.1 200 Connection established

            HTTP/2 200
            content-type: application/json; charset=utf-8

            {"ok": true}
            """
        )
        .strip()
        .replace("\n", "\r\n")
    )

    request_metadata = SlackRequest(None, "", token="xoxp-1")
    body, error = realish_eventrouter.http_check_ratelimited(request_metadata, response)
    assert body == '{"ok": true}'
    assert error == ""


def test_http_check_ratelimited_return_error_when_ratelimited(realish_eventrouter):
    response = (
        dedent(
            """
            HTTP/2 429
            content-type: application/json; charset=utf-8
            retry-after: 10

            {"ok": false, "error": "ratelimited"}
            """
        )
        .strip()
        .replace("\n", "\r\n")
    )

    request_metadata = SlackRequest(None, "", token="xoxp-1")
    body, error = realish_eventrouter.http_check_ratelimited(request_metadata, response)
    assert body == ""
    assert error == "ratelimited"
