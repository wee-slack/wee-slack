from __future__ import annotations

import json
import re
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
    Union,
)

import weechat
from websocket import (
    ABNF,
    WebSocket,
    WebSocketConnectionClosedException,
    create_connection,
)

from slack.error import (
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
from slack.slack_message_buffer import SlackMessageBuffer
from slack.slack_thread import SlackThread
from slack.slack_user import SlackBot, SlackUser, SlackUsergroup
from slack.task import Future, Task, create_task, gather, run_async, sleep
from slack.util import get_callback_name, get_cookies
from slack.weechat_buffer import buffer_new

if TYPE_CHECKING:
    from slack_api.slack_bots_info import SlackBotInfo
    from slack_api.slack_client_userboot import SlackClientUserbootIm
    from slack_api.slack_usergroups_info import SlackUsergroupInfo
    from slack_api.slack_users_conversations import SlackUsersConversations
    from slack_api.slack_users_info import SlackUserInfo
    from slack_api.slack_users_prefs import AllNotificationsPrefs
    from slack_rtm.slack_rtm_message import SlackRtmMessage, SlackSubteam
    from typing_extensions import Literal

    from slack.slack_conversation import SlackConversationsInfoInternal
    from slack.slack_search_buffer import SearchType, SlackSearchBuffer
else:
    SlackBotInfo = object
    SlackConversationsInfoInternal = object
    SlackUsergroupInfo = object
    SlackUserInfo = object
    SlackSubteam = object


def workspace_get_buffer_to_merge_with() -> Optional[str]:
    if shared.config.look.workspace_buffer.value == "merge_with_core":
        return weechat.buffer_search_main()
    elif shared.config.look.workspace_buffer.value == "merge_without_core":
        workspace_buffers_by_number = {
            weechat.buffer_get_integer(
                workspace.buffer_pointer, "number"
            ): workspace.buffer_pointer
            for workspace in shared.workspaces.values()
            if workspace.buffer_pointer is not None
        }
        if workspace_buffers_by_number:
            lowest_number = min(workspace_buffers_by_number.keys())
            return workspace_buffers_by_number[lowest_number]


SlackItemClass = TypeVar(
    "SlackItemClass", SlackConversation, SlackUser, SlackBot, SlackUsergroup
)
SlackItemInfo = TypeVar(
    "SlackItemInfo",
    SlackConversationsInfoInternal,
    SlackUserInfo,
    SlackBotInfo,
    Union[SlackUsergroupInfo, SlackSubteam],
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


class SlackUsergroups(
    SlackItem[SlackUsergroup, Union[SlackUsergroupInfo, SlackSubteam]]
):
    def __init__(self, workspace: SlackWorkspace):
        super().__init__(workspace, SlackUsergroup)

    async def _fetch_items_info(
        self, item_ids: Iterable[str]
    ) -> Dict[str, Union[SlackUsergroupInfo, SlackSubteam]]:
        response = await self.workspace.api.edgeapi.fetch_usergroups_info(
            list(item_ids)
        )
        return {info["id"]: info for info in response["results"]}

    async def _create_item_from_info(
        self, item_info: Union[SlackUsergroupInfo, SlackSubteam]
    ) -> SlackUsergroup:
        return self._item_class(self.workspace, item_info)


class SlackWorkspace(SlackBuffer):
    def __init__(self, name: str):
        super().__init__()
        self.name = name
        self.config = shared.config.create_workspace_config(self.name)
        self._api = SlackApi(self)
        self._initial_connect = True
        self._is_connected = False
        self._connect_task: Optional[Task[bool]] = None
        self._ws: Optional[WebSocket] = None
        self._hook_ws_fd: Optional[str] = None
        self._last_ws_received_time = time.time()
        self._last_tickle = time.time()
        self._debug_ws_buffer_pointer: Optional[str] = None
        self._reconnect_url: Optional[str] = None
        self.my_user: SlackUser
        self.conversations = SlackConversations(self)
        self.open_conversations: Dict[str, SlackConversation] = {}
        self.search_buffers: Dict[SearchType, SlackSearchBuffer] = {}
        self.users = SlackUsers(self)
        self.bots = SlackBots(self)
        self.usergroups = SlackUsergroups(self)
        self.usergroups_member: Set[str] = set()
        self.muted_channels: Set[str] = set()
        self.global_keywords_regex: Optional[re.Pattern[str]] = None
        self.custom_emojis: Dict[str, str] = {}
        self.max_users_per_fetch_request = 512

    def __repr__(self):
        return f"{self.__class__.__name__}({self.name})"

    @property
    def workspace(self) -> SlackWorkspace:
        return self

    @property
    def api(self) -> SlackApi:
        return self._api

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

    def get_full_name(self) -> str:
        return f"{shared.SCRIPT_NAME}.server.{self.name}"

    def get_buffer_props(self) -> Dict[str, str]:
        buffer_props = {
            "short_name": self.name,
            "title": "",
            "input_multiline": "1",
            "localvar_set_type": "server",
            "localvar_set_slack_type": "workspace",
            "localvar_set_channel": self.name,
            "localvar_set_server": self.name,
            "localvar_set_workspace": self.name,
            "localvar_set_completion_default_template": "${weechat.completion.default_template}|%(slack_channels)|%(slack_emojis)",
        }
        if hasattr(self, "my_user"):
            buffer_props["input_prompt"] = self.my_user.nick.raw_nick
            buffer_props["localvar_set_nick"] = self.my_user.nick.raw_nick
        return buffer_props

    def open_buffer(self, switch: bool = False):
        if self.buffer_pointer:
            if switch:
                weechat.buffer_set(self.buffer_pointer, "display", "1")
            return

        buffer_props = self.get_buffer_props()

        if switch:
            buffer_props["display"] = "1"

        self._buffer_pointer = buffer_new(
            self.get_full_name(),
            buffer_props,
            self._buffer_input_cb,
            self._buffer_close_cb,
        )

        buffer_to_merge_with = workspace_get_buffer_to_merge_with()
        if (
            buffer_to_merge_with
            and weechat.buffer_get_integer(self._buffer_pointer, "layout_number") < 1
        ):
            weechat.buffer_merge(self._buffer_pointer, buffer_to_merge_with)

        shared.buffers[self._buffer_pointer] = self

    def update_buffer_props(self) -> None:
        if self.buffer_pointer is None:
            return

        buffer_props = self.get_buffer_props()
        buffer_props["name"] = self.get_full_name()
        for key, value in buffer_props.items():
            weechat.buffer_set(self.buffer_pointer, key, value)

    def print(self, message: str) -> bool:
        if not self.buffer_pointer:
            return False
        weechat.prnt(self.buffer_pointer, message)
        return True

    async def connect(self) -> None:
        if self.is_connected:
            return
        self.open_buffer()
        self.print(f"Connecting to workspace {self.name}")
        self._connect_task = create_task(self._connect())
        self.is_connected = await self._connect_task
        self._connect_task = None

    async def _connect(self) -> bool:
        if self._reconnect_url is not None:
            try:
                await self._connect_ws(self._reconnect_url)
                return True
            except Exception:
                self._reconnect_url = None

        try:
            if self.token_type == "session":
                team_info = await self.api.fetch_team_info()
                self.id = team_info["team"]["id"]
                self.enterprise_id = (
                    self.id
                    if self.team_is_org_level
                    else team_info["team"]["enterprise_id"]
                    if "enterprise_id" in team_info["team"]
                    else None
                )
                self.domain = team_info["team"]["domain"]
                await self._connect_ws(
                    f"wss://wss-primary.slack.com/?token={self.config.api_token.value}&gateway_server={self.id}-1&slack_client=desktop&batch_presence_aware=1"
                )
            else:
                rtm_connect = await self.api.fetch_rtm_connect()
                self.id = rtm_connect["team"]["id"]
                self.enterprise_id = rtm_connect["team"].get("enterprise_id")
                self.domain = rtm_connect["team"]["domain"]
                self.my_user = await self.users[rtm_connect["self"]["id"]]
                await self._connect_ws(rtm_connect["url"])
        except Exception as e:
            print_error(
                f'Failed connecting to workspace "{self.name}": {store_and_format_exception(e)}'
            )
            return False

        return True

    def _set_global_keywords(self, all_notifications_prefs: AllNotificationsPrefs):
        global_keywords = set(
            all_notifications_prefs["global"]["global_keywords"].split(",")
        )
        regex_words = "|".join(re.escape(keyword) for keyword in global_keywords)
        if regex_words:
            self.global_keywords_regex = re.compile(
                rf"\b(?:{regex_words})\b", re.IGNORECASE
            )
        else:
            self.global_keywords_regex = None

    async def _initialize_oauth(self) -> List[SlackConversation]:
        prefs = await self.api.fetch_users_get_prefs(
            "muted_channels,all_notifications_prefs"
        )
        self.muted_channels = set(prefs["prefs"]["muted_channels"].split(","))
        all_notifications_prefs = json.loads(prefs["prefs"]["all_notifications_prefs"])
        self._set_global_keywords(all_notifications_prefs)

        usergroups = await self.api.fetch_usergroups_list(include_users=True)
        for usergroup in usergroups["usergroups"]:
            future = Future[SlackUsergroup]()
            future.set_result(SlackUsergroup(self, usergroup))
            self.usergroups[usergroup["id"]] = future
        self.usergroups_member = set(
            u["id"]
            for u in usergroups["usergroups"]
            if self.my_user.id in u.get("users", [])
        )

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

        # Load the first 1000 chanels to be able to look them up by name, since
        # we can't look up a channel id from channel name with OAuth tokens
        first_channels = await self.api.fetch_conversations_list_public(limit=1000)
        self.conversations.initialize_items(
            [channel["id"] for channel in first_channels["channels"]],
            {channel["id"]: channel for channel in first_channels["channels"]},
        )

        return conversations_to_open

    async def _initialize_session(self) -> List[SlackConversation]:
        user_boot_task = create_task(self.api.fetch_client_userboot())
        client_counts_task = create_task(self.api.fetch_client_counts())
        user_boot = await user_boot_task
        client_counts = await client_counts_task

        my_user_id = user_boot["self"]["id"]
        # self.users.initialize_items(my_user_id, {my_user_id: user_boot["self"]})
        self.my_user = await self.users[my_user_id]
        self.muted_channels = set(user_boot["prefs"]["muted_channels"].split(","))
        all_notifications_prefs = json.loads(
            user_boot["prefs"]["all_notifications_prefs"]
        )
        self._set_global_keywords(all_notifications_prefs)

        self.usergroups_member = set(user_boot["subteams"]["self"])

        channel_infos: Dict[str, SlackConversationsInfoInternal] = {
            channel["id"]: channel for channel in user_boot["channels"]
        }

        channel_counts = client_counts["channels"] + client_counts["mpims"]

        for channel_count in channel_counts:
            if channel_count["id"] in channel_infos:
                channel_infos[channel_count["id"]]["last_read"] = channel_count[
                    "last_read"
                ]

        im_infos: Dict[str, SlackClientUserbootIm] = {
            im["id"]: im for im in user_boot["ims"]
        }

        for im in im_infos.values():
            # latest is incorrectly set to the current timestamp for all conversations, so delete it
            del im["latest"]

        for im_count in client_counts["ims"]:
            if im_count["id"] in im_infos:
                im_infos[im_count["id"]]["last_read"] = im_count["last_read"]
                im_infos[im_count["id"]]["latest"] = im_count["latest"]

        channel_ids = set(
            [
                channel["id"]
                for channel in user_boot["channels"]
                if not channel["is_mpim"]
                and not channel["is_archived"]
                and (
                    self.team_is_org_level
                    or "internal_team_ids" not in channel
                    or self.id in channel["internal_team_ids"]
                )
            ]
            + [count["id"] for count in channel_counts if count["has_unreads"]]
        )

        im_ids = set(
            [
                im["id"]
                for im in user_boot["ims"]
                if "latest" in im and SlackTs(im["last_read"]) < SlackTs(im["latest"])
            ]
            + user_boot["is_open"]
            + [count["id"] for count in client_counts["ims"] if count["has_unreads"]]
        )

        conversation_ids = channel_ids | im_ids
        self.conversations.initialize_items(
            conversation_ids, {**channel_infos, **im_infos}
        )
        conversations = {
            conversation_id: await self.conversations[conversation_id]
            for conversation_id in conversation_ids
        }

        # TODO: Update last_read and other info on reconnect

        return list(conversations.values())

    async def _initialize(self):
        try:
            if self.token_type == "session":
                conversations_to_open = await self._initialize_session()
            else:
                conversations_to_open = await self._initialize_oauth()
        except Exception as e:
            print_error(
                f'Failed connecting to workspace "{self.name}": {store_and_format_exception(e)}'
            )
            self.disconnect()
            return

        self.update_buffer_props()

        custom_emojis_response = await self.api.fetch_emoji_list()
        self.custom_emojis = custom_emojis_response["emoji"]

        for conversation in sorted(
            conversations_to_open, key=lambda conversation: conversation.sort_key()
        ):
            await conversation.open_buffer()

        await gather(
            *(
                slack_buffer.set_hotlist()
                for slack_buffer in shared.buffers.values()
                if isinstance(slack_buffer, SlackMessageBuffer)
            )
        )

    async def _conversation_if_should_open(self, info: SlackUsersConversations):
        conversation = await self.conversations[info["id"]]
        if not conversation.should_open():
            if conversation.type != "im" and conversation.type != "mpim":
                return

            if conversation.last_read == SlackTs("0.0"):
                history = await self.api.fetch_conversations_history(conversation)
            else:
                history = await self.api.fetch_conversations_history_after(
                    conversation, conversation.last_read, inclusive=False
                )
            if not history["messages"]:
                return

        return conversation

    async def _load_unread_conversations(self):
        open_conversations = list(self.open_conversations.values())
        for conversation in open_conversations:
            if (
                conversation.hotlist_tss
                and not conversation.muted
                and self.is_connected
            ):
                await conversation.fill_history()
                # TODO: Better sleep heuristic
                sleep_duration = (
                    20000 if conversation.display_thread_replies() else 1000
                )
                await sleep(sleep_duration)

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
        self._last_ws_received_time = time.time()

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

            self._last_ws_received_time = time.time()

            if opcode == ABNF.OPCODE_PONG:
                return weechat.WEECHAT_RC_OK
            elif opcode != ABNF.OPCODE_TEXT:
                return weechat.WEECHAT_RC_OK

            run_async(self.ws_recv(json.loads(recv_data.decode())))

    async def ws_recv(self, data: SlackRtmMessage):
        # TODO: Remove old messages
        log(LogLevel.DEBUG, DebugMessageType.WEBSOCKET_RECV, json.dumps(data))

        try:
            if data["type"] == "hello":
                if self._initial_connect or not data["fast_reconnect"]:
                    await self._initialize()
                if self.is_connected:
                    self.print(f"Connected to workspace {self.name}")
                if self._initial_connect or not data["fast_reconnect"]:
                    await self._load_unread_conversations()
                self._initial_connect = False
                return
            elif data["type"] == "error":
                if data["error"]["code"] == 1:  # Socket URL has expired
                    self._reconnect_url = None
                return
            elif data["type"] == "reconnect_url":
                self._reconnect_url = data["url"]
                return
            elif data["type"] == "pref_change":
                if data["name"] == "muted_channels":
                    new_muted_channels = set(data["value"].split(","))
                    self._set_muted_channels(new_muted_channels)
                elif data["name"] == "all_notifications_prefs":
                    new_prefs = json.loads(data["value"])
                    new_muted_channels = set(
                        channel_id
                        for channel_id, prefs in new_prefs["channels"].items()
                        if prefs["muted"]
                    )
                    self._set_muted_channels(new_muted_channels)
                    self._set_global_keywords(new_prefs)
                return
            elif data["type"] == "user_status_changed":
                user_id = data["user"]["id"]
                if user_id in self.users:
                    user = await self.users[user_id]
                    user.update_info_json(data["user"])
                return
            elif data["type"] == "user_invalidated":
                user_id = data["user"]["id"]
                if user_id in self.users:
                    has_dm_conversation = any(
                        conversation.im_user_id == user_id
                        for conversation in self.open_conversations.values()
                    )
                    if has_dm_conversation:
                        user = await self.users[user_id]
                        user_info = await self.api.fetch_user_info(user_id)
                        user.update_info_json(user_info["user"])
                return
            elif data["type"] == "subteam_created":
                subteam_id = data["subteam"]["id"]
                self.usergroups.initialize_items(
                    [subteam_id], {subteam_id: data["subteam"]}
                )
                return
            elif data["type"] == "subteam_updated":
                subteam_id = data["subteam"]["id"]
                if subteam_id in self.usergroups:
                    usergroup = await self.usergroups[subteam_id]
                    usergroup.update_info_json(data["subteam"])
                return
            elif data["type"] == "subteam_members_changed":
                # Handling subteam_updated should be enough
                return
            elif data["type"] == "subteam_self_added":
                self.usergroups_member.add(data["subteam_id"])
                return
            elif data["type"] == "subteam_self_removed":
                self.usergroups_member.remove(data["subteam_id"])
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
                if data["type"] not in [
                    "file_public",
                    "file_shared",
                    "file_deleted",
                    "dnd_updated_user",
                    "pong",
                ]:
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

    def ws_send(self, msg: object):
        if not self.is_connected:
            raise SlackError(self, "Can't send to ws when not connected")
        if self._ws is None:
            raise SlackError(self, "is_connected is True while _ws is None")

        data = json.dumps(msg)
        log(LogLevel.DEBUG, DebugMessageType.WEBSOCKET_SEND, data)
        self._ws.send(data)

    def _set_muted_channels(self, muted_channels: Set[str]):
        changed_channels = self.muted_channels ^ muted_channels
        self.muted_channels = muted_channels
        for channel_id in changed_channels:
            channel = self.open_conversations.get(channel_id)
            if channel:
                channel.update_buffer_props()

    def ping(self):
        if not self.is_connected:
            raise SlackError(self, "Can't ping when not connected")
        if self._ws is None:
            raise SlackError(self, "is_connected is True while _ws is None")

        time_since_last_msg = time.time() - self._last_ws_received_time
        if time_since_last_msg > self.config.network_timeout.value:
            run_async(self.reconnect())
            return

        try:
            self.ws_send({"type": "ping"})
        except (WebSocketConnectionClosedException, socket.error):
            print("lost connection on ping, reconnecting")
            run_async(self.reconnect())

    def tickle(self, force: bool = False):
        if force or time.time() - self._last_tickle >= 20:
            self.ws_send({"type": "tickle"})
            self._last_tickle = time.time()

    def send_typing(self, buffer: SlackMessageBuffer):
        msg = {
            "type": "user_typing",
            "channel": buffer.conversation.id,
        }
        if isinstance(buffer, SlackThread):
            msg["thread_ts"] = buffer.parent.ts
        self.ws_send(msg)

    async def reconnect(self):
        self.disconnect()
        await self.connect()

    def disconnect(self):
        self.is_connected = False
        self.print(f"Disconnected from workspace {self.name}")

        if self._connect_task:
            self._connect_task.cancel()
            self._connect_task = None

        if self._hook_ws_fd:
            weechat.unhook(self._hook_ws_fd)
            self._hook_ws_fd = None

        if self._ws:
            self._ws.close()
            self._ws = None

    def _buffer_input_cb(self, data: str, buffer: str, input_data: str) -> int:
        self.print(
            f"{weechat.prefix('error')}{shared.SCRIPT_NAME}: this buffer is not a channel!"
        )
        return weechat.WEECHAT_RC_OK

    def _buffer_close_cb(self, data: str, buffer: str) -> int:
        run_async(self._buffer_close())
        return weechat.WEECHAT_RC_OK

    async def _buffer_close(self):
        if shared.script_is_unloading:
            return

        if self.is_connected:
            self.disconnect()

        conversations = list(shared.buffers.values())
        for conversation in conversations:
            if (
                isinstance(conversation, SlackMessageBuffer)
                and conversation.workspace == self
            ):
                await conversation.close_buffer()

        if self.buffer_pointer in shared.buffers:
            del shared.buffers[self.buffer_pointer]

        self._buffer_pointer = None
        self._initial_connect = True
