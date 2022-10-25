import os
import sys

import weechat

sys.path.append(os.path.dirname(os.path.realpath(__file__)))
from slack import globals as G  # pylint: disable=wrong-import-position
from slack.config import SlackConfig
from slack.main import init  # pylint: disable=wrong-import-position
from slack.task import create_task  # pylint: disable=wrong-import-position
from slack.util import get_callback_name  # pylint: disable=wrong-import-position

G.weechat_callbacks = globals()


def shutdown_cb():
    weechat.config_write(G.config.weechat_config.pointer)
    return weechat.WEECHAT_RC_OK


if __name__ == "__main__":
    if weechat.register(
        G.SCRIPT_NAME,
        G.SCRIPT_AUTHOR,
        G.SCRIPT_VERSION,
        G.SCRIPT_LICENSE,
        G.SCRIPT_DESC,
        get_callback_name(shutdown_cb),
        "",
    ):
        G.weechat_version = int(weechat.info_get("version_number", "") or 0)
        G.workspaces = {}
        G.config = SlackConfig()
        G.config.config_read()
        create_task(init(), final=True)
