from __future__ import annotations

import json
import re
import time
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union
from urllib.parse import urlencode

import weechat

from slack.http import http_request
from slack.shared import shared
from slack.task import Future, create_task, gather
from slack.util import get_callback_name

if TYPE_CHECKING:
    from slack_api import (
        SlackConversationIm,
        SlackConversationInfo,
        SlackConversationNotIm,
    )


def get_conversation_from_buffer_pointer(
    buffer_pointer: str,
) -> Optional[SlackConversation]:
    for workspace in shared.workspaces.values():
        for conversation in workspace.conversations.values():
            if conversation.buffer_pointer == buffer_pointer:
                return conversation


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
        self.is_connected = False
        self.nick = "TODO"
        # Maybe make private, so you have to use get_user? Maybe make get_user a getter, though don't know if that's a problem since it's async
        self.users: Dict[str, Future[SlackUser]] = {}
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

    async def create_user(self, id: str) -> SlackUser:
        user = SlackUser(self, id)
        await user.init()
        return user

    async def get_user(self, id: str) -> SlackUser:
        if id in self.users:
            return await self.users[id]
        self.users[id] = create_task(self.create_user(id))
        return await self.users[id]


class SlackUser:
    def __init__(self, workspace: SlackWorkspace, id: str):
        self.workspace = workspace
        self.id = id
        self.name: str

    @property
    def api(self) -> SlackApi:
        return self.workspace.api

    async def init(self):
        info = await self.api.fetch("users.info", {"user": self.id})
        self.name = info["user"]["name"]


def buffer_input_cb(data: str, buffer: str, input_data: str) -> int:
    weechat.prnt(buffer, "Text: %s" % input_data)
    return weechat.WEECHAT_RC_OK


class SlackConversation:
    def __init__(self, workspace: SlackWorkspace, id: str):
        self.workspace = workspace
        self.id = id
        # TODO: buffer_pointer may be accessed by buffer_switch before it's initialized
        self.buffer_pointer: str = ""
        self.name: str
        self.is_loading = False
        self.history_filled = False
        self.history_pending = False

    @property
    def api(self) -> SlackApi:
        return self.workspace.api

    @contextmanager
    def loading(self):
        self.is_loading = True
        weechat.bar_item_update("input_text")
        try:
            yield
        finally:
            self.is_loading = False
            weechat.bar_item_update("input_text")

    async def init(self):
        with self.loading():
            info = await self.fetch_info()
        self.name = info["channel"]["name"]
        self.buffer_pointer = weechat.buffer_new(
            self.name, get_callback_name(buffer_input_cb), "", "", ""
        )
        weechat.buffer_set(self.buffer_pointer, "localvar_set_nick", "nick")

    async def fetch_info(self):
        with self.loading():
            info = await self.api.fetch("conversations.info", {"channel": self.id})
        return info

    async def fill_history(self):
        if self.history_filled or self.history_pending:
            return

        with self.loading():
            self.history_pending = True

            history = await self.api.fetch(
                "conversations.history", {"channel": self.id}
            )
            start = time.time()

            messages = [SlackMessage(self, message) for message in history["messages"]]
            messages_rendered = await gather(
                *(message.render_message() for message in messages)
            )

            for rendered in reversed(messages_rendered):
                weechat.prnt(self.buffer_pointer, rendered)

            print(f"history w/o fetch took: {time.time() - start}")
            self.history_filled = True
            self.history_pending = False


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
