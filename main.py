import os
import sys

import weechat

sys.path.append(os.path.dirname(os.path.realpath(__file__)))
from slack.config import SlackConfig
from slack.init import init  # pylint: disable=wrong-import-position
from slack.shared import shared  # pylint: disable=wrong-import-position
from slack.task import create_task  # pylint: disable=wrong-import-position
from slack.util import get_callback_name  # pylint: disable=wrong-import-position

shared.weechat_callbacks = globals()


def shutdown_cb():
    weechat.config_write(shared.config.weechat_config.pointer)
    return weechat.WEECHAT_RC_OK


if __name__ == "__main__":
    if weechat.register(
        shared.SCRIPT_NAME,
        shared.SCRIPT_AUTHOR,
        shared.SCRIPT_VERSION,
        shared.SCRIPT_LICENSE,
        shared.SCRIPT_DESC,
        get_callback_name(shutdown_cb),
        "",
    ):
        shared.weechat_version = int(weechat.info_get("version_number", "") or 0)
        shared.workspaces = {}
        shared.config = SlackConfig()
        shared.config.config_read()
        create_task(init(), final=True)
