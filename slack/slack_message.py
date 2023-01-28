from __future__ import annotations

import re
from typing import TYPE_CHECKING, List, Optional

from slack.slack_user import SlackUser, format_bot_nick
from slack.task import gather

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

    async def _unfurl_refs(self, message: str) -> str:
        re_user = re.compile("<@([^>]+)>")
        user_ids: List[str] = re_user.findall(message)
        users_list = await gather(
            *(self.workspace.users[user_id] for user_id in user_ids),
            return_exceptions=True,
        )
        users = dict(zip(user_ids, users_list))

        def unfurl_user(user_id: str):
            user = users[user_id]
            return "@" + user.nick() if isinstance(user, SlackUser) else f"@{user_id}"

        return re_user.sub(lambda match: unfurl_user(match.group(1)), message)
