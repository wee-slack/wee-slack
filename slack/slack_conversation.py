from __future__ import annotations

import hashlib
from collections import OrderedDict
from typing import TYPE_CHECKING, Dict, List, Mapping, NoReturn, Optional, Tuple, Union

import weechat

from slack.python_compatibility import removeprefix
from slack.shared import shared
from slack.slack_buffer import SlackBuffer
from slack.slack_message import SlackMessage, SlackTs
from slack.slack_thread import SlackThread
from slack.task import gather, run_async

if TYPE_CHECKING:
    from slack_api.slack_conversations_info import SlackConversationsInfo
    from slack_rtm.slack_rtm_message import (
        SlackMessageChanged,
        SlackMessageDeleted,
        SlackMessageReplied,
        SlackShRoomJoin,
        SlackShRoomUpdate,
    )
    from typing_extensions import Literal

    from slack.slack_workspace import SlackWorkspace


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

            other_message = self._conversation.messages[ts_with_same_hash]
            run_async(self._conversation.rerender_message(other_message))
            if other_message.thread_buffer is not None:
                run_async(other_message.thread_buffer.update_buffer_props())
            for reply in other_message.replies.values():
                run_async(self._conversation.rerender_message(reply))

        self._setitem(key, short_hash)
        self._inverse_map[short_hash] = key
        return self[key]

    def get_ts(self, ts_hash: str) -> Optional[SlackTs]:
        hash_without_prefix = removeprefix(ts_hash, "$")
        return self._inverse_map.get(hash_without_prefix)


