from __future__ import annotations

import time
from abc import ABC, abstractmethod
from contextlib import contextmanager
from typing import TYPE_CHECKING, Dict, List, Mapping, Optional, Tuple

import weechat

from slack.shared import shared
from slack.slack_message import SlackMessage, SlackTs
from slack.util import get_callback_name

if TYPE_CHECKING:
    from typing_extensions import Literal

    from slack.slack_api import SlackApi
    from slack.slack_workspace import SlackWorkspace


def hdata_line_ts(line_pointer: str) -> Optional[SlackTs]:
    data = weechat.hdata_pointer(weechat.hdata_get("line"), line_pointer, "data")
    for i in range(
        weechat.hdata_integer(weechat.hdata_get("line_data"), data, "tags_count")
    ):
        tag = weechat.hdata_string(
            weechat.hdata_get("line_data"), data, f"{i}|tags_array"
        )
        if tag.startswith("slack_ts_"):
            return SlackTs(tag[9:])
    return None


def tags_set_notify_none(tags: List[str]) -> List[str]:
    notify_tags = {"notify_highlight", "notify_message", "notify_private"}
    tags = [tag for tag in tags if tag not in notify_tags]
    tags += ["no_highlight", "notify_none"]
    return tags


def modify_buffer_line(buffer_pointer: str, ts: SlackTs, new_text: str):
    own_lines = weechat.hdata_pointer(
        weechat.hdata_get("buffer"), buffer_pointer, "own_lines"
    )
    line_pointer = weechat.hdata_pointer(
        weechat.hdata_get("lines"), own_lines, "last_line"
    )

    # Find the last line with this ts
    is_last_line = True
    while line_pointer and hdata_line_ts(line_pointer) != ts:
        is_last_line = False
        line_pointer = weechat.hdata_move(weechat.hdata_get("line"), line_pointer, -1)

    if not line_pointer:
        return

    if shared.weechat_version >= 0x04000000:
        data = weechat.hdata_pointer(weechat.hdata_get("line"), line_pointer, "data")
        weechat.hdata_update(
            weechat.hdata_get("line_data"), data, {"message": new_text}
        )
        return

    # Find all lines for the message
    pointers: List[str] = []
    while line_pointer and hdata_line_ts(line_pointer) == ts:
        pointers.append(line_pointer)
        line_pointer = weechat.hdata_move(weechat.hdata_get("line"), line_pointer, -1)
    pointers.reverse()

    if not pointers:
        return

    if is_last_line:
        lines = new_text.split("\n")
        extra_lines_count = len(lines) - len(pointers)
        if extra_lines_count > 0:
            line_data = weechat.hdata_pointer(
                weechat.hdata_get("line"), pointers[0], "data"
            )
            tags_count = weechat.hdata_integer(
                weechat.hdata_get("line_data"), line_data, "tags_count"
            )
            tags = [
                weechat.hdata_string(
                    weechat.hdata_get("line_data"), line_data, f"{i}|tags_array"
                )
                for i in range(tags_count)
            ]
            tags = tags_set_notify_none(tags)
            tags_str = ",".join(tags)
            last_read_line = weechat.hdata_pointer(
                weechat.hdata_get("lines"), own_lines, "last_read_line"
            )
            should_set_unread = last_read_line == pointers[-1]

            # Insert new lines to match the number of lines in the message
            weechat.buffer_set(buffer_pointer, "print_hooks_enabled", "0")
            for _ in range(extra_lines_count):
                weechat.prnt_date_tags(buffer_pointer, ts.major, tags_str, " \t ")
                pointers.append(
                    weechat.hdata_pointer(
                        weechat.hdata_get("lines"), own_lines, "last_line"
                    )
                )
            if should_set_unread:
                weechat.buffer_set(buffer_pointer, "unread", "")
            weechat.buffer_set(buffer_pointer, "print_hooks_enabled", "1")
    else:
        # Split the message into at most the number of existing lines as we can't insert new lines
        lines = new_text.split("\n", len(pointers) - 1)
        # Replace newlines to prevent garbled lines in bare display mode
        lines = [line.replace("\n", " | ") for line in lines]

    # Extend lines in case the new message is shorter than the old as we can't delete lines
    lines += [""] * (len(pointers) - len(lines))

    for pointer, line in zip(pointers, lines):
        data = weechat.hdata_pointer(weechat.hdata_get("line"), pointer, "data")
        weechat.hdata_update(weechat.hdata_get("line_data"), data, {"message": line})


class SlackBuffer(ABC):
    def __init__(self):
        self._typing_self_last_sent = 0
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

    @property
    @abstractmethod
    def workspace(self) -> SlackWorkspace:
        raise NotImplementedError()

    @property
    @abstractmethod
    def context(self) -> Literal["conversation", "thread"]:
        raise NotImplementedError()

    @property
    @abstractmethod
    def messages(self) -> Mapping[SlackTs, SlackMessage]:
        raise NotImplementedError()

    @abstractmethod
    async def get_name_and_buffer_props(self) -> Tuple[str, Dict[str, str]]:
        raise NotImplementedError()

    @abstractmethod
    async def buffer_switched_to(self) -> None:
        raise NotImplementedError()

    def get_full_name(self, name: str) -> str:
        return f"{shared.SCRIPT_NAME}.{self.workspace.name}.{name}"

    async def open_buffer(self, switch: bool = False):
        if self.buffer_pointer:
            if switch:
                weechat.buffer_set(self.buffer_pointer, "display", "1")
            return

        name, buffer_props = await self.get_name_and_buffer_props()
        full_name = self.get_full_name(name)

        if switch:
            buffer_props["display"] = "1"

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

        shared.buffers[self.buffer_pointer] = self
        if switch:
            await self.buffer_switched_to()

    async def update_buffer_props(self) -> None:
        name, buffer_props = await self.get_name_and_buffer_props()
        buffer_props["name"] = self.get_full_name(name)
        for key, value in buffer_props.items():
            weechat.buffer_set(self.buffer_pointer, key, value)

    async def rerender_message(self, message: SlackMessage):
        modify_buffer_line(
            self.buffer_pointer,
            message.ts,
            await message.render_message(context=self.context, rerender=True),
        )

    async def rerender_history(self):
        for message in self.messages.values():
            await self.rerender_message(message)

    def set_typing_self(self):
        now = time.time()
        if now - 4 > self._typing_self_last_sent:
            self._typing_self_last_sent = now
            self.workspace.send_typing(self)

    async def print_message(self, message: SlackMessage, backlog: bool = False):
        rendered = await message.render(self.context)
        tags = await message.tags(backlog=backlog)
        weechat.prnt_date_tags(self.buffer_pointer, message.ts.major, tags, rendered)

    def _buffer_input_cb(self, data: str, buffer: str, input_data: str) -> int:
        weechat.prnt(buffer, "Text: %s" % input_data)
        return weechat.WEECHAT_RC_OK

    def _buffer_close_cb(self, data: str, buffer: str) -> int:
        if self.buffer_pointer in shared.buffers:
            del shared.buffers[self.buffer_pointer]
        self.buffer_pointer = ""
        self.history_filled = False
        return weechat.WEECHAT_RC_OK
