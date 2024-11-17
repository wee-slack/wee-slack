from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Optional, Set

import weechat

from slack.shared import shared
from slack.slack_buffer import SlackBuffer
from slack.slack_conversation import create_conversation_for_users
from slack.slack_emoji import get_emoji
from slack.slack_user import name_from_user_info
from slack.slack_workspace import SlackWorkspace
from slack.task import run_async
from slack.util import with_color
from slack.weechat_buffer import buffer_new

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


class SlackSearchBuffer(SlackBuffer):
    def __init__(
        self,
        workspace: SlackWorkspace,
        search_type: SearchType,
        query: Optional[str] = None,
    ):
        super().__init__()
        self._workspace = workspace
        self.search_type: SearchType = search_type
        self._query = query or ""
        self._lines: List[BufferLine] = []
        self._marked_lines: Set[int] = set()
        self._selected_line = 0
        run_async(self.open_buffer(switch=True, query=query))

    @property
    def workspace(self) -> SlackWorkspace:
        return self._workspace

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

    async def open_buffer(
        self,
        switch: bool = False,
        query: Optional[str] = None,
    ):
        if self._buffer_pointer is None:
            buffer_name = (
                f"{shared.SCRIPT_NAME}.search.{self.workspace.name}.{self.search_type}"
            )
            buffer_props = {
                "type": "free",
                "display": "1",
                "key_bind_up": "/slack search -up",
                "key_bind_down": "/slack search -down",
                "key_bind_ctrl-j": "/slack search -join_channel",
                "key_bind_meta-comma": "/slack search -mark",
                "key_bind_shift-up": "/slack search -up; /slack search -mark",
                "key_bind_shift-down": "/slack search -mark; /slack search -down",
            }

            self._buffer_pointer = buffer_new(
                buffer_name,
                buffer_props,
                self._buffer_input_cb,
                self._buffer_close_cb,
            )
            shared.buffers[self._buffer_pointer] = self

        if switch:
            weechat.buffer_set(self._buffer_pointer, "display", "1")

        if query is not None:
            self._query = query
            await self.search()

    def update_title(self, searching: bool = False):
        if self.buffer_pointer is None:
            return

        matches = (
            "Searching"
            if searching
            else f"First {len(self._lines)} matching {self.search_type}"
        )
        title = f"{matches} | Filter: {self._query or '*'} | Key(input): ctrl+j=join channel, ($)=refresh, (q)=close buffer"
        weechat.buffer_set(self.buffer_pointer, "title", title)

    def mark_line(self, y: int):
        if y < 0 or y >= len(self._lines):
            return
        if y in self._marked_lines:
            self._marked_lines.remove(y)
        else:
            self._marked_lines.add(y)
        self.print(y)

    def print(self, y: int):
        if self.buffer_pointer is None:
            return
        if y < 0 or y >= len(self._lines):
            return

        line_is_selected = y == self.selected_line
        line_is_marked = y in self._marked_lines
        marked_color = (
            shared.config.color.search_marked_selected.value
            if line_is_selected
            else shared.config.color.search_marked.value
        )
        selected_color_bg = (
            shared.config.color.search_line_selected_bg.value
            if line_is_selected
            else shared.config.color.search_line_marked_bg.value
            if line_is_marked
            else None
        )

        marked = with_color(marked_color, "* ") if line_is_marked else "  "
        line = with_color(
            f",{selected_color_bg}" if selected_color_bg is not None else None,
            f"{marked}{self._lines[y].content}",
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

    async def search(self, query: Optional[str] = None):
        if self.buffer_pointer is None:
            return
        if query is not None:
            self._query = query

        self.update_title(searching=True)

        marked_lines = [self._lines[line] for line in self._marked_lines]
        marked_lines_ids = {line.content_id for line in marked_lines}
        weechat.buffer_clear(self.buffer_pointer)
        self._selected_line = 0
        weechat.prnt_y(self.buffer_pointer, 0, f'Searching for "{self._query}"...')

        if self.search_type == "channels":
            results = await self.workspace.api.edgeapi.fetch_channels_search(
                self._query
            )
            self._lines = marked_lines + [
                BufferLine(
                    "channels",
                    self.format_channel(channel, results.get("member_channels", [])),
                    channel["id"],
                )
                for channel in results["results"]
                if channel["id"] not in marked_lines_ids
            ]
        elif self.search_type == "users":
            results = await self.workspace.api.edgeapi.fetch_users_search(self._query)
            self._lines = marked_lines + [
                BufferLine("users", self.format_user(user), user["id"])
                for user in results["results"]
                if user["id"] not in marked_lines_ids
            ]
        else:
            assert_never(self.search_type)
        self._marked_lines = set(range(len(marked_lines)))

        self.update_title()

        if not self._lines:
            weechat.prnt_y(self.buffer_pointer, 0, "No results found.")
            return

        for i in range(len(self._lines)):
            self.print(i)

    async def join_channel(self):
        marked_lines = (
            self._marked_lines if self._marked_lines else {self.selected_line}
        )
        if self.search_type == "channels":
            for line in marked_lines:
                channel_id = self._lines[line].content_id
                conversation = await self.workspace.conversations[channel_id]
                await conversation.api.conversations_join(conversation.id)
                await conversation.open_buffer(switch=True)
        elif self.search_type == "users":
            user_ids = [self._lines[line].content_id for line in marked_lines]
            await create_conversation_for_users(self.workspace, user_ids)
        else:
            assert_never(self.search_type)

    def _buffer_input_cb(self, data: str, buffer: str, input_data: str) -> int:
        if input_data == "q":
            weechat.buffer_close(buffer)
            return weechat.WEECHAT_RC_OK
        elif input_data == "$":
            run_async(self.search())
            return weechat.WEECHAT_RC_OK

        query = "" if input_data == "*" else input_data
        run_async(self.search(query))
        return weechat.WEECHAT_RC_OK

    def _buffer_close_cb(self, data: str, buffer: str) -> int:
        del self.workspace.search_buffers[self.search_type]

        if self.buffer_pointer in shared.buffers:
            del shared.buffers[self.buffer_pointer]

        self._buffer_pointer = None

        return weechat.WEECHAT_RC_OK
