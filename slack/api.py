from __future__ import annotations

import json
from typing import TYPE_CHECKING, Dict, Union
from urllib.parse import urlencode

from slack.http import http_request
from slack.shared import shared

if TYPE_CHECKING:
    from slack_api import SlackConversation, SlackConversationIm, SlackConversationNotIm


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


class SlackWorkspace:
    def __init__(self, name: str):
        self.name = name
        self.config = shared.config.create_workspace_config(self.name)
        self.api = SlackApi(self)


class SlackChannelCommonNew:
    def __init__(self, workspace: SlackWorkspace, slack_info: SlackConversation):
        self.workspace = workspace
        self.api = workspace.api
        self.id = slack_info["id"]
        # self.fetch_info()

    async def fetch_info(self):
        response = await self.api.fetch("conversations.info", {"channel": self.id})
        print(len(response))


class SlackChannelNew(SlackChannelCommonNew):
    def __init__(self, workspace: SlackWorkspace, slack_info: SlackConversationNotIm):
        super().__init__(workspace, slack_info)
        self.name = slack_info["name"]


class SlackIm(SlackChannelCommonNew):
    def __init__(self, workspace: SlackWorkspace, slack_info: SlackConversationIm):
        super().__init__(workspace, slack_info)
        self.user = slack_info["user"]
