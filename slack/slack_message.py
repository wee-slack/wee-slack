from __future__ import annotations

import re
from typing import TYPE_CHECKING, List, Match, Optional

from slack.log import print_exception_once
from slack.python_compatibility import removeprefix
from slack.shared import shared
from slack.slack_user import SlackUser, SlackUsergroup, format_bot_nick
from slack.task import gather
from slack.util import with_color

if TYPE_CHECKING:
    from slack_api.slack_conversations_history import SlackMessage as SlackMessageDict

    from slack.slack_conversation import SlackConversation
    from slack.slack_workspace import SlackWorkspace


class SlackMessage:
    def __init__(self, conversation: SlackConversation, message_json: SlackMessageDict):
        self._message_json = message_json
        self.conversation = conversation
        self.ts = message_json["ts"]

    @property
    def workspace(self) -> SlackWorkspace:
        return self.conversation.workspace

    @property
    def sender_user_id(self) -> Optional[str]:
        return self._message_json.get("user")

    async def render_message(self) -> str:
        prefix_coro = self._prefix()
        message_coro = self._unfurl_refs(self._message_json["text"])
        prefix, message = await gather(prefix_coro, message_coro)
        return f"{prefix}\t{message}"

    async def _prefix(self) -> str:
        if (
            "subtype" in self._message_json
            and self._message_json["subtype"] == "bot_message"
        ):
            username = self._message_json.get("username")
            if username:
                return format_bot_nick(username, colorize=True)
            else:
                bot = await self.workspace.bots[self._message_json["bot_id"]]
                return bot.nick(colorize=True)
        else:
            user = await self.workspace.users[self._message_json["user"]]
            return user.nick(colorize=True)

    async def _lookup_item_id(self, item_id: str):
        if item_id.startswith("@"):
            return await self.workspace.users[removeprefix(item_id, "@")]
        elif item_id.startswith("!subteam^"):
            return await self.workspace.usergroups[removeprefix(item_id, "!subteam^")]

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
            if isinstance(item, SlackUser):
                return with_color(
                    shared.config.color.user_mention_color.value, "@" + item.nick()
                )
            elif isinstance(item, SlackUsergroup):
                return with_color(
                    shared.config.color.usergroup_mention_color.value,
                    "@" + item.handle(),
                )
            elif match["fallback_name"]:
                return match["fallback_name"]
            elif item:
                print_exception_once(item)
            return match[0]

        return re_mention.sub(unfurl_ref, message)
