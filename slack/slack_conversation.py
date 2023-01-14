from __future__ import annotations

import time
from contextlib import contextmanager
from typing import TYPE_CHECKING, Optional

import weechat

from slack.shared import shared
from slack.slack_message import SlackMessage
from slack.task import gather
from slack.util import get_callback_name

if TYPE_CHECKING:
    from slack_api import SlackConversationInfoResponse

    from slack.slack_workspace import SlackApi, SlackWorkspace


def get_conversation_from_buffer_pointer(
    buffer_pointer: str,
) -> Optional[SlackConversation]:
    for workspace in shared.workspaces.values():
        for conversation in workspace.conversations.values():
            if conversation.buffer_pointer == buffer_pointer:
                return conversation
    return None


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
        if info["ok"] != True:
            # TODO: Handle error
            return

        info_channel = info["channel"]
        if info_channel["is_im"] == True:
            self.name = "IM"  # TODO
        elif info_channel["is_mpim"] == True:
            self.name = "MPIM"  # TODO
        else:
            self.name = info_channel["name"]

        self.buffer_pointer = weechat.buffer_new(
            self.name, get_callback_name(buffer_input_cb), "", "", ""
        )
        weechat.buffer_set(self.buffer_pointer, "localvar_set_nick", "nick")

    async def fetch_info(self) -> SlackConversationInfoResponse:
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
