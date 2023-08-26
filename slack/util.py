from __future__ import annotations

from typing import Callable, Optional

import weechat

from slack.shared import WeechatCallbackReturnType, shared


def get_callback_name(callback: Callable[..., WeechatCallbackReturnType]) -> str:
    callback_id = f"{callback.__name__}-{id(callback)}"
    shared.weechat_callbacks[callback_id] = callback
    return callback_id


def with_color(color: Optional[str], string: str, reset_color: str = "reset"):
    if color:
        return f"{weechat.color(color)}{string}{weechat.color(reset_color)}"
    else:
        return string
