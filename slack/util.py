from typing import Any, Callable

import weechat

from slack.shared import shared


def get_callback_name(callback: Callable[..., Any]) -> str:
    shared.weechat_callbacks[callback.__name__] = callback
    return callback.__name__


def with_color(color: str, string: str):
    return f"{weechat.color(color)}{string}{weechat.color('reset')}"
