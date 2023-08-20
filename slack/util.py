from __future__ import annotations

from typing import Callable

import weechat

from slack.shared import WeechatCallbackReturnType, shared


def get_callback_name(callback: Callable[..., WeechatCallbackReturnType]) -> str:
    callback_id = f"{callback.__name__}-{id(callback)}"
    shared.weechat_callbacks[callback_id] = callback
    return callback_id


def with_color(color: str, string: str, reset_color: str = "reset"):
    return f"{weechat.color(color)}{string}{weechat.color(reset_color)}"
