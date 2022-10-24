from enum import IntEnum

import globals
import weechat


class LogLevel(IntEnum):
    TRACE = 1
    DEBUG = 2
    INFO = 3
    WARN = 4
    ERROR = 5
    FATAL = 6


# TODO: Figure out what to do with print_error vs log
def print_error(message: str):
    weechat.prnt("", f"{weechat.prefix('error')}{globals.SCRIPT_NAME}: {message}")


def log(level: LogLevel, message: str):
    if level >= LogLevel.INFO:
        print(level, message)
