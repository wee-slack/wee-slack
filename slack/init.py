import weechat

from slack.commands import register_commands
from slack.config import SlackConfig
from slack.shared import shared
from slack.task import create_task, sleep
from slack.util import get_callback_name

SCRIPT_AUTHOR = "Trygve Aaberge <trygveaa@gmail.com>"
SCRIPT_LICENSE = "MIT"
SCRIPT_DESC = "Extends weechat for typing notification/search/etc on slack.com"
REPO_URL = "https://github.com/wee-slack/wee-slack"


def shutdown_cb():
    weechat.config_write(shared.config.weechat_config.pointer)
    return weechat.WEECHAT_RC_OK


def signal_buffer_switch_cb(data: str, signal: str, signal_data: str) -> int:
    current_conversation = None
    for workspace in shared.workspaces.values():
        conversation = workspace.get_conversation_from_buffer_pointer(signal_data)
        if conversation:
            current_conversation = conversation

    if current_conversation:
        create_task(current_conversation.fill_history())
    return weechat.WEECHAT_RC_OK


async def init():
    auto_connect = weechat.info_get("auto_connect", "") == "1"
    if auto_connect:
        await sleep(1)  # Defer auto connect to ensure the logger plugin is loaded
        for workspace in shared.workspaces.values():
            if workspace.config.autoconnect.value:
                await workspace.connect()


def main():
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

        create_task(init(), final=True)
