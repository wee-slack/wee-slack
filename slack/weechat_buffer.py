from __future__ import annotations

from typing import Callable, Dict

import weechat

from slack.shared import shared
from slack.util import get_callback_name


def buffer_new(
    name: str,
    properties: Dict[str, str],
    input_callback: Callable[[str, str, str], int],
    close_callback: Callable[[str, str], int],
) -> str:
    input_callback_name = get_callback_name(input_callback)
    close_callback_name = get_callback_name(close_callback)
    if shared.weechat_version >= 0x03050000:
        # WeeChat < 4.5.0 doesn't send the buffer_switch signal if the display
        # property is used with buffer_new_props, so set it afterwards instead
        if shared.weechat_version < 0x04050000:
            set_display = properties.pop("display", None)
        else:
            set_display = None
        buffer_pointer = weechat.buffer_new_props(
            name,
            properties,
            input_callback_name,
            "",
            close_callback_name,
            "",
        )
        if set_display is not None:
            weechat.buffer_set(buffer_pointer, "display", set_display)
    else:
        buffer_pointer = weechat.buffer_new(
            name,
            input_callback_name,
            "",
            close_callback_name,
            "",
        )
        for prop_name, value in properties.items():
            weechat.buffer_set(buffer_pointer, prop_name, value)
    return buffer_pointer
