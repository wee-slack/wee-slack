from __future__ import annotations

import time
from collections import OrderedDict
from contextlib import contextmanager
from typing import TYPE_CHECKING, List, Optional

import weechat

from slack.shared import shared
from slack.slack_message import SlackMessage, SlackTs
from slack.task import gather
from slack.util import get_callback_name

if TYPE_CHECKING:
    from slack_api.slack_conversations_info import SlackConversationsInfo
    from typing_extensions import Literal

    from slack.slack_api import SlackApi
    from slack.slack_workspace import SlackWorkspace


def get_conversation_from_buffer_pointer(
    buffer_pointer: str,
) -> Optional[SlackConversation]:
    for workspace in shared.workspaces.values():
        for conversation in workspace.open_conversations.values():
            if conversation.buffer_pointer == buffer_pointer:
                return conversation
    return None


class SlackConversation:
    def __init__(
        self,
        workspace: SlackWorkspace,
        info: SlackConversationsInfo,
    ):
        self.workspace = workspace
        self._info = info
        self._members: Optional[List[str]] = None
        self._messages: OrderedDict[SlackTs, SlackMessage] = OrderedDict()
        # TODO: buffer_pointer may be accessed by buffer_switch before it's initialized
        self.buffer_pointer: str = ""
        self.is_loading = False
        self.history_filled = False
        self.history_pending = False

        self.completion_context: Literal[
            "NO_COMPLETION",
            "PENDING_COMPLETION",
            "ACTIVE_COMPLETION",
            "IN_PROGRESS_COMPLETION",
        ] = "NO_COMPLETION"
        self.completion_values: List[str] = []
        self.completion_index = 0

    @classmethod
    async def create(cls, workspace: SlackWorkspace, conversation_id: str):
        info_response = await workspace.api.fetch_conversations_info(conversation_id)
        return cls(workspace, info_response["channel"])

    @property
    def _api(self) -> SlackApi:
        return self.workspace.api

    @property
    def id(self) -> str:
        return self._info["id"]

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

    async def name(self) -> str:
        if self._info["is_im"] is True:
            im_user = await self.workspace.users[self._info["user"]]
            return im_user.nick()
        elif self._info["is_mpim"] is True:
            if self._members is None:
                members_response = await self._api.fetch_conversations_members(self)
                self._members = members_response["members"]
                await self.workspace.users.initialize_items(self._members)
            member_users = await gather(
                *(self.workspace.users[user_id] for user_id in self._members)
            )
            return ",".join([user.nick() for user in member_users])
        else:
            return self._info["name"]

    def name_prefix(self, name_type: Literal["full_name", "short_name"]) -> str:
        if self._info["is_im"] is True:
            if name_type == "short_name":
                return " "
            else:
                return ""
        elif self._info["is_mpim"]:
            if name_type == "short_name":
                return "@"
            else:
                return ""
        else:
            return "#"

    @contextmanager
    def loading(self):
        self.is_loading = True
        weechat.bar_item_update("input_text")
        try:
            yield
        finally:
            self.is_loading = False
            weechat.bar_item_update("input_text")

    @contextmanager
    def completing(self):
        self.completion_context = "IN_PROGRESS_COMPLETION"
        try:
            yield
        finally:
            self.completion_context = "ACTIVE_COMPLETION"

    async def open_if_open(self):
        if "is_open" in self._info:
            if self._info["is_open"]:
                await self.open_buffer()
        elif self._info.get("is_member"):
            await self.open_buffer()

    async def open_buffer(self):
        if self.buffer_pointer:
            return

        name = await self.name()
        name_with_prefix_for_full_name = f"{self.name_prefix('full_name')}{name}"
        full_name = f"{shared.SCRIPT_NAME}.{self.workspace.name}.{name_with_prefix_for_full_name}"
        short_name = self.name_prefix("short_name") + name

        buffer_props = {
            "short_name": short_name,
            "title": "topic",
            "input_multiline": "1",
            "localvar_set_type": (
                "private" if self.type in ("im", "mpim") else "channel"
            ),
            "localvar_set_slack_type": self.type,
            "localvar_set_nick": self.workspace.my_user.nick(),
            "localvar_set_channel": name_with_prefix_for_full_name,
            "localvar_set_server": self.workspace.name,
        }

        if shared.weechat_version >= 0x03050000:
            self.buffer_pointer = weechat.buffer_new_props(
                full_name,
                buffer_props,
                get_callback_name(self._buffer_input_cb),
                "",
                get_callback_name(self._buffer_close_cb),
                "",
            )
        else:
            self.buffer_pointer = weechat.buffer_new(
                full_name,
                get_callback_name(self._buffer_input_cb),
                "",
                get_callback_name(self._buffer_close_cb),
                "",
            )
            for prop_name, value in buffer_props.items():
                weechat.buffer_set(self.buffer_pointer, prop_name, value)

        self.workspace.open_conversations[self.id] = self

    async def fill_history(self):
        if self.history_filled or self.history_pending:
            return

        with self.loading():
            self.history_pending = True

            history = await self._api.fetch_conversations_history(self)
            start = time.time()

            messages = [SlackMessage(self, message) for message in history["messages"]]
            for message in messages:
                self._messages[message.ts] = message

            sender_user_ids = [m.sender_user_id for m in messages if m.sender_user_id]
            await self.workspace.users.initialize_items(sender_user_ids)

            await gather(*(message.render() for message in messages))

            for message in reversed(messages):
                self.print_message(message, await message.render())

            print(f"history w/o fetch took: {time.time() - start}")
            self.history_filled = True
            self.history_pending = False

    async def add_message(self, message: SlackMessage):
        self._messages[message.ts] = message
        if self.history_filled:
            rendered = await message.render()
            self.print_message(message, rendered)
        else:
            weechat.buffer_set(
                self.buffer_pointer, "hotlist", str(message.priority.value)
            )

    def print_message(self, message: SlackMessage, rendered: str):
        weechat.prnt_date_tags(self.buffer_pointer, message.ts.major, "", rendered)

    def _buffer_input_cb(self, data: str, buffer: str, input_data: str) -> int:
        weechat.prnt(buffer, "Text: %s" % input_data)
        return weechat.WEECHAT_RC_OK

    def _buffer_close_cb(self, data: str, buffer: str) -> int:
        self.buffer_pointer = ""
        self.history_filled = False
        return weechat.WEECHAT_RC_OK
