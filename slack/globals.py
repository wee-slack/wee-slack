from typing import Any, Dict, Tuple

from api import SlackWorkspace
from config import SlackConfig
from task import Task

SCRIPT_NAME = "slack"
SCRIPT_AUTHOR = "Trygve Aaberge <trygveaa@gmail.com>"
SCRIPT_VERSION = "3.0.0"
SCRIPT_LICENSE = "MIT"
SCRIPT_DESC = "Extends weechat for typing notification/search/etc on slack.com"
REPO_URL = "https://github.com/wee-slack/wee-slack"

weechat_version: int
active_tasks: Dict[str, Task[Any]] = {}
active_responses: Dict[str, Tuple[Any, ...]] = {}
workspaces: Dict[str, SlackWorkspace] = {}
config: SlackConfig
