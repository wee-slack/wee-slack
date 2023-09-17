from __future__ import annotations

import json
import socket
import ssl
import time
from abc import ABC, abstractmethod
from typing import (
    TYPE_CHECKING,
    Dict,
    Generic,
    Iterable,
    List,
    Optional,
    Tuple,
    Type,
    TypeVar,
)

import weechat
from websocket import (
    ABNF,
    WebSocket,
    WebSocketConnectionClosedException,
    create_connection,
)

from slack.error import (
    SlackApiError,
    SlackError,
    SlackRtmError,
    store_and_format_exception,
)
from slack.log import print_error
from slack.proxy import Proxy
from slack.shared import shared
from slack.slack_api import SlackApi
from slack.slack_buffer import SlackBuffer
from slack.slack_conversation import SlackConversation
from slack.slack_message import SlackMessage, SlackTs
from slack.slack_thread import SlackThread
from slack.slack_user import SlackBot, SlackUser, SlackUsergroup
from slack.task import Future, Task, create_task, gather, run_async
from slack.util import get_callback_name

if TYPE_CHECKING:
    from slack_api.slack_bots_info import SlackBotInfo
    from slack_api.slack_conversations_info import SlackConversationsInfo
    from slack_api.slack_usergroups_info import SlackUsergroupInfo
    from slack_api.slack_users_info import SlackUserInfo
    from slack_rtm.slack_rtm_message import SlackRtmMessage
else:
    SlackBotInfo = object
    SlackConversationsInfo = object
    SlackUsergroupInfo = object
    SlackUserInfo = object

SlackItemClass = TypeVar(
    "SlackItemClass", SlackConversation, SlackUser, SlackBot, SlackUsergroup
)
SlackItemInfo = TypeVar(
    "SlackItemInfo",
    SlackConversationsInfo,
    SlackUserInfo,
    SlackBotInfo,
    SlackUsergroupInfo,
)


class SlackItem(
    ABC, Generic[SlackItemClass, SlackItemInfo], Dict[str, Future[SlackItemClass]]
):
    def __init__(self, workspace: SlackWorkspace, item_class: Type[SlackItemClass]):
        super().__init__()
        self.workspace = workspace
        self._item_class = item_class

    def __missing__(self, key: str):
        self[key] = create_task(self._create_item(key))
        return self[key]

    def initialize_items(self, item_ids: Iterable[str]):
        item_ids_to_init = set(item_id for item_id in item_ids if item_id not in self)
        if item_ids_to_init:
            items_info_task = create_task(self._fetch_items_info(item_ids_to_init))
            for item_id in item_ids_to_init:
                self[item_id] = create_task(self._create_item(item_id, items_info_task))

    async def _create_item(
        self,
        item_id: str,
        items_info_task: Optional[Future[Dict[str, SlackItemInfo]]] = None,
    ) -> SlackItemClass:
        if items_info_task:
            items_info = await items_info_task
            return self._create_item_from_info(items_info[item_id])
        else:
            return await self._item_class.create(self.workspace, item_id)

    @abstractmethod
    async def _fetch_items_info(
        self, item_ids: Iterable[str]
    ) -> Dict[str, SlackItemInfo]:
        raise NotImplementedError()

    @abstractmethod
    def _create_item_from_info(self, item_info: SlackItemInfo) -> SlackItemClass:
        raise NotImplementedError()


class SlackConversations(SlackItem[SlackConversation, SlackConversationsInfo]):
    def __init__(self, workspace: SlackWorkspace):
        super().__init__(workspace, SlackConversation)

    async def _fetch_items_info(
        self, item_ids: Iterable[str]
    ) -> Dict[str, SlackConversationsInfo]:
        responses = await gather(
            *(
                self.workspace.api.fetch_conversations_info(item_id)
                for item_id in item_ids
            )
        )
        return {
            response["channel"]["id"]: response["channel"] for response in responses
        }

    def _create_item_from_info(
        self, item_info: SlackConversationsInfo
    ) -> SlackConversation:
        return self._item_class(self.workspace, item_info)


class SlackUsers(SlackItem[SlackUser, SlackUserInfo]):
    def __init__(self, workspace: SlackWorkspace):
        super().__init__(workspace, SlackUser)

    async def _fetch_items_info(
        self, item_ids: Iterable[str]
    ) -> Dict[str, SlackUserInfo]:
        response = await self.workspace.api.fetch_users_info(item_ids)
        return {info["id"]: info for info in response["users"]}

    def _create_item_from_info(self, item_info: SlackUserInfo) -> SlackUser:
        return self._item_class(self.workspace, item_info)


