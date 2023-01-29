from __future__ import annotations

import time
from contextlib import contextmanager
from typing import TYPE_CHECKING, List, Optional

import weechat

from slack.shared import shared
from slack.slack_message import SlackMessage
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

    async def name(self) -> str:
        if "is_im" in self._info and self._info["is_im"] is True:
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
        if "is_im" in self._info and self._info["is_im"] is True:
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
        name = await self.name()
        full_name = f"{shared.SCRIPT_NAME}.{self.workspace.name}.{self.name_prefix('full_name')}{name}"
        short_name = self.name_prefix("short_name") + name

        self.buffer_pointer = weechat.buffer_new(
            full_name, get_callback_name(self.buffer_input_cb), "", "", ""
        )
        weechat.buffer_set(self.buffer_pointer, "short_name", short_name)
        weechat.buffer_set(
            self.buffer_pointer, "localvar_set_nick", self.workspace.my_user.nick()
        )

        self.workspace.open_conversations[self.id] = self

    async def fill_history(self):
        if self.history_filled or self.history_pending:
            return

        with self.loading():
            self.history_pending = True

            history = await self._api.fetch_conversations_history(self)
            start = time.time()

            messages = [SlackMessage(self, message) for message in history["messages"]]

            sender_user_ids = [m.sender_user_id for m in messages if m.sender_user_id]
            await self.workspace.users.initialize_items(sender_user_ids)

            messages_rendered = await gather(
                *(message.render_message() for message in messages)
            )

            for rendered in reversed(messages_rendered):
                weechat.prnt(self.buffer_pointer, rendered)

            print(f"history w/o fetch took: {time.time() - start}")
            self.history_filled = True
            self.history_pending = False

    def buffer_input_cb(self, data: str, buffer: str, input_data: str) -> int:
        weechat.prnt(buffer, "Text: %s" % input_data)
        return weechat.WEECHAT_RC_OK
