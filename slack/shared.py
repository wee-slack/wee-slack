from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Callable, Dict, List, Union

if TYPE_CHECKING:
    from slack.config import SlackConfig
    from slack.error import UncaughtError
    from slack.slack_buffer import SlackBuffer
    from slack.slack_emoji import Emoji
    from slack.slack_workspace import SlackWorkspace
    from slack.task import Future, Task

WeechatCallbackReturnType = Union[int, str, Dict[str, str], None]


class Shared:
    def __init__(self):
        self.SCRIPT_NAME = "slack"
        self.SCRIPT_VERSION = "3.0.0"

        self.weechat_version: int
        self.weechat_callbacks: Dict[str, Callable[..., WeechatCallbackReturnType]]
        self.active_tasks: Dict[str, List[Task[object]]] = defaultdict(list)
        self.active_futures: Dict[str, Future[object]] = {}
        self.buffers: Dict[str, SlackBuffer] = {}
        self.workspaces: Dict[str, SlackWorkspace] = {}
        self.config: SlackConfig
        self.uncaught_errors: List[UncaughtError] = []
        self.standard_emojis: Dict[str, Emoji]


shared = Shared()
