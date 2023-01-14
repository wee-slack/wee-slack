from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, List

from slack.task import gather

if TYPE_CHECKING:
    from slack.slack_conversation import SlackConversation
    from slack.slack_workspace import SlackApi, SlackWorkspace


class SlackMessage:
    def __init__(self, conversation: SlackConversation, message_json: Any):
        self.conversation = conversation
        self.ts = message_json["ts"]
        self.message_json = message_json

    @property
    def workspace(self) -> SlackWorkspace:
        return self.conversation.workspace

    @property
    def api(self) -> SlackApi:
        return self.workspace.api

    async def render_message(self):
        message = await self.unfurl_refs(self.message_json["text"])
        if "user" in self.message_json:
            user = await self.workspace.get_user(self.message_json["user"])
            prefix = user.name
        else:
            prefix = "bot"

        return f"{prefix}\t{message}"

    async def unfurl_refs(self, message: str):
        re_user = re.compile("<@([^>]+)>")
        user_ids: List[str] = re_user.findall(message)
        users_list = await gather(
            *(self.workspace.get_user(user_id) for user_id in user_ids)
        )
        users = dict(zip(user_ids, users_list))

        def unfurl_user(user_id: str):
            return "@" + users[user_id].name

        return re_user.sub(lambda match: unfurl_user(match.group(1)), message)
