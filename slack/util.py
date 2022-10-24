from typing import Any, Callable

import globals as G


def get_callback_name(callback: Callable[..., Any]) -> str:
    G.weechat_callbacks[callback.__name__] = callback
    return callback.__name__
