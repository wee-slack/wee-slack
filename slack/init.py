import weechat

from slack.config import SlackConfig, SlackWorkspace
from slack.shared import shared
from slack.task import create_task
from slack.util import get_callback_name

SCRIPT_AUTHOR = "Trygve Aaberge <trygveaa@gmail.com>"
SCRIPT_LICENSE = "MIT"
SCRIPT_DESC = "Extends weechat for typing notification/search/etc on slack.com"
REPO_URL = "https://github.com/wee-slack/wee-slack"


def shutdown_cb():
    weechat.config_write(shared.config.weechat_config.pointer)
    return weechat.WEECHAT_RC_OK


async def init():
    print(shared.workspaces)
    if "wee-slack-test" not in shared.workspaces:
        shared.workspaces["wee-slack-test"] = SlackWorkspace("wee-slack-test")
        shared.workspaces[
            "wee-slack-test"
        ].config.api_token.value = weechat.config_get_plugin("api_token")
        shared.workspaces[
            "wee-slack-test"
        ].config.api_cookies.value = weechat.config_get_plugin("api_cookie")
    workspace = shared.workspaces["wee-slack-test"]
    print(workspace)
    print(workspace.config.slack_timeout.value)
    print(shared.config.color.reaction_suffix.value)


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
        create_task(init(), final=True)
