from __future__ import annotations

import time
from dataclasses import dataclass
from enum import IntEnum
from typing import List, Set

import weechat

from slack.error import store_and_format_exception
from slack.shared import shared
from slack.util import get_callback_name


class LogLevel(IntEnum):
    TRACE = 1
    DEBUG = 2
    INFO = 3
    WARN = 4
    ERROR = 5
    FATAL = 6


class DebugMessageType(IntEnum):
    WEBSOCKET_SEND = 1
    WEBSOCKET_RECV = 2
    HTTP_REQUEST = 3
    LOG = 4


@dataclass
class DebugMessage:
    time: float
    level: LogLevel
    message_type: DebugMessageType
    message: str


debug_messages: List[DebugMessage] = []
printed_exceptions: Set[BaseException] = set()


# TODO: Figure out what to do with print_error vs log
def print_error(message: str):
    weechat.prnt("", f"{weechat.prefix('error')}{shared.SCRIPT_NAME}: {message}")


def print_exception_once(e: BaseException):
    if e not in printed_exceptions:
        print_error(store_and_format_exception(e))
        printed_exceptions.add(e)


def log(level: LogLevel, message_type: DebugMessageType, message: str):
    if level >= LogLevel.INFO:
        prefix = weechat.prefix("error") if level >= LogLevel.ERROR else "\t"
        weechat.prnt("", f"{prefix}{shared.SCRIPT_NAME} {level.name}: {message}")

    debug_message = DebugMessage(time.time(), level, message_type, message)
    debug_messages.append(debug_message)
    print_debug_buffer(debug_message)


def _close_debug_buffer_cb(data: str, buffer: str):
    shared.debug_buffer_pointer = None
    return weechat.WEECHAT_RC_OK


def open_debug_buffer():
    if shared.debug_buffer_pointer:
        weechat.buffer_set(shared.debug_buffer_pointer, "display", "1")
        return

    name = f"{shared.SCRIPT_NAME}.debug"
    shared.debug_buffer_pointer = weechat.buffer_new_props(
        name,
        {"display": "1"},
        "",
        "",
        get_callback_name(_close_debug_buffer_cb),
        "",
    )
    for message in debug_messages:
        print_debug_buffer(message)


def print_debug_buffer(debug_message: DebugMessage):
    if shared.debug_buffer_pointer:
        message = f"{debug_message.level.name} - {debug_message.message_type.name}\t{debug_message.message}"
        weechat.prnt_date_tags(
            shared.debug_buffer_pointer, int(debug_message.time), "", message
        )
