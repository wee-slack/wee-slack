from __future__ import annotations

import json
import socket
import ssl
import time
from typing import Any, Dict, Generic, Type, TypeVar

import weechat
from websocket import ABNF, WebSocketConnectionClosedException, create_connection

from slack.proxy import Proxy
from slack.shared import shared
from slack.slack_api import SlackApi
from slack.slack_conversation import SlackConversation
from slack.slack_user import SlackBot, SlackUser
from slack.task import Future, create_task
from slack.util import get_callback_name

SlackUserOrBot = TypeVar("SlackUserOrBot", SlackUser, SlackBot)


class SlackUsersOrBots(Generic[SlackUserOrBot], Dict[str, Future[SlackUserOrBot]]):
    def __init__(self, workspace: SlackWorkspace, item_class: Type[SlackUserOrBot]):
        super().__init__()
        self.workspace = workspace
        self.item_class = item_class

    def __missing__(self, key: str):
        self[key] = create_task(self._create_item(key))
        return self[key]

    async def _create_item(self, item_id: str) -> SlackUserOrBot:
        item = self.item_class(self.workspace, item_id)
        await item.init()
        return item


class SlackWorkspace:
    def __init__(self, name: str):
        self.name = name
        self.config = shared.config.create_workspace_config(self.name)
        self.api = SlackApi(self)
        self.is_connected = False
        self.users = SlackUsersOrBots(self, SlackUser)
        self.bots = SlackUsersOrBots(self, SlackBot)
        self.conversations: Dict[str, SlackConversation] = {}

    def __setattr__(self, __name: str, __value: Any) -> None:
        super().__setattr__(__name, __value)

        if __name == "is_connected":
            weechat.bar_item_update("input_text")

    async def connect(self):
        rtm_connect = await self.api.fetch_rtm_connect()
        if rtm_connect["ok"] is False:
            # TODO: Handle error
            raise Exception("Failed fetching rtm.connect")

        self.id = rtm_connect["team"]["id"]
        self.my_user = await self.users[rtm_connect["self"]["id"]]

        await self.connect_ws(rtm_connect["url"])

        # "types": "public_channel,private_channel,im",
        user_channels_response = await self.api.fetch_users_conversations(
            "public_channel"
        )
        if user_channels_response["ok"] is False:
            # TODO: Handle error
            raise Exception("Failed fetching conversations")

        user_channels = user_channels_response["channels"]

        for channel in user_channels:
            conversation = SlackConversation(self, channel["id"])
            self.conversations[channel["id"]] = conversation
            create_task(conversation.init())

        self.is_connected = True

    async def connect_ws(self, url: str):
        sslopt_ca_certs = {}
        if hasattr(ssl, "get_default_verify_paths") and callable(
            ssl.get_default_verify_paths
        ):
            ssl_defaults = ssl.get_default_verify_paths()
            if ssl_defaults.cafile is not None:
                sslopt_ca_certs = {"ca_certs": ssl_defaults.cafile}

        proxy = Proxy()
        proxy_options = {
            "proxy_type": proxy.type,
            "http_proxy_host": proxy.address,
            "http_proxy_port": proxy.port,
            "http_proxy_auth": (proxy.username, proxy.password),
            "http_proxy_timeout": self.config.network_timeout.value,
        }
        # TODO: Handle errors
        self.ws = create_connection(
            url,
            self.config.network_timeout.value,
            sslopt=sslopt_ca_certs,
            **proxy_options,
        )

        self.hook = weechat.hook_fd(
            self.ws.sock.fileno(),
            1,
            0,
            0,
            get_callback_name(self.ws_read_cb),
            "",
        )
        self.ws.sock.setblocking(False)

    def ws_read_cb(self, data: str, fd: int) -> int:
        while True:
            try:
                opcode, recv_data = self.ws.recv_data(control_frame=True)
            except ssl.SSLWantReadError:
                # No more data to read at this time.
                return weechat.WEECHAT_RC_OK
            except (WebSocketConnectionClosedException, socket.error) as e:
                # TODO: Handle error
                # handle_socket_error(e, team, "receive")
                print(e)
                return weechat.WEECHAT_RC_OK

            if opcode == ABNF.OPCODE_PONG:
                # TODO: Maybe record last time anything was received instead
                self.last_pong_time = time.time()
                return weechat.WEECHAT_RC_OK
            elif opcode != ABNF.OPCODE_TEXT:
                return weechat.WEECHAT_RC_OK

            self.ws_recv(json.loads(recv_data.decode()))

    def ws_recv(self, data: Any):
        print(f"received: {data}")