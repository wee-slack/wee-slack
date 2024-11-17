from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Callable, Dict, List, Optional, Union

if TYPE_CHECKING:
    from slack.commands import Command
    from slack.config import SlackConfig
    from slack.error import UncaughtError
    from slack.slack_buffer import SlackBuffer
    from slack.slack_emoji import Emoji
    from slack.slack_workspace import SlackWorkspace
    from slack.task import Future, Task

WeechatCallbackReturnType = Union[int, str, Dict[str, str], None]

MESSAGE_ID_REGEX_STRING = r"(?P<msg_id>\d+|\$[0-9a-z]{3,})"
REACTION_CHANGE_REGEX_STRING = r"(?P<reaction_change>\+|-)"

EMOJI_CHAR_REGEX_STRING = "(?P<emoji_char>[\U00000080-\U0010ffff]+)"
EMOJI_NAME_REGEX_STRING = (
    ":(?P<emoji_name>[a-z0-9_+-]+(?:::skin-tone-[2-6](?:-[2-6])?)?):"
)
EMOJI_CHAR_OR_NAME_REGEX_STRING = (
    f"(?:{EMOJI_CHAR_REGEX_STRING}|{EMOJI_NAME_REGEX_STRING})"
)


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
        self.current_buffer_pointer: str
        self.config: SlackConfig
        self.commands: Dict[str, Command] = {}
        self.uncaught_errors: List[UncaughtError] = []
        self.standard_emojis: Dict[str, Emoji]
        self.standard_emojis_inverse: Dict[str, Emoji]
        self.highlight_tag = "highlight"
        self.debug_buffer_pointer: Optional[str] = None
        self.script_is_unloading = False


shared = Shared()
