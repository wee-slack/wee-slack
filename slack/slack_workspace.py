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
    Mapping,
    Optional,
    Set,
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
from slack.log import DebugMessageType, LogLevel, log, print_error
from slack.proxy import Proxy
from slack.shared import shared
from slack.slack_api import SlackApi
from slack.slack_buffer import SlackBuffer
from slack.slack_conversation import SlackConversation
from slack.slack_message import SlackMessage, SlackTs
from slack.slack_thread import SlackThread
from slack.slack_user import SlackBot, SlackUser, SlackUsergroup
from slack.task import Future, Task, create_task, gather, run_async
from slack.util import get_callback_name, get_cookies

if TYPE_CHECKING:
    from slack_api.slack_bots_info import SlackBotInfo
    from slack_api.slack_usergroups_info import SlackUsergroupInfo
    from slack_api.slack_users_conversations import SlackUsersConversations
    from slack_api.slack_users_info import SlackUserInfo
    from slack_rtm.slack_rtm_message import SlackRtmMessage
    from typing_extensions import Literal

    from slack.slack_conversation import SlackConversationsInfoInternal
else:
    SlackBotInfo = object
    SlackConversationsInfoInternal = object
    SlackUsergroupInfo = object
    SlackUserInfo = object

SlackItemClass = TypeVar(
    "SlackItemClass", SlackConversation, SlackUser, SlackBot, SlackUsergroup
)
SlackItemInfo = TypeVar(
    "SlackItemInfo",
    SlackConversationsInfoInternal,
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

    def initialize_items(
        self,
        item_ids: Iterable[str],
        items_info_prefetched: Optional[Mapping[str, SlackItemInfo]] = None,
    ):
        item_ids_to_init = set(item_id for item_id in item_ids if item_id not in self)
        if item_ids_to_init:
            item_ids_to_fetch = (
                set(
                    item_id
                    for item_id in item_ids_to_init
                    if item_id not in items_info_prefetched
                )
                if items_info_prefetched
                else item_ids_to_init
            )
            items_info_task = create_task(self._fetch_items_info(item_ids_to_fetch))
            for item_id in item_ids_to_init:
                self[item_id] = create_task(
                    self._create_item(item_id, items_info_task, items_info_prefetched)
                )

    async def _create_item(
        self,
        item_id: str,
        items_info_task: Optional[Future[Dict[str, SlackItemInfo]]] = None,
        items_info_prefetched: Optional[Mapping[str, SlackItemInfo]] = None,
    ) -> SlackItemClass:
        if items_info_prefetched and item_id in items_info_prefetched:
            return await self._create_item_from_info(items_info_prefetched[item_id])
        elif items_info_task:
            items_info = await items_info_task
            item = items_info.get(item_id)
            if item is None:
                raise SlackError(self.workspace, "item_not_found")
            return await self._create_item_from_info(item)
        else:
            return await self._item_class.create(self.workspace, item_id)

    @abstractmethod
    async def _fetch_items_info(
        self, item_ids: Iterable[str]
    ) -> Dict[str, SlackItemInfo]:
        raise NotImplementedError()

    @abstractmethod
    async def _create_item_from_info(self, item_info: SlackItemInfo) -> SlackItemClass:
        raise NotImplementedError()


class SlackConversations(SlackItem[SlackConversation, SlackConversationsInfoInternal]):
    def __init__(self, workspace: SlackWorkspace):
        super().__init__(workspace, SlackConversation)

    async def _fetch_items_info(
        self, item_ids: Iterable[str]
    ) -> Dict[str, SlackConversationsInfoInternal]:
        responses = await gather(
            *(
                self.workspace.api.fetch_conversations_info(item_id)
                for item_id in item_ids
            )
        )
        return {
            response["channel"]["id"]: response["channel"] for response in responses
        }

    async def _create_item_from_info(
        self, item_info: SlackConversationsInfoInternal
    ) -> SlackConversation:
        return await self._item_class(self.workspace, item_info)


class SlackUsers(SlackItem[SlackUser, SlackUserInfo]):
    def __init__(self, workspace: SlackWorkspace):
        super().__init__(workspace, SlackUser)

    async def _fetch_items_info(
        self, item_ids: Iterable[str]
    ) -> Dict[str, SlackUserInfo]:
        response = await self.workspace.api.fetch_users_info(item_ids)
        return {info["id"]: info for info in response["users"]}

    async def _create_item_from_info(self, item_info: SlackUserInfo) -> SlackUser:
        return self._item_class(self.workspace, item_info)


class SlackBots(SlackItem[SlackBot, SlackBotInfo]):
    def __init__(self, workspace: SlackWorkspace):
        super().__init__(workspace, SlackBot)

    async def _fetch_items_info(
        self, item_ids: Iterable[str]
    ) -> Dict[str, SlackBotInfo]:
        response = await self.workspace.api.fetch_bots_info(item_ids)
        return {info["id"]: info for info in response["bots"]}

    async def _create_item_from_info(self, item_info: SlackBotInfo) -> SlackBot:
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

    async def _create_item_from_info(
        self, item_info: SlackUsergroupInfo
    ) -> SlackUsergroup:
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
        self._debug_ws_buffer_pointer: Optional[str] = None
        self.conversations = SlackConversations(self)
        self.open_conversations: Dict[str, SlackConversation] = {}
        self.users = SlackUsers(self)
        self.bots = SlackBots(self)
        self.usergroups = SlackUsergroups(self)
        self.muted_channels: Set[str] = set()
        self.custom_emojis: Dict[str, str] = {}

    def __repr__(self):
        return f"{self.__class__.__name__}({self.name})"

    @property
    def token_type(self) -> Literal["oauth", "session", "unknown"]:
        if self.config.api_token.value.startswith("xoxp-"):
            return "oauth"
        elif self.config.api_token.value.startswith("xoxc-"):
            return "session"
        else:
            return "unknown"

    @property
    def team_is_org_level(self) -> bool:
        return self.id.startswith("E")

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
        weechat.prnt("", f"Connecting to workspace {self.name}")
        self._connect_task = create_task(self._connect())
        await self._connect_task
        weechat.prnt("", f"Connected to workspace {self.name}")
        self._connect_task = None

    async def _connect_oauth(self) -> List[SlackConversation]:
        rtm_connect = await self.api.fetch_rtm_connect()
        self.id = rtm_connect["team"]["id"]
        self.my_user = await self.users[rtm_connect["self"]["id"]]

        await self._connect_ws(rtm_connect["url"])

        prefs = await self.api.fetch_users_get_prefs("muted_channels")
        self.muted_channels = set(prefs["prefs"]["muted_channels"].split(","))

        users_conversations_response = await self.api.fetch_users_conversations(
            "public_channel,private_channel,mpim,im"
        )
        channels = users_conversations_response["channels"]
        self.conversations.initialize_items(channel["id"] for channel in channels)

        conversations_if_should_open = await gather(
            *(self._conversation_if_should_open(channel) for channel in channels)
        )
        conversations_to_open = [
            c for c in conversations_if_should_open if c is not None
        ]
        return conversations_to_open

    async def _connect_session(self) -> List[SlackConversation]:
        team_info_task = create_task(self.api.fetch_team_info())
        user_boot_task = create_task(self.api.fetch_client_userboot())
        client_counts_task = create_task(self.api.fetch_client_counts())
        team_info = await team_info_task
        user_boot = await user_boot_task
        client_counts = await client_counts_task

        self.id = team_info["team"]["id"]
        self.enterprise_id = (
            self.id
            if self.team_is_org_level
            else team_info["team"]["enterprise_id"]
            if "enterprise_id" in team_info["team"]
            else None
        )
        my_user_id = user_boot["self"]["id"]
        # self.users.initialize_items(my_user_id, {my_user_id: user_boot["self"]})
        self.my_user = await self.users[my_user_id]
        self.muted_channels = set(user_boot["prefs"]["muted_channels"].split(","))

        await self._connect_ws(
            f"wss://wss-primary.slack.com/?token={self.config.api_token.value}&batch_presence_aware=1"
        )

        conversation_counts = (
            client_counts["channels"] + client_counts["mpims"] + client_counts["ims"]
        )

        conversation_ids = set(
            [
                channel["id"]
                for channel in user_boot["channels"]
                if not channel["is_mpim"]
                and (
                    self.team_is_org_level
                    or "internal_team_ids" not in channel
                    or self.id in channel["internal_team_ids"]
                )
            ]
            + user_boot["is_open"]
            + [count["id"] for count in conversation_counts if count["has_unreads"]]
        )

        conversation_counts_ids = set(count["id"] for count in conversation_counts)
        if not conversation_ids.issubset(conversation_counts_ids):
            raise SlackError(
                self,
                "Unexpectedly missing some conversations in client.counts",
                {
                    "conversation_ids": list(conversation_ids),
                    "conversation_counts_ids": list(conversation_counts_ids),
                },
            )

        channel_infos: Dict[str, SlackConversationsInfoInternal] = {
            channel["id"]: channel for channel in user_boot["channels"]
        }
        self.conversations.initialize_items(conversation_ids, channel_infos)
        conversations = {
            conversation_id: await self.conversations[conversation_id]
            for conversation_id in conversation_ids
        }

        for conversation_count in conversation_counts:
            if conversation_count["id"] in conversations:
                conversation = conversations[conversation_count["id"]]
                # TODO: Update without moving unread marker to the bottom
                if conversation.last_read == SlackTs("0.0"):
                    conversation.last_read = SlackTs(conversation_count["last_read"])

        return list(conversations.values())

    async def _connect(self) -> None:
        try:
            if self.token_type == "session":
                conversations_to_open = await self._connect_session()
            else:
                conversations_to_open = await self._connect_oauth()
        except SlackApiError as e:
            print_error(
                f'failed connecting to workspace "{self.name}": {e.response["error"]}'
            )
            return

        custom_emojis_response = await self.api.fetch_emoji_list()
        self.custom_emojis = custom_emojis_response["emoji"]

        if not self.api.edgeapi.is_available:
            usergroups = await self.api.fetch_usergroups_list()
            for usergroup in usergroups["usergroups"]:
                future = Future[SlackUsergroup]()
                future.set_result(SlackUsergroup(self, usergroup))
                self.usergroups[usergroup["id"]] = future

        for conversation in sorted(
            conversations_to_open, key=lambda conversation: conversation.sort_key()
        ):
            await conversation.open_buffer()

        await gather(
            *(slack_buffer.set_hotlist() for slack_buffer in shared.buffers.values())
        )

        self.is_connected = True

    async def _conversation_if_should_open(self, info: SlackUsersConversations):
        conversation = await self.conversations[info["id"]]
        if not conversation.should_open():
            if conversation.type != "im" and conversation.type != "mpim":
                return

            if conversation.last_read == SlackTs("0.0"):
                history = await self.api.fetch_conversations_history(conversation)
            else:
                history = await self.api.fetch_conversations_history_after(
                    conversation, conversation.last_read
                )
            if not history["messages"]:
                return

        return conversation

    async def _connect_ws(self, url: str):
        proxy = Proxy()
        # TODO: Handle errors
        self._ws = create_connection(
            url,
            self.config.network_timeout.value,
            cookie=get_cookies(self.config.api_cookies.value),
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
            except (WebSocketConnectionClosedException, socket.error) as e:
                print("lost connection on receive, reconnecting", e)
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
        # TODO: Remove old messages
        log(LogLevel.DEBUG, DebugMessageType.WEBSOCKET_RECV, json.dumps(data))

        try:
            if data["type"] in [
                "hello",
                "file_public",
                "file_shared",
                "file_deleted",
                "dnd_updated_user",
            ]:
                return
            elif data["type"] == "pref_change":
                if data["name"] == "muted_channels":
                    new_muted_channels = set(data["value"].split(","))
                    changed_channels = self.muted_channels ^ new_muted_channels
                    self.muted_channels = new_muted_channels
                    for channel_id in changed_channels:
                        channel = self.open_conversations.get(channel_id)
                        if channel:
                            channel.update_buffer_props()
                return
            elif data["type"] == "user_status_changed":
                user = await self.users[data["user"]["id"]]
                user.update_info_json(data["user"])
                for conversation in self.open_conversations.values():
                    if conversation.im_user_id == user.id:
                        conversation.update_buffer_props()
                return
            elif data["type"] == "channel_joined" or data["type"] == "group_joined":
                channel_id = data["channel"]["id"]
            elif data["type"] == "reaction_added" or data["type"] == "reaction_removed":
                channel_id = data["item"]["channel"]
            elif (
                data["type"] == "thread_marked"
                or data["type"] == "thread_subscribed"
                or data["type"] == "thread_unsubscribed"
            ) and data["subscription"]["type"] == "thread":
                channel_id = data["subscription"]["channel"]
            elif data["type"] == "sh_room_join" or data["type"] == "sh_room_update":
                channel_id = data["huddle"]["channel_id"]
            elif "channel" in data and isinstance(data["channel"], str):
                channel_id = data["channel"]
            else:
                log(
                    LogLevel.DEBUG,
                    DebugMessageType.LOG,
                    f"unknown websocket message type (without channel): {data.get('type')}",
                )
                return

            channel = self.open_conversations.get(channel_id)
            if channel is None:
                if (
                    data["type"] == "message"
                    or data["type"] == "im_open"
                    or data["type"] == "mpim_open"
                    or data["type"] == "group_open"
                    or data["type"] == "channel_joined"
                    or data["type"] == "group_joined"
                ):
                    channel = await self.conversations[channel_id]
                    if channel.type in ["im", "mpim"] or data["type"] in [
                        "channel_joined",
                        "group_joined",
                    ]:
                        await channel.open_buffer()
                        await channel.set_hotlist()
                else:
                    log(
                        LogLevel.DEBUG,
                        DebugMessageType.LOG,
                        "received websocket message for not open conversation, discarding",
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
                    if "subtype" in data and data["subtype"] == "channel_topic":
                        channel.set_topic(data["topic"])

                    message = SlackMessage(channel, data)
                    await channel.add_new_message(message)
            elif (
                data["type"] == "im_close"
                or data["type"] == "mpim_close"
                or data["type"] == "group_close"
                or data["type"] == "channel_left"
                or data["type"] == "group_left"
            ):
                if channel.buffer_pointer is not None and channel.is_joined:
                    await channel.close_buffer()
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
            elif (
                data["type"] == "channel_marked"
                or data["type"] == "group_marked"
                or data["type"] == "mpim_marked"
                or data["type"] == "im_marked"
            ):
                channel.last_read = SlackTs(data["ts"])
            elif (
                data["type"] == "thread_marked"
                and data["subscription"]["type"] == "thread"
            ):
                message = channel.messages.get(
                    SlackTs(data["subscription"]["thread_ts"])
                )
                if message:
                    message.last_read = SlackTs(data["subscription"]["last_read"])
            elif (
                data["type"] == "thread_subscribed"
                or data["type"] == "thread_unsubscribed"
            ) and data["subscription"]["type"] == "thread":
                message = channel.messages.get(
                    SlackTs(data["subscription"]["thread_ts"])
                )
                if message:
                    subscribed = data["type"] == "thread_subscribed"
                    await message.update_subscribed(subscribed, data["subscription"])
            elif data["type"] == "sh_room_join" or data["type"] == "sh_room_update":
                await channel.update_message_room(data)
            elif data["type"] == "user_typing":
                await channel.typing_add_user(data)
            else:
                log(
                    LogLevel.DEBUG,
                    DebugMessageType.LOG,
                    f"unknown websocket message type (with channel): {data.get('type')}",
                )
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

        msg = {
            "type": "user_typing",
            "channel": buffer.conversation.id,
        }
        if isinstance(buffer, SlackThread):
            msg["thread_ts"] = buffer.parent.ts
        self._ws.send(json.dumps(msg))

    async def reconnect(self):
        self.disconnect()
        await self.connect()

    def disconnect(self):
        self.is_connected = False
        weechat.prnt("", f"Disconnected from workspace {self.name}")

        if self._connect_task:
            self._connect_task.cancel()
            self._connect_task = None

        if self._hook_ws_fd:
            weechat.unhook(self._hook_ws_fd)
            self._hook_ws_fd = None

        if self._ws:
            self._ws.close()
            self._ws = None
