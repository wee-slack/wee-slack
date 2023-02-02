from __future__ import annotations

from enum import IntEnum
from typing import Set

import weechat

from slack.error import store_and_format_exception
from slack.shared import shared

printed_exceptions: Set[BaseException] = set()


class LogLevel(IntEnum):
    TRACE = 1
    DEBUG = 2
    INFO = 3
    WARN = 4
    ERROR = 5
    FATAL = 6


# TODO: Figure out what to do with print_error vs log
def print_error(message: str):
    weechat.prnt("", f"{weechat.prefix('error')}{shared.SCRIPT_NAME}: {message}")


def print_exception_once(e: BaseException):
    if e not in printed_exceptions:
        print_error(store_and_format_exception(e))
        printed_exceptions.add(e)


def log(level: LogLevel, message: str):
    if level >= LogLevel.INFO:
        prefix = weechat.prefix("error") if level >= LogLevel.ERROR else "\t"
        weechat.prnt("", f"{prefix}{shared.SCRIPT_NAME} {level.name}: {message}")
