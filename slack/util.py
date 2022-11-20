from typing import Callable, Dict, Union

import weechat

from slack.shared import shared

weechat_callback_return_type = Union[int, str, Dict[str, str], None]


def get_callback_name(callback: Callable[..., weechat_callback_return_type]) -> str:
    shared.weechat_callbacks[callback.__name__] = callback
    return callback.__name__


def with_color(color: str, string: str):
    return f"{weechat.color(color)}{string}{weechat.color('reset')}"
