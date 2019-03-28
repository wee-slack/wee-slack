from __future__ import print_function, unicode_literals

from wee_slack import SlackTS


def test_slackts():
    base = SlackTS("1485976156.000017")

    b = SlackTS("1485976156.000016")
    c = SlackTS("1485976156.000018")

    d = SlackTS("1485976155.000017")
    e = SlackTS("1485976157.000017")

    assert base > b
    assert base < c

    assert base > d
    assert base < e

    c = SlackTS()
    assert c > base

    assert base == "1485976156.000017"
    assert base > "1485976156.000016"
    assert base < "1485976156.000018"
