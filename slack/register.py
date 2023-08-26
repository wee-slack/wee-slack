from __future__ import annotations

import weechat

from slack.commands import register_commands
from slack.config import SlackConfig
from slack.shared import shared
from slack.slack_conversation import get_conversation_from_buffer_pointer
from slack.slack_emoji import load_standard_emojis
from slack.task import run_async, sleep
from slack.util import get_callback_name, with_color

SCRIPT_AUTHOR = "Trygve Aaberge <trygveaa@gmail.com>"
SCRIPT_LICENSE = "MIT"
SCRIPT_DESC = "Extends weechat for typing notification/search/etc on slack.com"


def shutdown_cb():
    weechat.config_write(shared.config.weechat_config.pointer)
    return weechat.WEECHAT_RC_OK


def signal_buffer_switch_cb(data: str, signal: str, buffer_pointer: str) -> int:
    conversation = get_conversation_from_buffer_pointer(buffer_pointer)
    if conversation:
        run_async(conversation.buffer_switched_to())
    return weechat.WEECHAT_RC_OK


def input_text_changed_cb(data: str, signal: str, buffer_pointer: str) -> int:
    reset_completion_context_on_input(buffer_pointer)
    return weechat.WEECHAT_RC_OK


def input_text_cursor_moved_cb(data: str, signal: str, buffer_pointer: str) -> int:
    reset_completion_context_on_input(buffer_pointer)
    return weechat.WEECHAT_RC_OK


def reset_completion_context_on_input(buffer_pointer: str):
    conversation = get_conversation_from_buffer_pointer(buffer_pointer)
    if conversation and conversation.completion_context != "IN_PROGRESS_COMPLETION":
        conversation.completion_context = "NO_COMPLETION"


def modifier_input_text_display_with_cursor_cb(
    data: str, modifier: str, buffer_pointer: str, string: str
) -> str:
    prefix = ""
    conversation = get_conversation_from_buffer_pointer(buffer_pointer)
    if conversation:
        input_delim_color = weechat.config_string(
            weechat.config_get("weechat.bar.input.color_delim")
        )
        input_delim_start = with_color(input_delim_color, "[")
        input_delim_end = with_color(input_delim_color, "]")
        if not conversation.workspace.is_connected:
            prefix += (
                f"{input_delim_start}"
                f"{with_color(shared.config.color.disconnected.value, 'disconnected')}"
                f"{input_delim_end} "
            )
        if conversation.is_loading:
            prefix += (
                f"{input_delim_start}"
                f"{with_color(shared.config.color.loading.value, 'loading')}"
                f"{input_delim_end} "
            )
    return prefix + string


def typing_self_cb(data: str, signal: str, signal_data: str) -> int:
    if not shared.config.look.typing_status_self:
        return weechat.WEECHAT_RC_OK

    conversation = get_conversation_from_buffer_pointer(signal_data)
    if conversation:
        conversation.typing_update_self(signal)
    return weechat.WEECHAT_RC_OK


def ws_ping_cb(data: str, remaining_calls: int) -> int:
    for workspace in shared.workspaces.values():
        if workspace.is_connected:
            workspace.ping()
    return weechat.WEECHAT_RC_OK


async def init_async():
    auto_connect = weechat.info_get("auto_connect", "") == "1"
    if auto_connect:
        await sleep(1)  # Defer auto connect to ensure the logger plugin is loaded
        for workspace in shared.workspaces.values():
            if workspace.config.autoconnect:
                run_async(workspace.connect())


def register():
    if weechat.register(
        shared.SCRIPT_NAME,
        SCRIPT_AUTHOR,
        shared.SCRIPT_VERSION,
        SCRIPT_LICENSE,
        SCRIPT_DESC,
        get_callback_name(shutdown_cb),
        "",
    ):
        shared.weechat_version = int(weechat.info_get("version_number", "") or 0)
        shared.standard_emojis = load_standard_emojis()
        shared.workspaces = {}
        shared.config = SlackConfig()
        shared.config.config_read()
        register_commands()

        weechat.hook_signal(
            "buffer_switch", get_callback_name(signal_buffer_switch_cb), ""
        )
        weechat.hook_signal(
            "window_switch", get_callback_name(signal_buffer_switch_cb), ""
        )
        weechat.hook_signal(
            "input_text_changed", get_callback_name(input_text_changed_cb), ""
        )
        weechat.hook_signal(
            "input_text_cursor_moved", get_callback_name(input_text_cursor_moved_cb), ""
        )
        weechat.hook_modifier(
            "input_text_display_with_cursor",
            get_callback_name(modifier_input_text_display_with_cursor_cb),
            "",
        )
        weechat.hook_signal("typing_self_*", get_callback_name(typing_self_cb), "")
        weechat.hook_timer(5000, 0, 0, get_callback_name(ws_ping_cb), "")

        run_async(init_async())
