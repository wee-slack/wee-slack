from __future__ import annotations

from slack.slack_message import SlackTs

str_base = "1234567890.012345"
str_base_not_padded = "1234567890.12345"
str_different_minor = "1234567890.012346"
str_different_major = "1234567891.012345"

ts_base = SlackTs(str_base)
ts_base_not_padded = SlackTs(str_base_not_padded)
ts_different_minor = SlackTs(str_different_minor)
ts_different_major = SlackTs(str_different_major)


def test_slackts_eq():
    assert ts_base == ts_base
    assert ts_base == ts_base_not_padded
    assert ts_base == str_base
    assert not ts_base == ts_different_minor
    assert not ts_base == ts_different_major
    assert not ts_base == str_different_minor
    assert not ts_base == str_different_major


def test_slackts_ne():
    assert ts_base != ts_different_minor
    assert ts_base != ts_different_major
    assert ts_base != str_different_minor
    assert ts_base != str_different_major
    assert not ts_base != ts_base
    assert not ts_base != ts_base_not_padded
    assert not ts_base != str_base


def test_slackts_gt():
    assert ts_different_minor > ts_base
    assert ts_different_major > ts_base
    assert str_different_minor > ts_base
    assert str_different_major > ts_base
    assert not ts_base > ts_base
    assert not ts_base > ts_base_not_padded
    assert not ts_base > ts_different_minor
    assert not ts_base > ts_different_major
    assert not ts_base > str_base
    assert not ts_base > str_different_minor
    assert not ts_base > str_different_major


def test_slackts_ge():
    assert ts_base >= ts_base
    assert ts_base >= ts_base_not_padded
    assert ts_different_minor >= ts_base
    assert ts_different_major >= ts_base
    assert ts_base >= str_base
    assert str_different_minor >= ts_base
    assert str_different_major >= ts_base
    assert not ts_base >= ts_different_minor
    assert not ts_base >= ts_different_major
    assert not ts_base >= str_different_minor
    assert not ts_base >= str_different_major


def test_slackts_lt():
    assert ts_base < ts_different_minor
    assert ts_base < ts_different_major
    assert ts_base < str_different_minor
    assert ts_base < str_different_major
    assert not ts_base < ts_base
    assert not ts_base < ts_base_not_padded
    assert not ts_different_minor < ts_base
    assert not ts_different_major < ts_base
    assert not ts_base < str_base
    assert not str_different_minor < ts_base
    assert not str_different_major < ts_base


def test_slackts_le():
    assert ts_base <= ts_base
    assert ts_base <= ts_base_not_padded
    assert ts_base <= ts_different_minor
    assert ts_base <= ts_different_major
    assert ts_base <= str_base
    assert ts_base <= str_different_minor
    assert ts_base <= str_different_major
    assert not ts_different_minor <= ts_base
    assert not ts_different_major <= ts_base
    assert not str_different_minor <= ts_base
    assert not str_different_major <= ts_base
