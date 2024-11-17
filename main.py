from __future__ import annotations

import os
import sys

sys.path.append(os.path.dirname(os.path.realpath(__file__)))
from slack.register import register  # noqa: E402, pylint: disable=wrong-import-position
from slack.shared import shared  # noqa: E402, pylint: disable=wrong-import-position

shared.weechat_callbacks = globals()

if __name__ == "__main__":
    register()
