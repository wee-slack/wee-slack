from __future__ import annotations

from typing import Dict

import weechat

from slack.shared import shared
from slack.slack_api import SlackApi
from slack.slack_conversation import SlackConversation
from slack.slack_user import SlackUser
from slack.task import Future, create_task


class SlackUsers(Dict[str, Future[SlackUser]]):
    def __init__(self, workspace: SlackWorkspace):
        super().__init__()
        self.workspace = workspace

    def __missing__(self, key: str):
        self[key] = create_task(self._create_user(key))
        return self[key]

    async def _create_user(self, user_id: str) -> SlackUser:
        user = SlackUser(self.workspace, user_id)
        await user.init()
        return user


class SlackWorkspace:
    def __init__(self, name: str):
        self.name = name
        self.config = shared.config.create_workspace_config(self.name)
        self.api = SlackApi(self)
        self.is_connected = False
        self.nick = "TODO"
        self.users = SlackUsers(self)
        self.conversations: Dict[str, SlackConversation] = {}

    async def connect(self):
        # rtm_connect = await self.api.fetch("rtm.connect")
        # "types": "public_channel,private_channel,im",
        user_channels_response = await self.api.fetch_users_conversations(
            "public_channel"
        )
        user_channels = user_channels_response["channels"]

        for channel in user_channels:
            conversation = SlackConversation(self, channel["id"])
            self.conversations[channel["id"]] = conversation
            create_task(conversation.init())

        # print(rtm_connect)
        # print([c["name"] for c in user_channels])
        self.is_connected = True
        weechat.bar_item_update("input_text")
