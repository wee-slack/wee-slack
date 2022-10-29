from typing import Any, Callable

from slack.shared import shared


def get_callback_name(callback: Callable[..., Any]) -> str:
    shared.weechat_callbacks[callback.__name__] = callback
    return callback.__name__
