from __future__ import annotations

import os
import sys

import weechat

sys.path.append(os.path.dirname(os.path.realpath(__file__)))
import globals  # pylint: disable=wrong-import-position
from config import SlackConfig, SlackWorkspace  # pylint: disable=wrong-import-position
from task import create_task  # pylint: disable=wrong-import-position


def shutdown_cb():
    weechat.config_write(globals.config.weechat_config.pointer)
    return weechat.WEECHAT_RC_OK


async def init():
    print(globals.workspaces)
    if "wee-slack-test" not in globals.workspaces:
        globals.workspaces["wee-slack-test"] = SlackWorkspace("wee-slack-test")
        globals.workspaces[
            "wee-slack-test"
        ].config.api_token.value = weechat.config_get_plugin("api_token")
        globals.workspaces[
            "wee-slack-test"
        ].config.api_cookies.value = weechat.config_get_plugin("api_cookie")
    workspace = globals.workspaces["wee-slack-test"]
    print(workspace)
    print(workspace.config.slack_timeout.value)
    print(globals.config.color.reaction_suffix.value)


if __name__ == "__main__":
    if weechat.register(
        globals.SCRIPT_NAME,
        globals.SCRIPT_AUTHOR,
        globals.SCRIPT_VERSION,
        globals.SCRIPT_LICENSE,
        globals.SCRIPT_DESC,
        shutdown_cb.__name__,
        "",
    ):
        globals.weechat_version = int(weechat.info_get("version_number", "") or 0)
        globals.workspaces = {}
        globals.config = SlackConfig()
        globals.config.config_read()
        create_task(init(), final=True)