class SlackBots(SlackItem[SlackBot, SlackBotInfo]):
    def __init__(self, workspace: SlackWorkspace):
        super().__init__(workspace, SlackBot)

    async def _fetch_items_info(
        self, item_ids: Iterable[str]
    ) -> Dict[str, SlackBotInfo]:
        response = await self.workspace.api.fetch_bots_info(item_ids)
        return {info["id"]: info for info in response["bots"]}

    def _create_item_from_info(self, item_info: SlackBotInfo) -> SlackBot:
        return self._item_class(self.workspace, item_info)


class SlackUsergroups(SlackItem[SlackUsergroup, SlackUsergroupInfo]):
    def __init__(self, workspace: SlackWorkspace):
        super().__init__(workspace, SlackUsergroup)

    async def _fetch_items_info(
        self, item_ids: Iterable[str]
    ) -> Dict[str, SlackUsergroupInfo]:
        response = await self.workspace.api.edgeapi.fetch_usergroups_info(
            list(item_ids)
        )
        return {info["id"]: info for info in response["results"]}

    def _create_item_from_info(self, item_info: SlackUsergroupInfo) -> SlackUsergroup:
        return self._item_class(self.workspace, item_info)


class SlackWorkspace:
    def __init__(self, name: str):
        self.name = name
        self.config = shared.config.create_workspace_config(self.name)
        self.api = SlackApi(self)
        self._is_connected = False
        self._connect_task: Optional[Task[None]] = None
        self._ws: Optional[WebSocket] = None
        self._hook_ws_fd: Optional[str] = None
        self._ws_messages: List[Tuple[float, SlackRtmMessage]] = []
        self._debug_ws_buffer_pointer: Optional[str] = None
        self.conversations = SlackConversations(self)
        self.open_conversations: Dict[str, SlackConversation] = {}
        self.users = SlackUsers(self)
        self.bots = SlackBots(self)
        self.usergroups = SlackUsergroups(self)

    def __repr__(self):
        return f"{self.__class__.__name__}('{self.name}')"

    @property
    def is_connected(self):
        return self._is_connected

    @property
    def is_connecting(self):
        return self._connect_task is not None

    @is_connected.setter
    def is_connected(self, value: bool):
        self._is_connected = value
        weechat.bar_item_update("input_text")

    async def connect(self) -> None:
        if self.is_connected:
            return
        self._connect_task = create_task(self._connect())
        await self._connect_task
        self._connect_task = None

    async def _connect(self) -> None:
        try:
            rtm_connect = await self.api.fetch_rtm_connect()
        except SlackApiError as e:
            print_error(
                f'failed connecting to workspace "{self.name}": {e.response["error"]}'
            )
            return

        self.id = rtm_connect["team"]["id"]
        self.enterprise_id = rtm_connect["team"].get("enterprise_id")
        self.my_user = await self.users[rtm_connect["self"]["id"]]

        await self._connect_ws(rtm_connect["url"])

        if not self.api.edgeapi.is_available:
            usergroups = await self.api.fetch_usergroups_list()
            for usergroup in usergroups["usergroups"]:
                future = Future[SlackUsergroup]()
                future.set_result(SlackUsergroup(self, usergroup))
                self.usergroups[usergroup["id"]] = future

        users_conversations_response = await self.api.fetch_users_conversations(
            "public_channel,private_channel,mpim,im"
        )
        channels = users_conversations_response["channels"]
        self.conversations.initialize_items(channel["id"] for channel in channels)
        for channel in channels:
            conversation = await self.conversations[channel["id"]]
            run_async(conversation.open_if_open())

        self.is_connected = True

    async def _connect_ws(self, url: str):
        proxy = Proxy()
        # TODO: Handle errors
        self._ws = create_connection(
            url,
            self.config.network_timeout.value,
            proxy_type=proxy.type,
            http_proxy_host=proxy.address,
            http_proxy_port=proxy.port,
            http_proxy_auth=(proxy.username, proxy.password),
            http_proxy_timeout=self.config.network_timeout.value,
        )

        self._hook_ws_fd = weechat.hook_fd(
            self._ws.sock.fileno(),
            1,
            0,
            0,
            get_callback_name(self._ws_read_cb),
            "",
        )
        self._ws.sock.setblocking(False)

    def _ws_read_cb(self, data: str, fd: int) -> int:
        if self._ws is None:
            raise SlackError(self, "ws_read_cb called while _ws is None")
        while True:
            try:
                opcode, recv_data = self._ws.recv_data(control_frame=True)
            except ssl.SSLWantReadError:
                # No more data to read at this time.
                return weechat.WEECHAT_RC_OK
            except (WebSocketConnectionClosedException, socket.error):
                print("lost connection on receive, reconnecting")
                run_async(self.reconnect())
                return weechat.WEECHAT_RC_OK

            if opcode == ABNF.OPCODE_PONG:
                # TODO: Maybe record last time anything was received instead
                self.last_pong_time = time.time()
                return weechat.WEECHAT_RC_OK
            elif opcode != ABNF.OPCODE_TEXT:
                return weechat.WEECHAT_RC_OK

            run_async(self._ws_recv(json.loads(recv_data.decode())))

    async def _ws_recv(self, data: SlackRtmMessage):
        epoch = time.time()
        # TODO: Remove old messages
        self._ws_messages.append((epoch, data))
        self.print_debug_ws_buffer(epoch, data)

        try:
            if data["type"] == "hello":
                return
            elif data["type"] == "reaction_added" or data["type"] == "reaction_removed":
                channel_id = data["item"]["channel"]
            elif data["type"] == "sh_room_join" or data["type"] == "sh_room_update":
                channel_id = data["huddle"]["channel_id"]
            elif "channel" in data and type(data["channel"]) == str:
                channel_id = data["channel"]
            else:
                weechat.prnt("", f"\t{self.name} received: {json.dumps(data)}")
                return

            channel = self.open_conversations.get(channel_id)
            if channel is None:
                weechat.prnt(
                    "",
                    f"\t{self.name} received for not open conversation, discarding: {json.dumps(data)}",
                )
                return

            if data["type"] == "message":
                if "subtype" in data and data["subtype"] == "message_changed":
                    await channel.change_message(data)
                elif "subtype" in data and data["subtype"] == "message_deleted":
                    await channel.delete_message(data)
                elif "subtype" in data and data["subtype"] == "message_replied":
                    await channel.change_message(data)
                else:
                    message = SlackMessage(channel, data)
                    await channel.add_new_message(message)
            elif data["type"] == "reaction_added" and data["item"]["type"] == "message":
                await channel.reaction_add(
                    SlackTs(data["item"]["ts"]), data["reaction"], data["user"]
                )
            elif (
                data["type"] == "reaction_removed" and data["item"]["type"] == "message"
            ):
                await channel.reaction_remove(
                    SlackTs(data["item"]["ts"]), data["reaction"], data["user"]
                )
            elif data["type"] == "sh_room_join" or data["type"] == "sh_room_update":
                await channel.update_message_room(data)
            elif data["type"] == "user_typing":
                await channel.typing_add_user(data)
            else:
                weechat.prnt("", f"\t{self.name} received: {json.dumps(data)}")
        except Exception as e:
            slack_error = SlackRtmError(self, e, data)
            print_error(store_and_format_exception(slack_error))

    def ping(self):
        if not self.is_connected:
            raise SlackError(self, "Can't ping when not connected")
        if self._ws is None:
            raise SlackError(self, "is_connected is True while _ws is None")
        try:
            self._ws.ping()
            # workspace.last_ping_time = time.time()
        except (WebSocketConnectionClosedException, socket.error):
            print("lost connection on ping, reconnecting")
            run_async(self.reconnect())

    def send_typing(self, buffer: SlackBuffer):
        if not self.is_connected:
            raise SlackError(self, "Can't send typing when not connected")
        if self._ws is None:
            raise SlackError(self, "is_connected is True while _ws is None")

        if isinstance(buffer, SlackConversation):
            conversation_id = buffer.id
        elif isinstance(buffer, SlackThread):
            conversation_id = buffer.parent.conversation.id
        else:
            raise NotImplementedError(f"Unknown buffer type: {type(buffer)}")

        msg = {
            "type": "user_typing",
            "channel": conversation_id,
        }
        if isinstance(buffer, SlackThread):
            msg["thread_ts"] = buffer.parent.ts
        self._ws.send(json.dumps(msg))

    def _close_debug_ws_buffer_cb(self, data: str, buffer: str):
        self._debug_ws_buffer_pointer = None
        return weechat.WEECHAT_RC_OK

    def open_debug_ws_buffer(self):
        if self._debug_ws_buffer_pointer:
            weechat.buffer_set(self._debug_ws_buffer_pointer, "display", "1")
            return

        name = f"{shared.SCRIPT_NAME}.debug.ws.{self.name}"
        self._debug_ws_buffer_pointer = weechat.buffer_new_props(
            name,
            {"display": "1"},
            "",
            "",
            get_callback_name(self._close_debug_ws_buffer_cb),
            "",
        )
        for epoch, message in self._ws_messages:
            self.print_debug_ws_buffer(epoch, message)

    def print_debug_ws_buffer(self, epoch: float, message: SlackRtmMessage):
        if self._debug_ws_buffer_pointer:
            weechat.prnt_date_tags(
                self._debug_ws_buffer_pointer, int(epoch), "", json.dumps(message)
            )

    async def reconnect(self):
        self.disconnect()
        await self.connect()

    def disconnect(self):
        self.is_connected = False

        if self._connect_task:
            self._connect_task.cancel()

        if self._hook_ws_fd:
            weechat.unhook(self._hook_ws_fd)
            self._hook_ws_fd = None

        if self._ws:
            self._ws.close()
            self._ws = None
