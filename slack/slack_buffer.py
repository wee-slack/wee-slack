from __future__ import annotations

import re
import time
from abc import ABC, abstractmethod
from contextlib import contextmanager
from typing import (
    TYPE_CHECKING,
    Dict,
    Generator,
    List,
    Mapping,
    Match,
    Optional,
    Set,
    Tuple,
)

import weechat

from slack.log import print_error
from slack.shared import MESSAGE_ID_REGEX_STRING, REACTION_CHANGE_REGEX_STRING, shared
from slack.slack_message import SlackMessage, SlackTs
from slack.slack_user import SlackUser
from slack.task import gather, run_async
from slack.util import get_callback_name, htmlescape

if TYPE_CHECKING:
    from typing_extensions import Literal, assert_never

    from slack.slack_api import SlackApi
    from slack.slack_conversation import SlackConversation
    from slack.slack_workspace import SlackWorkspace

EMOJI_CHAR_REGEX_STRING = "(?P<emoji_char>[\U00000080-\U0010ffff]+)"
EMOJI_NAME_REGEX_STRING = (
    ":(?P<emoji_name>[a-z0-9_+-]+(?:::skin-tone-[2-6](?:-[2-6])?)?):"
)
EMOJI_CHAR_OR_NAME_REGEX_STRING = (
    f"(?:{EMOJI_CHAR_REGEX_STRING}|{EMOJI_NAME_REGEX_STRING})"
)


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
        self.history_pending = False
        self.history_pending_messages: List[SlackMessage] = []
        self.history_needs_refresh = False
        self.last_printed_ts: Optional[SlackTs] = None
        self.hotlist_tss: Set[SlackTs] = set()

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
    def conversation(self) -> SlackConversation:
        raise NotImplementedError()

    @property
    @abstractmethod
    def context(self) -> Literal["conversation", "thread"]:
        raise NotImplementedError()

    @property
    @abstractmethod
    def members(self) -> Generator[SlackUser, None, None]:
        raise NotImplementedError()

    @property
    @abstractmethod
    def messages(self) -> Mapping[SlackTs, SlackMessage]:
        raise NotImplementedError()

    @property
    @abstractmethod
    def last_read(self) -> Optional[SlackTs]:
        raise NotImplementedError()

    @abstractmethod
    def get_name_and_buffer_props(self) -> Tuple[str, Dict[str, str]]:
        raise NotImplementedError()

    async def buffer_switched_to(self) -> None:
        self.hotlist_tss.clear()

    def get_full_name(self, name: str) -> str:
        return f"{shared.SCRIPT_NAME}.{self.workspace.name}.{name}"

    async def open_buffer(self, switch: bool = False):
        if self.buffer_pointer:
            if switch:
                weechat.buffer_set(self.buffer_pointer, "display", "1")
            return

        name, buffer_props = self.get_name_and_buffer_props()
        full_name = self.get_full_name(name)

        buffer_props["highlight_tags"] = (
            f"{buffer_props['highlight_tags']},{shared.highlight_tag}"
            if buffer_props.get("highlight_tags")
            else shared.highlight_tag
        )

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

    def update_buffer_props(self) -> None:
        name, buffer_props = self.get_name_and_buffer_props()
        buffer_props["name"] = self.get_full_name(name)
        for key, value in buffer_props.items():
            weechat.buffer_set(self.buffer_pointer, key, value)

    @abstractmethod
    async def set_hotlist(self) -> None:
        raise NotImplementedError()

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

    async def print_message(self, message: SlackMessage):
        rendered = await message.render(self.context)
        backlog = self.last_read is not None and message.ts <= self.last_read
        tags = await message.tags(backlog)
        weechat.prnt_date_tags(self.buffer_pointer, message.ts.major, tags, rendered)
        if backlog:
            weechat.buffer_set(self.buffer_pointer, "unread", "")
        else:
            self.hotlist_tss.add(message.ts)
        self.last_printed_ts = message.ts

    def last_read_line_ts(self) -> Optional[SlackTs]:
        if self.buffer_pointer:
            own_lines = weechat.hdata_pointer(
                weechat.hdata_get("buffer"), self.buffer_pointer, "own_lines"
            )
            first_line_not_read = weechat.hdata_integer(
                weechat.hdata_get("lines"), own_lines, "first_line_not_read"
            )
            if first_line_not_read:
                return
            line = weechat.hdata_pointer(
                weechat.hdata_get("lines"), own_lines, "last_read_line"
            )
            while line:
                ts = hdata_line_ts(line)
                if ts:
                    return ts
                line = weechat.hdata_move(weechat.hdata_get("line"), line, -1)

    @abstractmethod
    async def mark_read(self) -> None:
        raise NotImplementedError()

    def set_unread_and_hotlist(self):
        if self.buffer_pointer:
            # TODO: Move unread marker to correct position according to last_read for WeeChat >= 4.0.0
            weechat.buffer_set(self.buffer_pointer, "unread", "")
            weechat.buffer_set(self.buffer_pointer, "hotlist", "-1")
            self.hotlist_tss.clear()

    def ts_from_hash(self, ts_hash: str) -> Optional[SlackTs]:
        return self.conversation.message_hashes.get_ts(ts_hash)

    def ts_from_index(
        self, index: int, message_filter: Optional[Literal["sender_self"]] = None
    ) -> Optional[SlackTs]:
        if index < 0:
            return

        lines = weechat.hdata_pointer(
            weechat.hdata_get("buffer"), self.buffer_pointer, "lines"
        )

        line = weechat.hdata_pointer(weechat.hdata_get("lines"), lines, "last_line")
        while line and index:
            if not message_filter:
                index -= 1
            elif message_filter == "sender_self":
                ts = hdata_line_ts(line)
                if ts is not None:
                    message = self.messages[ts]
                    if (
                        message.sender_user_id == self.workspace.my_user.id
                        and message.subtype in [None, "me_message", "thread_broadcast"]
                    ):
                        index -= 1
            else:
                assert_never(message_filter)

            if index == 0:
                break

            line = weechat.hdata_move(weechat.hdata_get("line"), line, -1)

        if line:
            return hdata_line_ts(line)

    def ts_from_hash_or_index(
        self,
        hash_or_index: str,
        message_filter: Optional[Literal["sender_self"]] = None,
    ) -> Optional[SlackTs]:
        if not hash_or_index:
            return self.ts_from_index(1, message_filter)
        elif hash_or_index.isdigit():
            return self.ts_from_index(int(hash_or_index), message_filter)
        else:
            return self.ts_from_hash(hash_or_index)

    @abstractmethod
    async def post_message(self, text: str) -> None:
        raise NotImplementedError()

    async def send_change_reaction(
        self, ts: SlackTs, emoji_char: str, change_type: Literal["+", "-"]
    ) -> None:
        emoji = shared.standard_emojis_inverse.get(emoji_char)
        emoji_name = emoji["name"] if emoji else emoji_char
        await self._api.reactions_change(self.conversation, ts, emoji_name, change_type)

    async def edit_message(self, ts: SlackTs, old: str, new: str, flags: str):
        message = self.messages[ts]

        if new == "" and old == "":
            await self._api.chat_delete_message(self.conversation, message.ts)
        else:
            num_replace = 0 if "g" in flags else 1
            f = re.UNICODE
            f |= re.IGNORECASE if "i" in flags else 0
            f |= re.MULTILINE if "m" in flags else 0
            f |= re.DOTALL if "s" in flags else 0
            old_message_text = message.text
            new_message_text = re.sub(old, new, old_message_text, num_replace, f)
            if new_message_text != old_message_text:
                await self._api.chat_update_message(
                    self.conversation, message.ts, new_message_text
                )
            else:
                print_error("The regex didn't match any part of the message")

    async def linkify_text(self, text: str) -> str:
        escaped_text = (
            htmlescape(text)
            # Replace some WeeChat formatting chars with Slack formatting chars
            .replace("\x02", "*")
            .replace("\x1D", "_")
        )

        users = await gather(*self.workspace.users.values(), return_exceptions=True)
        nick_to_user_id = {
            user.nick(only_nick=True): user.id
            for user in users
            if not isinstance(user, BaseException)
        }

        def linkify_word(match: Match[str]) -> str:
            word = match.group(0)
            nick = match.group(1)
            if nick in nick_to_user_id:
                return "<@{}>".format(nick_to_user_id[nick])
            return word

        linkify_regex = r"(?:^|(?<=\s))@([\w\(\)\'.-]+)"
        return re.sub(linkify_regex, linkify_word, escaped_text, flags=re.UNICODE)

    async def process_input(self, input_data: str):
        special = re.match(
            rf"{MESSAGE_ID_REGEX_STRING}?(?:{REACTION_CHANGE_REGEX_STRING}{EMOJI_CHAR_OR_NAME_REGEX_STRING}\s*|s/)",
            input_data,
        )
        if special:
            msg_id = special.group("msg_id")
            emoji = special.group("emoji_char") or special.group("emoji_name")
            reaction_change_type = special.group("reaction_change")

            message_filter = "sender_self" if not emoji else None
            ts = self.ts_from_hash_or_index(msg_id, message_filter)
            if ts is None:
                print_error(f"No slack message found for message id or index {msg_id}")
                return

            if emoji and (reaction_change_type == "+" or reaction_change_type == "-"):
                await self.send_change_reaction(ts, emoji, reaction_change_type)
            else:
                try:
                    old, new, flags = re.split(r"(?<!\\)/", input_data)[1:]
                except ValueError:
                    print_error(
                        "Incomplete regex for changing a message, "
                        "it should be in the form s/old text/new text/"
                    )
                else:
                    # Replacement string in re.sub() is a string, not a regex, so get rid of escapes
                    new = new.replace(r"\/", "/")
                    old = old.replace(r"\/", "/")
                    await self.edit_message(ts, old, new, flags)
        else:
            if input_data.startswith(("//", " ")):
                input_data = input_data[1:]
            text = await self.linkify_text(input_data)
            await self.post_message(text)

    def _buffer_input_cb(self, data: str, buffer: str, input_data: str) -> int:
        run_async(self.process_input(input_data))
        return weechat.WEECHAT_RC_OK

    def _buffer_close_cb(self, data: str, buffer: str) -> int:
        if self.buffer_pointer in shared.buffers:
            del shared.buffers[self.buffer_pointer]
        self.buffer_pointer = ""
        self.last_printed_ts = None
        self.hotlist_tss.clear()
        return weechat.WEECHAT_RC_OK