class SlackConversation(SlackBuffer):
    def __init__(
        self,
        workspace: SlackWorkspace,
        info: SlackConversationsInfo,
    ):
        super().__init__()
        self._workspace = workspace
        self._info = info
        self._members: Optional[List[str]] = None
        self._messages: OrderedDict[SlackTs, SlackMessage] = OrderedDict()
        self.nicklist_needs_refresh = True
        self.message_hashes = SlackConversationMessageHashes(self)

    @classmethod
    async def create(cls, workspace: SlackWorkspace, conversation_id: str):
        info_response = await workspace.api.fetch_conversations_info(conversation_id)
        return cls(workspace, info_response["channel"])

    @property
    def id(self) -> str:
        return self._info["id"]

    @property
    def workspace(self) -> SlackWorkspace:
        return self._workspace

    @property
    def context(self) -> Literal["conversation", "thread"]:
        return "conversation"

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

    async def name(self) -> str:
        if self._info["is_im"] is True:
            im_user = await self.workspace.users[self._info["user"]]
            return im_user.nick()
        elif self._info["is_mpim"] is True:
            members = await self.load_members(load_all=True)
            member_users = await gather(
                *(
                    self.workspace.users[user_id]
                    for user_id in members
                    if user_id != self.workspace.my_user.id
                )
            )
            return ",".join(sorted(user.nick() for user in member_users))
        else:
            return self._info["name"]

    def name_prefix(
        self,
        name_type: Literal["full_name", "short_name", "short_name_without_padding"],
    ) -> str:
        if self._info["is_im"] is True:
            if name_type == "short_name":
                return " "
            else:
                return ""
        elif self._info["is_mpim"]:
            if name_type == "short_name" or name_type == "short_name_without_padding":
                return "@"
            else:
                return ""
        else:
            return "#"

    async def name_with_prefix(
        self,
        name_type: Literal["full_name", "short_name", "short_name_without_padding"],
    ) -> str:
        return f"{self.name_prefix(name_type)}{await self.name()}"

    async def open_if_open(self):
        if "is_open" in self._info:
            if self._info["is_open"]:
                await self.open_buffer()
        elif self._info.get("is_member"):
            await self.open_buffer()

    async def get_name_and_buffer_props(self) -> Tuple[str, Dict[str, str]]:
        name_without_prefix = await self.name()
        name = f"{self.name_prefix('full_name')}{name_without_prefix}"
        short_name = self.name_prefix("short_name") + name_without_prefix

        return name, {
            "short_name": short_name,
            "title": "topic",
            "input_multiline": "1",
            "nicklist": "0" if self.type == "im" else "1",
            "nicklist_display_groups": "0",
            "localvar_set_type": self.buffer_type,
            "localvar_set_slack_type": self.type,
            "localvar_set_nick": self.workspace.my_user.nick(),
            "localvar_set_channel": name,
            "localvar_set_server": self.workspace.name,
        }

    async def buffer_switched_to(self):
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

    async def fetch_replies(
        self, message: SlackMessage
    ) -> Optional[List[SlackMessage]]:
        if not message.is_thread_parent:
            return

        replies_response = await self._api.fetch_conversations_replies(message)
        replies = [
            SlackMessage(self, reply) for reply in replies_response["messages"][1:]
        ]

        for reply in replies:
            message.replies[reply.ts] = reply
            self._messages[reply.ts] = reply

        message.replies = OrderedDict(sorted(message.replies.items()))
        self._messages = OrderedDict(sorted(self._messages.items()))

        message.reply_history_filled = True
        return replies

    async def fill_history(self):
        if self.history_filled or self.history_pending:
            return

        with self.loading():
            self.history_pending = True

            history = await self._api.fetch_conversations_history(self)

            conversation_messages = [
                SlackMessage(self, message) for message in history["messages"]
            ]
            for message in reversed(conversation_messages):
                self._messages[message.ts] = message

            if self.display_thread_replies():
                await gather(
                    *(self.fetch_replies(message) for message in conversation_messages)
                )

            self._messages = OrderedDict(sorted(self._messages.items()))
            messages = [
                message
                for message in self._messages.values()
                if self.should_display_message(message)
            ]

            sender_user_ids = [m.sender_user_id for m in messages if m.sender_user_id]
            self.workspace.users.initialize_items(sender_user_ids)

            sender_bot_ids = [m.sender_bot_id for m in messages if m.sender_bot_id]
            self.workspace.bots.initialize_items(sender_bot_ids)

            await gather(*(message.render(self.context) for message in messages))

            for message in messages:
                await self.print_message(message, backlog=True)

            self.history_filled = True
            self.history_pending = False

    async def nicklist_update(self):
        if self.nicklist_needs_refresh:
            self.nicklist_needs_refresh = False
            members = await self.load_members()
            weechat.nicklist_remove_all(self.buffer_pointer)
            await gather(*(self.nicklist_add_user(user_id) for user_id in members))

    async def nicklist_add_user(self, user_id: str):
        user = await self.workspace.users[user_id]
        # TODO: weechat.color.nicklist_away
        color = user.nick_color() if shared.config.look.color_nicks_in_nicklist else ""
        weechat.nicklist_add_nick(
            self.buffer_pointer, "", user.nick(), color, "", "", 1
        )

    def display_thread_replies(self) -> bool:
        buffer_value = weechat.buffer_get_string(
            self.buffer_pointer, "localvar_display_thread_replies_in_channel"
        )
        if buffer_value:
            return bool(weechat.config_string_to_boolean(buffer_value))
        return shared.config.look.display_thread_replies_in_channel.value

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
            if self.history_filled:
                await self.print_message(message)
            else:
                weechat.buffer_set(
                    self.buffer_pointer, "hotlist", str(message.priority.value)
                )

        parent_message = message.parent_message
        if parent_message:
            parent_message.replies[message.ts] = message
            if parent_message.thread_buffer:
                await parent_message.thread_buffer.print_message(message)

        if message.sender_user_id:
            # TODO: thread buffers
            user = await self.workspace.users[message.sender_user_id]
            weechat.hook_signal_send(
                "typing_set_nick",
                weechat.WEECHAT_HOOK_SIGNAL_STRING,
                f"{self.buffer_pointer};off;{user.nick()}",
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

    async def open_thread(self, thread_hash: str, switch: bool = False):
        thread_ts = self.message_hashes.get_ts(thread_hash)
        if thread_ts:
            thread_message = self.messages.get(thread_ts)
            if thread_message is None:
                # TODO: Fetch message
                return
            if thread_message.thread_buffer is None:
                thread_message.thread_buffer = SlackThread(thread_message)
            await thread_message.thread_buffer.open_buffer(switch)
