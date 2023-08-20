from __future__ import annotations

import re
from enum import Enum
from typing import TYPE_CHECKING, List, Match, Optional

from slack.log import print_exception_once
from slack.python_compatibility import removeprefix
from slack.shared import shared
from slack.slack_user import format_bot_nick
from slack.task import gather
from slack.util import with_color

if TYPE_CHECKING:
    from slack_api.slack_conversations_history import SlackMessage as SlackMessageDict

    from slack.slack_conversation import SlackConversation
    from slack.slack_workspace import SlackWorkspace


class MessagePriority(Enum):
    LOW = 0
    MESSAGE = 1
    PRIVATE = 2
    HIGHLIGHT = 3


class SlackTs(str):
    def __init__(self, ts: str):
        self.major, self.minor = [int(x) for x in ts.split(".", 1)]

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SlackTs):
            return False
        return self.major == other.major and self.minor == other.minor

    def __hash__(self) -> int:
        return hash((self.major, self.minor))

    def __repr__(self) -> str:
        return f"SlackTs('{self}')"


class SlackMessage:
    def __init__(self, conversation: SlackConversation, message_json: SlackMessageDict):
        self._message_json = message_json
        self._rendered = None
        self.conversation = conversation
        self.ts = SlackTs(message_json["ts"])

    @property
    def workspace(self) -> SlackWorkspace:
        return self.conversation.workspace

    @property
    def is_bot_message(self) -> bool:
        return (
            "subtype" in self._message_json
            and self._message_json["subtype"] == "bot_message"
        )

    @property
    def sender_user_id(self) -> Optional[str]:
        if not self.is_bot_message:
            return self._message_json.get("user")

    @property
    def sender_bot_id(self) -> Optional[str]:
        if self.is_bot_message:
            return self._message_json.get("bot_id")

    @property
    def priority(self) -> MessagePriority:
        return MessagePriority.MESSAGE

    async def tags(self, backlog: bool = False) -> str:
        nick = await self._prefix(colorize=False, only_nick=True)
        tags = ["slack_privmsg", f"slack_ts_{self.ts}", f"nick_{nick}"]

        if self.sender_user_id:
            user_or_bot = await self.workspace.users[self.sender_user_id]
        elif self.sender_bot_id:
            user_or_bot = await self.workspace.bots[self.sender_bot_id]
        else:
            user_or_bot = None

        if user_or_bot and shared.weechat_version >= 0x04000000:
            tags.append(f"prefix_nick_{user_or_bot.nick_color()}")

        if self.is_bot_message:
            tags.append("bot_message")
        if self.sender_user_id:
            tags.append(f"slack_user_id_{self.sender_user_id}")
        if self.sender_bot_id:
            tags.append(f"slack_bot_id_{self.sender_bot_id}")

        if backlog:
            tags += ["no_highlight", "notify_none", "logger_backlog", "no_log"]
        else:
            tags += ["notify_message", "log1"]

        return ",".join(tags)

    async def render(self) -> str:
        if self._rendered is not None:
            return self._rendered

        prefix_coro = self._prefix()
        message_coro = self._unfurl_refs(self._message_json["text"])
        prefix, message = await gather(prefix_coro, message_coro)
        self._rendered = f"{prefix}\t{message}"
        return self._rendered

    async def _prefix(self, colorize: bool = True, only_nick: bool = False) -> str:
        if (
            "subtype" in self._message_json
            and self._message_json["subtype"] == "bot_message"
        ):
            username = self._message_json.get("username")
            if username:
                return format_bot_nick(username, colorize=colorize, only_nick=only_nick)
            else:
                bot = await self.workspace.bots[self._message_json["bot_id"]]
                return bot.nick(colorize=colorize, only_nick=only_nick)
        else:
            user = await self.workspace.users[self._message_json["user"]]
            return user.nick(colorize=colorize, only_nick=only_nick)

    def _item_prefix(self, item_id: str):
        if item_id.startswith("#") or item_id.startswith("@"):
            return item_id[0]
        elif item_id.startswith("!subteam^") or item_id in [
            "!here",
            "!channel",
            "!everyone",
        ]:
            return "@"
        else:
            return ""

    async def _lookup_item_id(self, item_id: str):
        if item_id.startswith("#"):
            conversation = await self.workspace.conversations[
                removeprefix(item_id, "#")
            ]
            color = shared.config.color.channel_mention_color.value
            name = conversation.name_prefix("short_name") + await conversation.name()
            return (color, name)
        elif item_id.startswith("@"):
            user = await self.workspace.users[removeprefix(item_id, "@")]
            color = shared.config.color.user_mention_color.value
            return (color, self._item_prefix(item_id) + user.nick())
        elif item_id.startswith("!subteam^"):
            usergroup = await self.workspace.usergroups[
                removeprefix(item_id, "!subteam^")
            ]
            color = shared.config.color.usergroup_mention_color.value
            return (color, self._item_prefix(item_id) + usergroup.handle())
        elif item_id in ["!here", "!channel", "!everyone"]:
            color = shared.config.color.usergroup_mention_color.value
            return (color, self._item_prefix(item_id) + removeprefix(item_id, "!"))

    async def _unfurl_refs(self, message: str) -> str:
        re_mention = re.compile(r"<(?P<id>[^|>]+)(?:\|(?P<fallback_name>[^>]*))?>")
        mention_matches = list(re_mention.finditer(message))
        mention_ids: List[str] = [match["id"] for match in mention_matches]
        items_list = await gather(
            *(self._lookup_item_id(mention_id) for mention_id in mention_ids),
            return_exceptions=True,
        )
        items = dict(zip(mention_ids, items_list))

        def unfurl_ref(match: Match[str]):
            item = items[match["id"]]
            if item and not isinstance(item, BaseException):
                return with_color(item[0], item[1])
            elif match["fallback_name"]:
                prefix = self._item_prefix(match["id"])
                if match["fallback_name"].startswith(prefix):
                    return match["fallback_name"]
                else:
                    return prefix + match["fallback_name"]
            elif item:
                print_exception_once(item)
            return match[0]

        return re_mention.sub(unfurl_ref, message)
