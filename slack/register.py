from __future__ import annotations

import weechat

from slack.commands import register_commands
from slack.completions import register_completions
from slack.config import SlackConfig
from slack.shared import shared
from slack.slack_emoji import load_standard_emojis
from slack.slack_message_buffer import SlackMessageBuffer
from slack.task import run_async, sleep
from slack.util import get_callback_name, with_color

SCRIPT_AUTHOR = "Trygve Aaberge <trygveaa@gmail.com>"
SCRIPT_LICENSE = "MIT"
SCRIPT_DESC = "Extends weechat for typing notification/search/etc on slack.com"


def shutdown_cb():
    shared.script_is_unloading = True
    weechat.config_write(shared.config.weechat_config.pointer)
    return weechat.WEECHAT_RC_OK


def signal_buffer_switch_cb(data: str, signal: str, buffer_pointer: str) -> int:
    prev_buffer_pointer = shared.current_buffer_pointer
    shared.current_buffer_pointer = buffer_pointer

    if prev_buffer_pointer != buffer_pointer:
        prev_slack_buffer = shared.buffers.get(prev_buffer_pointer)
        if isinstance(prev_slack_buffer, SlackMessageBuffer):
            run_async(prev_slack_buffer.mark_read())

    slack_buffer = shared.buffers.get(buffer_pointer)
    if isinstance(slack_buffer, SlackMessageBuffer):
        run_async(slack_buffer.buffer_switched_to())

    return weechat.WEECHAT_RC_OK


def input_text_changed_cb(data: str, signal: str, buffer_pointer: str) -> int:
    reset_completion_context_on_input(buffer_pointer)
    return weechat.WEECHAT_RC_OK


def input_text_cursor_moved_cb(data: str, signal: str, buffer_pointer: str) -> int:
    reset_completion_context_on_input(buffer_pointer)
    return weechat.WEECHAT_RC_OK


def reset_completion_context_on_input(buffer_pointer: str):
    slack_buffer = shared.buffers.get(buffer_pointer)
    if (
        isinstance(slack_buffer, SlackMessageBuffer)
        and slack_buffer.completion_context != "IN_PROGRESS_COMPLETION"
    ):
        slack_buffer.completion_context = "NO_COMPLETION"


def modifier_input_text_display_with_cursor_cb(
    data: str, modifier: str, buffer_pointer: str, string: str
) -> str:
    prefix = ""
    slack_buffer = shared.buffers.get(buffer_pointer)
    if slack_buffer:
        input_delim_color = weechat.config_string(
            weechat.config_get("weechat.bar.input.color_delim")
        )
        input_delim_start = with_color(input_delim_color, "[")
        input_delim_end = with_color(input_delim_color, "]")
        if (
            not slack_buffer.workspace.is_connected
            and not slack_buffer.workspace.is_connecting
        ):
            prefix += (
                f"{input_delim_start}"
                f"{with_color(shared.config.color.disconnected.value, 'disconnected')}"
                f"{input_delim_end} "
            )
        if (
            slack_buffer.workspace.is_connecting
            or isinstance(slack_buffer, SlackMessageBuffer)
            and slack_buffer.is_loading
        ):
            text = "connecting" if slack_buffer.workspace.is_connecting else "loading"
            prefix += (
                f"{input_delim_start}"
                f"{with_color(shared.config.color.loading.value, text)}"
                f"{input_delim_end} "
            )
    return prefix + string


def key_pressed_cb(data: str, signal: str, signal_data: str) -> int:
    for workspace in shared.workspaces.values():
        if (
            workspace.is_connected
            and workspace.config.keep_active.value == "on_activity"
        ):
            workspace.tickle()
    return weechat.WEECHAT_RC_OK


def typing_self_cb(data: str, signal: str, signal_data: str) -> int:
    if not shared.config.look.typing_status_self or signal != "typing_self_typing":
        return weechat.WEECHAT_RC_OK

    slack_buffer = shared.buffers.get(signal_data)
    if isinstance(slack_buffer, SlackMessageBuffer):
        slack_buffer.set_typing_self()
    return weechat.WEECHAT_RC_OK


def timer_tickle_cb(data: str, remaining_calls: int) -> int:
    for workspace in shared.workspaces.values():
        if workspace.is_connected and workspace.config.keep_active.value == "always":
            workspace.tickle(force=True)
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
        shared.current_buffer_pointer = weechat.current_buffer()
        shared.standard_emojis = load_standard_emojis()
        shared.standard_emojis_inverse = {
            value["unicode"]: value for value in shared.standard_emojis.values()
        }
        shared.workspaces = {}
        shared.config = SlackConfig()
        shared.config.config_read()
        register_completions()
        register_commands()

        weechat.hook_signal(
            "buffer_switch", get_callback_name(signal_buffer_switch_cb), ""
        )
        weechat.hook_signal(
            "input_text_changed", get_callback_name(input_text_changed_cb), ""
        )
        weechat.hook_signal(
            "input_text_cursor_moved", get_callback_name(input_text_cursor_moved_cb), ""
        )
        weechat.hook_modifier(
            "100|input_text_display_with_cursor",
            get_callback_name(modifier_input_text_display_with_cursor_cb),
            "",
        )
        weechat.hook_signal("key_pressed", get_callback_name(key_pressed_cb), "")
        weechat.hook_signal("typing_self_*", get_callback_name(typing_self_cb), "")
        weechat.hook_timer(20000, 0, 0, get_callback_name(timer_tickle_cb), "")
        weechat.hook_timer(5000, 0, 0, get_callback_name(ws_ping_cb), "")

        run_async(init_async())
