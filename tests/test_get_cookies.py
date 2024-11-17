from __future__ import annotations

from slack.util import get_cookies


def test_get_cookies_without_key_value_encoded():
    cookie = get_cookies("a%2Bb")
    assert cookie == "d=a%2Bb"


def test_get_cookies_without_key_value_not_encoded():
    cookie = get_cookies("a+b")
    assert cookie == "d=a%2Bb"


def test_get_cookies_multiple_keys_value_encoded():
    cookie = get_cookies("d=a%2Bb ; d-s=1")
    assert cookie == "d=a%2Bb; d-s=1"


def test_get_cookies_multiple_keys_value_not_encoded():
    cookie = get_cookies("d=a+b ; d-s=1")
    assert cookie == "d=a%2Bb; d-s=1"
