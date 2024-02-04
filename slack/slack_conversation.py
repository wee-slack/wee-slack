from __future__ import annotations

import hashlib
from collections import OrderedDict
from typing import (
    TYPE_CHECKING,
    Dict,
    Generator,
    List,
    Mapping,
    NoReturn,
    Optional,
    Tuple,
    Type,
    TypeVar,
    Union,
)

import weechat

from slack.error import SlackApiError, SlackError
from slack.python_compatibility import removeprefix
from slack.shared import shared
from slack.slack_buffer import SlackBuffer
from slack.slack_message import (
    MessagePriority,
    PendingMessageItem,
    SlackMessage,
    SlackTs,
)
from slack.slack_thread import SlackThread
from slack.slack_user import Nick, SlackUser
from slack.task import Task, gather, run_async
from slack.util import unhtmlescape, with_color

if TYPE_CHECKING:
    from slack_api.slack_client_userboot import SlackClientUserbootIm
    from slack_api.slack_conversations_info import SlackConversationsInfo, SlackTopic
    from slack_api.slack_users_conversations import SlackUsersConversationsNotIm
    from slack_rtm.slack_rtm_message import (
        SlackMessageChanged,
        SlackMessageDeleted,
        SlackMessageReplied,
        SlackShRoomJoin,
        SlackShRoomUpdate,
        SlackUserTyping,
    )
    from typing_extensions import Literal

    from slack.slack_workspace import SlackWorkspace

    SlackConversationsInfoInternal = Union[
        SlackConversationsInfo, SlackUsersConversationsNotIm, SlackClientUserbootIm
    ]


def update_buffer_props():
    for workspace in shared.workspaces.values():
        for conversation in workspace.open_conversations.values():
            conversation.update_buffer_props()


def invalidate_nicklists():
    for workspace in shared.workspaces.values():
        for conversation in workspace.open_conversations.values():
            conversation.nicklist_needs_refresh = True


def sha1_hex(string: str) -> str:
    return str(hashlib.sha1(string.encode()).hexdigest())


def hash_from_ts(ts: SlackTs) -> str:
    return sha1_hex(str(ts))


class SlackConversationMessageHashes(Dict[SlackTs, str]):
    def __init__(self, conversation: SlackConversation):
        self._conversation = conversation
        self._inverse_map: Dict[str, SlackTs] = {}

    def __setitem__(self, key: SlackTs, value: str) -> NoReturn:
        raise RuntimeError("Set from outside isn't allowed")

    def __delitem__(self, key: SlackTs) -> None:
        if key in self:
            hash_key = self[key]
            del self._inverse_map[hash_key]
        super().__delitem__(key)

    def _setitem(self, key: SlackTs, value: str) -> None:
        super().__setitem__(key, value)

    def __missing__(self, key: SlackTs) -> str:
        hash_len = 3
        full_hash = hash_from_ts(key)
        short_hash = full_hash[:hash_len]

        while any(
            existing_hash.startswith(short_hash) for existing_hash in self._inverse_map
        ):
            hash_len += 1
            short_hash = full_hash[:hash_len]

        if short_hash[:-1] in self._inverse_map:
            ts_with_same_hash = self._inverse_map.pop(short_hash[:-1])
            other_full_hash = hash_from_ts(ts_with_same_hash)
            other_short_hash = other_full_hash[:hash_len]

            while short_hash == other_short_hash:
                hash_len += 1
                short_hash = full_hash[:hash_len]
                other_short_hash = other_full_hash[:hash_len]

            self._setitem(ts_with_same_hash, other_short_hash)
            self._inverse_map[other_short_hash] = ts_with_same_hash

            other_message = self._conversation.messages.get(ts_with_same_hash)
            if other_message:
                run_async(self._conversation.rerender_message(other_message))
                if other_message.thread_buffer is not None:
                    other_message.thread_buffer.update_buffer_props()
                for reply in other_message.replies.values():
                    run_async(self._conversation.rerender_message(reply))

        self._setitem(key, short_hash)
        self._inverse_map[short_hash] = key
        return self[key]

    def get_ts(self, ts_hash: str) -> Optional[SlackTs]:
        hash_without_prefix = removeprefix(ts_hash, "$")
        return self._inverse_map.get(hash_without_prefix)


