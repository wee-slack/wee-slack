from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Tuple

if TYPE_CHECKING:
    from .api import SlackWorkspace
    from .config import SlackConfig
    from .task import Task


class Shared:
    def __init__(self):
        self.SCRIPT_NAME = "slack"
        self.SCRIPT_AUTHOR = "Trygve Aaberge <trygveaa@gmail.com>"
        self.SCRIPT_VERSION = "3.0.0"
        self.SCRIPT_LICENSE = "MIT"
        self.SCRIPT_DESC = (
            "Extends weechat for typing notification/search/etc on slack.com"
        )
        self.REPO_URL = "https://github.com/wee-slack/wee-slack"

        self.weechat_version: int
        self.weechat_callbacks: Dict[str, Any]
        self.active_tasks: Dict[str, Task[Any]] = {}
        self.active_responses: Dict[str, Tuple[Any, ...]] = {}
        self.workspaces: Dict[str, SlackWorkspace] = {}
        self.config: SlackConfig


shared = Shared()
