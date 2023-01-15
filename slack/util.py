from __future__ import annotations

from typing import Callable, Dict, Union

import weechat

from slack.shared import shared

weechat_callback_return_type = Union[int, str, Dict[str, str], None]


def get_callback_name(callback: Callable[..., weechat_callback_return_type]) -> str:
    callback_id = f"{callback.__name__}-{id(callback)}"
    shared.weechat_callbacks[callback_id] = callback
    return callback_id


def with_color(color: str, string: str):
    return f"{weechat.color(color)}{string}{weechat.color('reset')}"
