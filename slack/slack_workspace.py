from __future__ import annotations

import json
from typing import Dict, Union
from urllib.parse import urlencode

import weechat

from slack.http import http_request
from slack.shared import shared
from slack.slack_conversation import SlackConversation
from slack.slack_user import SlackUser
from slack.task import Future, create_task


class SlackApi:
    def __init__(self, workspace: SlackWorkspace):
        self.workspace = workspace

    def get_request_options(self):
        return {
            "useragent": f"wee_slack {shared.SCRIPT_VERSION}",
            "httpheader": f"Authorization: Bearer {self.workspace.config.api_token.value}",
            "cookie": self.workspace.config.api_cookies.value,
        }

    async def fetch(self, method: str, params: Dict[str, Union[str, int]] = {}):
        url = f"https://api.slack.com/api/{method}?{urlencode(params)}"
        response = await http_request(
            url,
            self.get_request_options(),
            self.workspace.config.slack_timeout.value * 1000,
        )
        return json.loads(response)

    async def fetch_list(
        self,
        method: str,
        list_key: str,
        params: Dict[str, Union[str, int]] = {},
        pages: int = 1,  # negative or 0 means all pages
    ):
        response = await self.fetch(method, params)
        next_cursor = response.get("response_metadata", {}).get("next_cursor")
        if pages != 1 and next_cursor and response["ok"]:
            params["cursor"] = next_cursor
            next_pages = await self.fetch_list(method, list_key, params, pages - 1)
            response[list_key].extend(next_pages[list_key])
            return response
        return response


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
        user_channels_response = await self.api.fetch_list(
            "users.conversations",
            "channels",
            {
                "exclude_archived": True,
                # "types": "public_channel,private_channel,im",
                "types": "public_channel",
                "limit": 1000,
            },
            -1,
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
