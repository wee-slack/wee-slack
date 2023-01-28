from __future__ import annotations

import time
from contextlib import contextmanager
from typing import TYPE_CHECKING, List, Optional, Union

import weechat

from slack.shared import shared
from slack.slack_message import SlackMessage
from slack.task import gather
from slack.util import get_callback_name

if TYPE_CHECKING:
    from typing_extensions import Literal

    from slack.slack_api import SlackApi
    from slack.slack_workspace import SlackWorkspace


def get_conversation_from_buffer_pointer(
    buffer_pointer: str,
) -> Optional[SlackConversation]:
    for workspace in shared.workspaces.values():
        for conversation in workspace.conversations.values():
            if conversation.buffer_pointer == buffer_pointer:
                return conversation
    return None


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

        self.completion_context: Union[
            Literal["NO_COMPLETION"],
            Literal["PENDING_COMPLETION"],
            Literal["ACTIVE_COMPLETION"],
            Literal["IN_PROGRESS_COMPLETION"],
        ] = "NO_COMPLETION"
        self.completion_values: List[str] = []
        self.completion_index = 0

    @property
    def _api(self) -> SlackApi:
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

    @contextmanager
    def completing(self):
        self.completion_context = "IN_PROGRESS_COMPLETION"
        try:
            yield
        finally:
            self.completion_context = "ACTIVE_COMPLETION"

    async def init(self):
        with self.loading():
            info = await self._api.fetch_conversations_info(self)

        info_channel = info["channel"]
        if info_channel["is_im"] is True:
            self.name = "IM"  # TODO
        elif info_channel["is_mpim"] is True:
            self.name = "MPIM"  # TODO
        else:
            self.name = info_channel["name"]

        full_name = f"{shared.SCRIPT_NAME}.{self.workspace.name}.{self.name}"

        self.buffer_pointer = weechat.buffer_new(
            full_name, get_callback_name(self.buffer_input_cb), "", "", ""
        )
        weechat.buffer_set(self.buffer_pointer, "short_name", self.name)
        weechat.buffer_set(
            self.buffer_pointer, "localvar_set_nick", self.workspace.my_user.nick()
        )

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
