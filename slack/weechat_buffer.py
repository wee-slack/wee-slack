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
        buffer_pointer = weechat.buffer_new_props(
            name,
            properties,
            input_callback_name,
            "",
            close_callback_name,
            "",
        )
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
