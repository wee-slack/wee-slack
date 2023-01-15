from __future__ import annotations

import json
from typing import TYPE_CHECKING, Dict, Union
from urllib.parse import urlencode

from slack.http import http_request
from slack.shared import shared

if TYPE_CHECKING:
    from slack_api.slack_bots_info import SlackBotInfoResponse
    from slack_api.slack_conversations_history import SlackConversationsHistoryResponse
    from slack_api.slack_conversations_info import SlackConversationsInfoResponse
    from slack_api.slack_rtm_connect import SlackRtmConnectResponse
    from slack_api.slack_users_conversations import SlackUsersConversationsResponse
    from slack_api.slack_users_info import SlackUsersInfoResponse

    from slack.slack_conversation import SlackConversation
    from slack.slack_user import SlackBot, SlackUser
    from slack.slack_workspace import SlackWorkspace


class SlackApi:
    def __init__(self, workspace: SlackWorkspace):
        self.workspace = workspace

    def _get_request_options(self):
        return {
            "useragent": f"wee_slack {shared.SCRIPT_VERSION}",
            "httpheader": f"Authorization: Bearer {self.workspace.config.api_token.value}",
            "cookie": self.workspace.config.api_cookies.value,  # TODO: url_encode_if_not_encoded
        }

    async def _fetch(self, method: str, params: Dict[str, Union[str, int]] = {}):
        url = f"https://api.slack.com/api/{method}?{urlencode(params)}"
        response = await http_request(
            url,
            self._get_request_options(),
            self.workspace.config.network_timeout.value * 1000,
        )
        return json.loads(response)

    async def _fetch_list(
        self,
        method: str,
        list_key: str,
        params: Dict[str, Union[str, int]] = {},
        pages: int = -1,  # negative or 0 means all pages
    ):
        response = await self._fetch(method, params)
        next_cursor = response.get("response_metadata", {}).get("next_cursor")
        if pages != 1 and next_cursor and response["ok"]:
            params["cursor"] = next_cursor
            next_pages = await self._fetch_list(method, list_key, params, pages - 1)
            response[list_key].extend(next_pages[list_key])
            return response
        return response

    async def fetch_rtm_connect(self) -> SlackRtmConnectResponse:
        return await self._fetch("rtm.connect")

    async def fetch_conversations_history(
        self, conversation: SlackConversation
    ) -> SlackConversationsHistoryResponse:
        return await self._fetch("conversations.history", {"channel": conversation.id})

    async def fetch_conversations_info(
        self, conversation: SlackConversation
    ) -> SlackConversationsInfoResponse:
        return await self._fetch("conversations.info", {"channel": conversation.id})

    async def fetch_users_conversations(
        self,
        types: str,
        exclude_archived: bool = True,
        limit: int = 1000,
        pages: int = -1,
    ) -> SlackUsersConversationsResponse:
        return await self._fetch_list(
            "users.conversations",
            "channels",
            {
                "types": types,
                "exclude_archived": exclude_archived,
                "limit": limit,
            },
            pages,
        )

    async def fetch_users_info(self, user: SlackUser) -> SlackUsersInfoResponse:
        return await self._fetch("users.info", {"user": user.id})

    async def fetch_bots_info(self, bot: SlackBot) -> SlackBotInfoResponse:
        return await self._fetch("bots.info", {"bot": bot.id})
