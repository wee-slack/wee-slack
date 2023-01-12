from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Any, Dict, List

if TYPE_CHECKING:
    from slack.api import SlackWorkspace
    from slack.config import SlackConfig
    from slack.task import Future, Task


class Shared:
    def __init__(self):
        self.SCRIPT_NAME = "slack"
        self.SCRIPT_VERSION = "3.0.0"

        self.weechat_version: int
        self.weechat_callbacks: Dict[str, Any]
        self.active_tasks: Dict[str, List[Task[Any]]] = defaultdict(list)
        self.active_futures: Dict[str, Future[Any]] = {}
        self.workspaces: Dict[str, SlackWorkspace] = {}
        self.config: SlackConfig


shared = Shared()
