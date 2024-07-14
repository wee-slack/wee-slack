from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Optional

import weechat

from slack.shared import shared
from slack.slack_conversation import create_conversation_for_users
from slack.slack_emoji import get_emoji
from slack.slack_user import name_from_user_info
from slack.slack_workspace import SlackWorkspace
from slack.task import run_async
from slack.util import get_callback_name, with_color

if TYPE_CHECKING:
    from slack_api.slack_conversations_info import SlackConversationsInfoPublic
    from slack_api.slack_users_info import SlackUserInfo
    from typing_extensions import Literal, assert_never

    SearchType = Literal["channels", "users"]


@dataclass
class BufferLine:
    type: SearchType
    content: str
    content_id: str


class SlackSearchBuffer:
    def __init__(
        self,
        workspace: SlackWorkspace,
        search_type: SearchType,
        query: Optional[str] = None,
    ):
        self.workspace = workspace
        self.search_type: SearchType = search_type
        self._lines: List[BufferLine] = []
        self._selected_line = 0

        buffer_name = f"{shared.SCRIPT_NAME}.search.{search_type}"
        buffer_props = {
            "type": "free",
            "display": "1",
            "key_bind_up": "/slack search -up",
            "key_bind_down": "/slack search -down",
            "key_bind_meta-j": "/slack search -join_channel",
        }

        if shared.weechat_version >= 0x03050000:
            self.buffer_pointer = weechat.buffer_new_props(
                buffer_name,
                buffer_props,
                get_callback_name(self._buffer_input_cb),
                "",
                get_callback_name(self._buffer_close_cb),
                "",
            )
        else:
            self.buffer_pointer = weechat.buffer_new(
                buffer_name,
                get_callback_name(self._buffer_input_cb),
                "",
                get_callback_name(self._buffer_close_cb),
                "",
            )
            for prop_name, value in buffer_props.items():
                weechat.buffer_set(self.buffer_pointer, prop_name, value)

        if query is not None:
            run_async(self.search(query))

    @property
    def selected_line(self) -> int:
        return self._selected_line

    @selected_line.setter
    def selected_line(self, value: int):
        old_line = self._selected_line
        if value < 0:
            self._selected_line = len(self._lines) - 1
        elif value >= len(self._lines):
            self._selected_line = 0
        else:
            self._selected_line = value
        self.print(old_line)
        self.print(self._selected_line)

    def switch_to_buffer(self):
        weechat.buffer_set(self.buffer_pointer, "display", "1")

    def print(self, y: int):
        if y < 0 or y >= len(self._lines):
            return
        content = self._lines[y].content
        line = (
            with_color(f",{shared.config.color.search_line_selected_bg.value}", content)
            if y == self.selected_line
            else content
        )
        weechat.prnt_y(self.buffer_pointer, y, line)

    def format_channel(
        self, channel_info: SlackConversationsInfoPublic, member_channels: List[str]
    ) -> str:
        prefix = "&" if channel_info["is_private"] else "#"
        name = f"{prefix}{channel_info['name']}"
        joined = " (joined)" if channel_info["id"] in member_channels else ""
        # TODO: Resolve refs
        purpose = channel_info["purpose"]["value"].replace("\n", " ")
        description = f" - Description: {purpose}" if purpose else ""
        return f"{name}{joined}{description}"

    def format_user(self, user_info: SlackUserInfo) -> str:
        name = name_from_user_info(self.workspace, user_info)
        real_name = user_info["profile"].get("real_name", "")
        real_name_str = f" - {real_name}" if real_name else ""

        title = user_info["profile"].get("title", "")
        title_str = f" - Title: {title}" if title else ""

        status_emoji_name = user_info["profile"].get("status_emoji", "")
        status_emoji = (
            get_emoji(status_emoji_name.strip(":")) if status_emoji_name else ""
        )
        status_text = user_info["profile"].get("status_text", "") or ""
        status = f"{status_emoji} {status_text}".strip()
        status_str = f" - Status: {status}" if status else ""

        return f"{name}{real_name_str}{title_str}{status_str}"

    async def search(self, query: str):
        weechat.buffer_clear(self.buffer_pointer)
        self._selected_line = 0
        weechat.prnt_y(self.buffer_pointer, 0, f'Searching for "{query}"...')

        if self.search_type == "channels":
            results = await self.workspace.api.edgeapi.fetch_channels_search(query)
            self._lines = [
                BufferLine(
                    "channels",
                    self.format_channel(channel, results.get("member_channels", [])),
                    channel["id"],
                )
                for channel in results["results"]
            ]
        elif self.search_type == "users":
            results = await self.workspace.api.edgeapi.fetch_users_search(query)
            self._lines = [
                BufferLine("users", self.format_user(user), user["id"])
                for user in results["results"]
            ]
        else:
            assert_never(self.search_type)

        if not self._lines:
            weechat.prnt_y(self.buffer_pointer, 0, "No results found.")
            return

        for i in range(len(self._lines)):
            self.print(i)

    async def join_channel(self):
        if self.search_type == "channels":
            channel_id = self._lines[self.selected_line].content_id
            conversation = await self.workspace.conversations[channel_id]
            await conversation.api.conversations_join(conversation.id)
            await conversation.open_buffer(switch=True)
        elif self.search_type == "users":
            user_ids = [self._lines[self.selected_line].content_id]
            await create_conversation_for_users(self.workspace, user_ids)
        else:
            assert_never(self.search_type)

    def _buffer_input_cb(self, data: str, buffer: str, input_data: str) -> int:
        run_async(self.search(input_data))
        return weechat.WEECHAT_RC_OK

    def _buffer_close_cb(self, data: str, buffer: str) -> int:
        del shared.search_buffers[self.search_type]
        return weechat.WEECHAT_RC_OK