class SlackConversation(SlackBuffer):
    async def __new__(
        cls,
        workspace: SlackWorkspace,
        info: SlackConversationsInfoInternal,
    ):
        conversation = super().__new__(cls)
        conversation.__init__(workspace, info)
        return await conversation

    def __init__(
        self,
        workspace: SlackWorkspace,
        info: SlackConversationsInfoInternal,
    ):
        super().__init__()
        self._workspace = workspace
        self._info = info
        self._members: Optional[List[str]] = None
        self._im_user: Optional[SlackUser] = None
        self._mpim_users: Optional[List[SlackUser]] = None
        self._messages: OrderedDict[SlackTs, SlackMessage] = OrderedDict()
        self._nicklist: Dict[Nick, str] = {}
        self.nicklist_needs_refresh = True
        self.message_hashes = SlackConversationMessageHashes(self)

        self._last_read = (
            SlackTs(self._info["last_read"])
            if "last_read" in self._info
            else SlackTs("0.0")
        )

        self._topic: SlackTopic = (
            self._info["topic"]
            if "topic" in self._info
            else {"value": "", "creator": "", "last_set": 0}
        )

    async def __init_async(self):
        if self._info["is_im"] is True:
            self._im_user = await self._workspace.users[self._info["user"]]
        elif self.type == "mpim":
            if "members" in self._info:
                members = self._info["members"]
            else:
                members = await self.load_members(load_all=True)

            self._mpim_users = await gather(
                *(
                    self._workspace.users[user_id]
                    for user_id in members
                    if user_id != self._workspace.my_user.id
                )
            )

    def __await__(self: _T) -> Generator[Task[None], None, _T]:
        yield from self.__init_async().__await__()
        return self

    @classmethod
    async def create(
        cls: Type[_T], workspace: SlackWorkspace, conversation_id: str
    ) -> _T:
        info_response = await workspace.api.fetch_conversations_info(conversation_id)
        return await cls(workspace, info_response["channel"])

    def __repr__(self):
        return f"{self.__class__.__name__}({self.workspace}, {self.id})"

    @property
    def id(self) -> str:
        return self._info["id"]

    @property
    def workspace(self) -> SlackWorkspace:
        return self._workspace

    @property
    def conversation(self) -> SlackConversation:
        return self

    @property
    def context(self) -> Literal["conversation", "thread"]:
        return "conversation"

    @property
    def members(self) -> Generator[Nick, None, None]:
        for nick in self._nicklist:
            if nick.type == "user":
                yield nick

    @property
    def messages(self) -> Mapping[SlackTs, SlackMessage]:
        return self._messages

    @property
    def type(self) -> Literal["channel", "private", "mpim", "im"]:
        if self._info["is_im"] is True:
            return "im"
        elif self._info["is_mpim"] is True:
            return "mpim"
        elif self._info["is_private"] is True:
            return "private"
        else:
            return "channel"

    @property
    def buffer_type(self) -> Literal["private", "channel"]:
        return "private" if self.type in ("im", "mpim") else "channel"

    @property
    def last_read(self) -> SlackTs:
        return self._last_read

    @last_read.setter
    def last_read(self, value: SlackTs):
        self._last_read = value
        self.set_unread_and_hotlist()

    @property
    def muted(self) -> bool:
        return self.id in self.workspace.muted_channels

    @property
    def im_user_id(self) -> Optional[str]:
        if self.type == "im":
            return self._info.get("user")

    def sort_key(self) -> str:
        type_sort_key = {
            "channel": 0,
            "private": 1,
            "mpim": 2,
            "im": 3,
        }[self.type]
        return f"{type_sort_key}{self.name()}".lower()

    def name(self) -> str:
        if self._im_user is not None:
            return self._im_user.nick.format()
        elif self._info["is_im"] is True:
            raise SlackError(self.workspace, "IM conversation without _im_user set")
        elif self._mpim_users is not None:
            return ",".join(sorted(user.nick.format() for user in self._mpim_users))
        else:
            return self._info["name"]

    def name_prefix(
        self,
        name_type: Literal["full_name", "short_name", "short_name_without_padding"],
    ) -> str:
        if self.type == "im":
            if name_type == "short_name":
                return " "
            else:
                return ""
        elif self.type == "mpim":
            if name_type == "short_name" or name_type == "short_name_without_padding":
                return "@"
            else:
                return ""
        elif self.type == "private":
            return "&"
        else:
            return "#"

    def name_with_prefix(
        self,
        name_type: Literal["full_name", "short_name", "short_name_without_padding"],
    ) -> str:
        return f"{self.name_prefix(name_type)}{self.name()}"

    def should_open(self):
        if "is_open" in self._info:
            if self._info["is_open"]:
                return True
        elif self._info.get("is_member"):
            return True
        return False

    def buffer_title(self) -> str:
        # TODO: unfurl and apply styles
        topic = unhtmlescape(self._topic["value"])
        if self._im_user:
            status = f"{self._im_user.status_emoji} {self._im_user.status_text}".strip()
            return " | ".join(part for part in [status, topic] if part)
        return topic

    def set_topic(self, title: str):
        self._topic["value"] = title
        self.update_buffer_props()

    def get_name_and_buffer_props(self) -> Tuple[str, Dict[str, str]]:
        name_without_prefix = self.name()
        name = f"{self.name_prefix('full_name')}{name_without_prefix}"
        short_name = self.name_prefix("short_name") + name_without_prefix
        if self.muted:
            short_name = with_color(
                shared.config.color.buflist_muted_conversation.value, short_name
            )

        return name, {
            "short_name": short_name,
            "title": self.buffer_title(),
            "input_multiline": "1",
            "nicklist": "0" if self.type == "im" else "1",
            "nicklist_display_groups": "0",
            "localvar_set_type": self.buffer_type,
            "localvar_set_slack_type": self.type,
            "localvar_set_nick": self.workspace.my_user.nick.raw_nick,
            "localvar_set_channel": name,
            "localvar_set_server": self.workspace.name,
            "localvar_set_completion_default_template": "${weechat.completion.default_template}|%(slack_channels)|%(slack_emojis)",
        }

    async def buffer_switched_to(self):
        await super().buffer_switched_to()
        await gather(self.nicklist_update(), self.fill_history())

    async def open_buffer(self, switch: bool = False):
        await super().open_buffer(switch)
        self.workspace.open_conversations[self.id] = self

    async def rerender_message(self, message: SlackMessage):
        await super().rerender_message(message)
        parent_message = message.parent_message
        if parent_message and parent_message.thread_buffer:
            await parent_message.thread_buffer.rerender_message(message)

    async def load_members(self, load_all: bool = False):
        if self._members is None:
            members_response = await self._api.fetch_conversations_members(
                self, limit=None if load_all else 1000
            )
            self._members = members_response["members"]
        self.workspace.users.initialize_items(self._members)
        return self._members

    async def fetch_replies(self, thread_ts: SlackTs) -> List[SlackMessage]:
        replies_response = await self._api.fetch_conversations_replies(self, thread_ts)
        messages = [
            SlackMessage(self, message) for message in replies_response["messages"]
        ]

        if thread_ts != messages[0].ts:
            raise SlackError(
                self.workspace,
                f"First message in conversations.replies response did not match thread_ts {thread_ts}",
                replies_response,
            )

        if thread_ts not in self._messages:
            self._messages[thread_ts] = messages[0]

        parent_message = self._messages[thread_ts]

        replies = messages[1:]
        for reply in replies:
            parent_message.replies[reply.ts] = reply
            self._messages[reply.ts] = reply

        parent_message.replies = OrderedDict(sorted(parent_message.replies.items()))
        self._messages = OrderedDict(sorted(self._messages.items()))

        parent_message.reply_history_filled = True
        return replies

    async def set_hotlist(self):
        if self.last_printed_ts is not None:
            self.history_needs_refresh = True

        if self.buffer_pointer and shared.current_buffer_pointer == self.buffer_pointer:
            await self.fill_history()
            return

        if self.last_printed_ts is not None:
            history_after_ts = (
                next(iter(self._messages))
                if self.display_thread_replies()
                else self.last_printed_ts
            )
            history = await self._api.fetch_conversations_history_after(
                self, history_after_ts
            )
        else:
            history = await self._api.fetch_conversations_history(self)

        if self.buffer_pointer and shared.current_buffer_pointer != self.buffer_pointer:
            for message_json in history["messages"]:
                message = SlackMessage(self, message_json)
                if message.ts > self.last_read and message.ts not in self.hotlist_tss:
                    weechat.buffer_set(
                        self.buffer_pointer, "hotlist", message.priority.value
                    )
                    self.hotlist_tss.add(message.ts)
                if (
                    self.display_thread_replies()
                    and (
                        not self.muted
                        or shared.config.look.muted_conversations_notify.value == "all"
                    )
                    and message.latest_reply
                    and message.latest_reply > self.last_read
                    and message.latest_reply not in self.hotlist_tss
                ):
                    # TODO: Load subscribed threads, so they are added to hotlist for muted channels if they have highlights
                    priority = (
                        MessagePriority.PRIVATE
                        if self.buffer_type == "private"
                        else MessagePriority.MESSAGE
                    )
                    weechat.buffer_set(self.buffer_pointer, "hotlist", priority.value)
                    self.hotlist_tss.add(message.latest_reply)

    async def fill_history(self):
        if self.history_pending:
            return

        if self.last_printed_ts is not None and not self.history_needs_refresh:
            return

        with self.loading():
            self.history_pending = True

            history_after_ts = (
                next(iter(self._messages), None)
                if self.history_needs_refresh
                else self.last_printed_ts
            )
            if history_after_ts:
                history = await self._api.fetch_conversations_history_after(
                    self, history_after_ts
                )
            else:
                history = await self._api.fetch_conversations_history(self)

            conversation_messages = [
                SlackMessage(self, message) for message in history["messages"]
            ]
            for message in reversed(conversation_messages):
                self._messages[message.ts] = message

            if self.display_thread_replies():
                await gather(
                    *(
                        self.fetch_replies(message.ts)
                        for message in conversation_messages
                        if message.is_thread_parent
                    )
                )

            if self.history_needs_refresh:
                await self.rerender_history()

            self._messages = OrderedDict(sorted(self._messages.items()))
            self.history_pending_messages.clear()
            messages = [
                message
                for message in self._messages.values()
                if self.should_display_message(message)
                and self.last_printed_ts is None
                or message.ts > self.last_printed_ts
            ]

            user_ids = [m.sender_user_id for m in messages if m.sender_user_id]
            if self.display_reaction_nicks():
                reaction_user_ids = [
                    user_id
                    for m in messages
                    for reaction in m.reactions
                    for user_id in reaction["users"]
                ]
                user_ids.extend(reaction_user_ids)

            parsed_messages = [
                item for m in messages for item in m.parse_message_text()
            ]
            pending_items = [
                item for item in parsed_messages if isinstance(item, PendingMessageItem)
            ]
            item_user_ids = [
                item.item_id for item in pending_items if item.item_type == "user"
            ]
            user_ids.extend(item_user_ids)

            self.workspace.users.initialize_items(user_ids)

            sender_bot_ids = [
                m.sender_bot_id
                for m in messages
                if m.sender_bot_id and not m.sender_user_id
            ]
            self.workspace.bots.initialize_items(sender_bot_ids)

            await gather(*(message.render(self.context) for message in messages))

            for message in messages:
                await self.print_message(message)

            while self.history_pending_messages:
                message = self.history_pending_messages.pop(0)
                await self.print_message(message)

            self.history_needs_refresh = False
            self.history_pending = False

    async def nicklist_update(self):
        if self.nicklist_needs_refresh and self.type != "im":
            self.nicklist_needs_refresh = False
            try:
                members = await self.load_members()
            except SlackApiError as e:
                if e.response["error"] == "enterprise_is_restricted":
                    return
                raise e
            else:
                users = await gather(
                    *(self.workspace.users[user_id] for user_id in members)
                )
                for user in users:
                    self.nicklist_add_nick(user.nick)

    def nicklist_add_nick(self, nick: Nick):
        if nick in self._nicklist or self.type == "im" or self.buffer_pointer is None:
            return

        # TODO: weechat.color.nicklist_away
        color = nick.color if shared.config.look.color_nicks_in_nicklist else ""
        visible = 1 if nick.type == "user" else 0

        nick_pointer = weechat.nicklist_add_nick(
            self.buffer_pointer, "", nick.raw_nick, color, nick.suffix, "", visible
        )
        self._nicklist[nick] = nick_pointer

    def nicklist_remove_nick(self, nick: Nick):
        if self.type == "im" or self.buffer_pointer is None:
            return
        nick_pointer = self._nicklist.pop(nick)
        weechat.nicklist_remove_nick(self.buffer_pointer, nick_pointer)

    def display_thread_replies(self) -> bool:
        if self.buffer_pointer is not None:
            buffer_value = weechat.buffer_get_string(
                self.buffer_pointer, "localvar_display_thread_replies_in_channel"
            )
            if buffer_value:
                return bool(weechat.config_string_to_boolean(buffer_value))
        return shared.config.look.display_thread_replies_in_channel.value

    def display_reaction_nicks(self) -> bool:
        if self.buffer_pointer is not None:
            buffer_value = weechat.buffer_get_string(
                self.buffer_pointer, "localvar_display_reaction_nicks"
            )
            if buffer_value:
                return bool(weechat.config_string_to_boolean(buffer_value))
        return shared.config.look.display_reaction_nicks.value

    def should_display_message(self, message: SlackMessage) -> bool:
        return (
            not message.is_reply
            or message.is_thread_broadcast
            or self.display_thread_replies()
        )

    async def add_new_message(self, message: SlackMessage):
        # TODO: Remove old messages
        self._messages[message.ts] = message

        if self.should_display_message(message):
            if self.history_pending:
                self.history_pending_messages.append(message)
            elif self.last_printed_ts is not None:
                await self.print_message(message)
            elif self.buffer_pointer is not None:
                weechat.buffer_set(
                    self.buffer_pointer, "hotlist", message.priority.value
                )
                self.hotlist_tss.add(message.ts)

        parent_message = message.parent_message
        if parent_message:
            parent_message.replies[message.ts] = message
            thread_buffer = parent_message.thread_buffer
            if thread_buffer:
                if thread_buffer.history_pending:
                    thread_buffer.history_pending_messages.append(message)
                else:
                    await thread_buffer.print_message(message)
        elif message.thread_ts is not None:
            await self.fetch_replies(message.thread_ts)

        if message.sender_user_id:
            user = await self.workspace.users[message.sender_user_id]
            if message.is_reply:
                if parent_message and parent_message.thread_buffer:
                    weechat.hook_signal_send(
                        "typing_set_nick",
                        weechat.WEECHAT_HOOK_SIGNAL_STRING,
                        f"{parent_message.thread_buffer.buffer_pointer};off;{user.nick.format()}",
                    )
            else:
                weechat.hook_signal_send(
                    "typing_set_nick",
                    weechat.WEECHAT_HOOK_SIGNAL_STRING,
                    f"{self.buffer_pointer};off;{user.nick.format()}",
                )

    async def change_message(
        self, data: Union[SlackMessageChanged, SlackMessageReplied]
    ):
        ts = SlackTs(data["ts"])
        message = self._messages.get(ts)
        if message:
            message.update_message_json(data["message"])
            await self.rerender_message(message)

    async def delete_message(self, data: SlackMessageDeleted):
        ts = SlackTs(data["deleted_ts"])
        if ts in self.message_hashes:
            del self.message_hashes[ts]
        message = self._messages.get(ts)
        if message:
            message.deleted = True
            await self.rerender_message(message)

    async def update_message_room(
        self, data: Union[SlackShRoomJoin, SlackShRoomUpdate]
    ):
        ts = SlackTs(data["room"]["thread_root_ts"])
        message = self._messages.get(ts)
        if message:
            message.update_message_json_room(data["room"])
            await self.rerender_message(message)

    async def reaction_add(self, message_ts: SlackTs, reaction: str, user_id: str):
        message = self._messages.get(message_ts)
        if message:
            message.reaction_add(reaction, user_id)
            await self.rerender_message(message)

    async def reaction_remove(self, message_ts: SlackTs, reaction: str, user_id: str):
        message = self._messages.get(message_ts)
        if message:
            message.reaction_remove(reaction, user_id)
            await self.rerender_message(message)

    async def typing_add_user(self, data: SlackUserTyping):
        if not shared.config.look.typing_status_nicks:
            return

        user = await self.workspace.users[data["user"]]
        if "thread_ts" not in data:
            weechat.hook_signal_send(
                "typing_set_nick",
                weechat.WEECHAT_HOOK_SIGNAL_STRING,
                f"{self.buffer_pointer};typing;{user.nick.format()}",
            )
        else:
            thread_ts = SlackTs(data["thread_ts"])
            parent_message = self._messages.get(thread_ts)
            if parent_message and parent_message.thread_buffer:
                weechat.hook_signal_send(
                    "typing_set_nick",
                    weechat.WEECHAT_HOOK_SIGNAL_STRING,
                    f"{parent_message.thread_buffer.buffer_pointer};typing;{user.nick.format()}",
                )

    async def open_thread(self, thread_hash: str, switch: bool = False):
        thread_ts = self.ts_from_hash(thread_hash)
        if thread_ts:
            thread_message = self.messages.get(thread_ts)
            if thread_message is None:
                # TODO: Fetch message
                return
            if thread_message.thread_buffer is None:
                thread_message.thread_buffer = SlackThread(thread_message)
            await thread_message.thread_buffer.open_buffer(switch)

    async def print_message(self, message: SlackMessage):
        await super().print_message(message)

        nick = await message.nick()
        if message.subtype in ["channel_leave", "group_leave"]:
            self.nicklist_remove_nick(nick)
        else:
            self.nicklist_add_nick(nick)

    async def mark_read(self):
        last_read_line_ts = self.last_read_line_ts()
        if last_read_line_ts and last_read_line_ts != self.last_read:
            await self._api.conversations_mark(self, last_read_line_ts)

    async def _buffer_closed(self):
        if self.id in self.workspace.open_conversations:
            del self.workspace.open_conversations[self.id]
        if self.type in ["im", "mpim"]:
            await self._api.conversations_close(self)

    def _buffer_close_cb(self, data: str, buffer: str) -> int:
        super()._buffer_close_cb(data, buffer)
        if shared.script_is_unloading:
            return weechat.WEECHAT_RC_OK
        run_async(self._buffer_closed())
        return weechat.WEECHAT_RC_OK


_T = TypeVar("_T", bound=SlackConversation)
