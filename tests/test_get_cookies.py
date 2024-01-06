from slack.util import get_cookies


def test_get_cookies_multiple_keys_value_encoded():
    cookie = get_cookies("d=a%2Bb ; d-s=1")
    assert cookie == "d=a%2Bb; d-s=1"


def test_get_cookies_multiple_keys_value_not_encoded():
    cookie = get_cookies("d=a+b ; d-s=1")
    assert cookie == "d=a%2Bb; d-s=1"
