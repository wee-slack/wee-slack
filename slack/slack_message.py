from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from enum import Enum
from typing import (
    TYPE_CHECKING,
    Generator,
    Iterable,
    List,
    Mapping,
    Match,
    Optional,
    Union,
)

import weechat

from slack.error import (
    SlackApiError,
    SlackError,
    UncaughtError,
    store_and_format_uncaught_error,
    store_uncaught_error,
)
from slack.log import print_error
from slack.python_compatibility import removeprefix, removesuffix
from slack.shared import shared
from slack.slack_emoji import get_emoji
from slack.slack_user import (
    Nick,
    get_bot_nick,
    get_user_nick,
    name_from_user_profile,
    nick_color,
)
from slack.task import gather
from slack.util import htmlescape, intersperse, unhtmlescape, with_color

if TYPE_CHECKING:
    from slack_api.slack_conversations_history import SlackMessage as SlackMessageDict
    from slack_api.slack_conversations_history import (
        SlackMessageBlock,
        SlackMessageBlockCompositionText,
        SlackMessageBlockElementImage,
        SlackMessageBlockRichTextElement,
        SlackMessageBlockRichTextList,
        SlackMessageBlockRichTextSection,
        SlackMessageReaction,
        SlackMessageSubtypeHuddleThreadRoom,
    )
    from slack_api.slack_files_info import SlackFile
    from slack_rtm.slack_rtm_message import SlackThreadSubscription
    from typing_extensions import Literal, assert_never

    from slack.slack_conversation import SlackConversation
    from slack.slack_thread import SlackThread
    from slack.slack_workspace import SlackWorkspace

    MessageContext = Literal["conversation", "thread"]
else:
    MessageContext = str

ts_tag_prefix = "slack_ts_"


def format_date(timestamp: int, token_string: str, link: Optional[str] = None) -> str:
    ref_datetime = datetime.fromtimestamp(timestamp)
    token_to_format = {
        "date_num": "%Y-%m-%d",
        "date": "%B %d, %Y",
        "date_short": "%b %d, %Y",
        "date_long": "%A, %B %d, %Y",
        "time": "%H:%M",
        "time_secs": "%H:%M:%S",
    }

    def replace_token(match: Match[str]):
        token = match.group(1)
        if token.startswith("date_") and token.endswith("_pretty"):
            if ref_datetime.date() == date.today():
                return "today"
            elif ref_datetime.date() == date.today() - timedelta(days=1):
                return "yesterday"
            elif ref_datetime.date() == date.today() + timedelta(days=1):
                return "tomorrow"
            else:
                token = token.replace("_pretty", "")
        if token in token_to_format:
            return ref_datetime.strftime(token_to_format[token])
        else:
            return match.group(0)

    formatted_date = re.sub(r"{([^}]+)}", replace_token, token_string)
    if link is not None:
        return format_url(link, formatted_date)
    else:
        return formatted_date


def format_url(url: str, text: Optional[str] = None) -> str:
    return weechat.string_eval_expression(
        shared.config.look.render_url_as.value,
        {},
        {"url": url, "text": text or ""},
        {},
    )


def convert_int_to_letter(num: int) -> str:
    letter = ""
    while num > 0:
        num -= 1
        letter = chr((num % 26) + 97) + letter
        num //= 26
    return letter


def convert_int_to_roman(num: int) -> str:
    roman_numerals = {
        1000: "m",
        900: "cm",
        500: "d",
        400: "cd",
        100: "c",
        90: "xc",
        50: "l",
        40: "xl",
        10: "x",
        9: "ix",
        5: "v",
        4: "iv",
        1: "i",
    }
    roman_numeral = ""
    for value, symbol in roman_numerals.items():
        while num >= value:
            roman_numeral += symbol
            num -= value
    return roman_numeral


def ts_from_tag(tag: str) -> Optional[SlackTs]:
    if tag.startswith(ts_tag_prefix):
        return SlackTs(tag[len(ts_tag_prefix) :])
    return None


def is_not_found_error(e: Union[SlackApiError, SlackError]) -> bool:
    return (
        isinstance(e, SlackApiError)
        and e.response["error"]
        in ["channel_not_found", "user_not_found", "bot_not_found"]
        or isinstance(e, SlackError)
        and e.error in ["item_not_found", "usergroup_not_found"]
    )


class MessagePriority(Enum):
    NONE = "none"
    LOW = weechat.WEECHAT_HOTLIST_LOW
    MESSAGE = weechat.WEECHAT_HOTLIST_MESSAGE
    PRIVATE = weechat.WEECHAT_HOTLIST_PRIVATE
    HIGHLIGHT = weechat.WEECHAT_HOTLIST_HIGHLIGHT


class SlackTs(str):
    def __init__(self, ts: str):
        self.major, self.minor = [int(x) for x in ts.split(".", maxsplit=1)]

    def __hash__(self) -> int:
        return hash((self.major, self.minor))

    def __repr__(self) -> str:
        return f"SlackTs('{self}')"

    def _cmp(self, other: object) -> int:
        if isinstance(other, str):
            other = SlackTs(other)
        if not isinstance(other, SlackTs):
            return NotImplemented
        elif self.major > other.major:
            return 1
        elif self.major < other.major:
            return -1
        elif self.minor > other.minor:
            return 1
        elif self.minor < other.minor:
            return -1
        else:
            return 0

    def __eq__(self, other: object) -> bool:
        return self._cmp(other) == 0

    def __ne__(self, other: object) -> bool:
        return self._cmp(other) != 0

    def __gt__(self, other: object) -> bool:
        return self._cmp(other) == 1

    def __ge__(self, other: object) -> bool:
        return self._cmp(other) >= 0

    def __lt__(self, other: object) -> bool:
        return self._cmp(other) == -1

    def __le__(self, other: object) -> bool:
        return self._cmp(other) <= 0


class PendingMessageItem:
    def __init__(
        self,
        message: SlackMessage,
        item_type: Literal[
            "conversation", "user", "usergroup", "broadcast", "message_nick", "file"
        ],
        item_id: str,
        display_type: Literal["mention", "chat"] = "mention",
        fallback_name: Optional[str] = None,
        file: Optional[SlackFile] = None,
    ):
        self.message = message
        self.item_type: Literal[
            "conversation", "user", "usergroup", "broadcast", "message_nick", "file"
        ] = item_type
        self.item_id = item_id
        self.display_type: Literal["mention", "chat"] = display_type
        self.fallback_name = fallback_name
        self.file = file

    def __repr__(self):
        return f"{self.__class__.__name__}({self.message}, {self.item_type}, {self.item_id}, {self.display_type})"

    async def resolve(self) -> str:
        if self.item_type == "conversation":
            try:
                conversation = await self.message.workspace.conversations[self.item_id]
                name = conversation.name_with_prefix("short_name_without_padding")
            except (SlackApiError, SlackError) as e:
                if is_not_found_error(e):
                    name = (
                        f"#{self.fallback_name}"
                        if self.fallback_name
                        else "#<private channel>"
                    )
                else:
                    raise e
            if self.display_type == "mention":
                color = shared.config.color.channel_mention.value
            elif self.display_type == "chat":
                color = "chat_channel"
            else:
                assert_never(self.display_type)
            return with_color(color, name)

        elif self.item_type == "user":
            try:
                user = await self.message.workspace.users[self.item_id]
            except (SlackApiError, SlackError) as e:
                if is_not_found_error(e):
                    name = (
                        f"@{self.fallback_name}"
                        if self.fallback_name
                        else f"@{self.item_id}"
                    )
                    return name
                else:
                    raise e

            if self.display_type == "mention":
                name = f"@{user.nick.format()}"
                color = (
                    user.nick.color
                    if shared.config.color.user_mention_nick_color.value
                    else shared.config.color.user_mention.value
                )
                return with_color(color, name)
            elif self.display_type == "chat":
                return user.nick.format(colorize=True)
            else:
                assert_never(self.display_type)

        elif self.item_type == "usergroup":
            try:
                usergroup = await self.message.workspace.usergroups[self.item_id]
                name = f"@{usergroup.handle()}"
            except (SlackApiError, SlackError) as e:
                if (
                    isinstance(e, SlackApiError)
                    and e.response["error"] == "invalid_auth"
                    or is_not_found_error(e)
                ):
                    name = (
                        self.fallback_name if self.fallback_name else f"@{self.item_id}"
                    )
                else:
                    raise e
            return with_color(shared.config.color.usergroup_mention.value, name)

        elif self.item_type == "broadcast":
            broadcast_name = self.item_id.replace("group", "channel")
            name = f"@{broadcast_name}"
            return with_color(shared.config.color.usergroup_mention.value, name)

        elif self.item_type == "message_nick":
            nick = await self.message.nick()
            return nick.format(colorize=True)

        elif self.item_type == "file":
            if self.file is None or self.file.get("file_access") == "check_file_info":
                file_response = await self.message.workspace.api.fetch_files_info(
                    self.item_id
                )
                file = file_response["file"]
            else:
                file = self.file

            if file.get("mode") == "tombstone":
                return with_color(
                    shared.config.color.deleted_message.value,
                    "(This file was deleted)",
                )
            elif file.get("mode") == "hidden_by_limit":
                return with_color(
                    shared.config.color.deleted_message.value,
                    "(This file is not available because the workspace has passed its storage limit)",
                )
            elif file.get("file_access") == "file_not_found":
                return with_color(
                    shared.config.color.deleted_message.value,
                    "(This file was not found)",
                )
            elif (
                file.get("mimetype") == "application/vnd.slack-docs"
                and "permalink" in file
            ):
                url = f"{file['permalink']}?origin_team={self.message.workspace.id}&origin_channel={self.message.conversation.id}"
                title = unhtmlescape(file.get("title", ""))
                return format_url(url, title)
            elif "url_private" in file:
                title = unhtmlescape(file.get("title", ""))
                return format_url(file["url_private"], title)
            else:
                error = SlackError(self.message.workspace, "Unsupported file", file)
                uncaught_error = UncaughtError(error)
                store_uncaught_error(uncaught_error)
                return with_color(
                    shared.config.color.render_error.value,
                    f"<Unsupported file, error id: {uncaught_error.id}>",
                )

        else:
            assert_never(self.item_type)

    def should_highlight(
        self, *, only_mention: bool = False, only_personal: bool = False
    ) -> bool:
        if only_mention and self.display_type != "mention":
            return False

        if self.item_type == "conversation":
            return False
        elif self.item_type == "user":
            return self.item_id == self.message.workspace.my_user.id
        elif self.item_type == "usergroup":
            return self.item_id in self.message.workspace.usergroups_member
        elif self.item_type == "broadcast":
            # TODO: figure out how to handle here broadcast
            return not only_personal
        elif self.item_type == "message_nick":
            return False
        elif self.item_type == "file":
            return False
        else:
            assert_never(self.item_type)


class SlackMessage:
    def __init__(self, conversation: SlackConversation, message_json: SlackMessageDict):
        self._message_json = message_json
        self._rendered_prefix = None
        self._rendered_message = None
        self._parsed_message: Optional[List[Union[str, PendingMessageItem]]] = None
        self.conversation = conversation
        self.ts = SlackTs(message_json["ts"])
        self.replies_tss: List[SlackTs] = []
        self._replies = SlackMessageReplies(self)
        self.reply_history_filled = False
        self.thread_buffer: Optional[SlackThread] = None
        self._last_thread_notify: SlackTs = SlackTs("0.0")
        self._deleted = False

        # Only subscribed threads have the last_read property, so for other
        # threads set it to the latest_reply ts if it exists, so existing
        # messages are considered read, but new messages are not.
        self._last_read = (
            SlackTs(self._message_json["last_read"])
            if "last_read" in self._message_json
            else SlackTs(self.latest_reply)
            if self.latest_reply
            else self.ts
        )

    def __repr__(self):
        return f"{self.__class__.__name__}({self.conversation}, {self.ts})"

    @property
    def message_json(self) -> SlackMessageDict:
        return self._message_json

    @property
    def workspace(self) -> SlackWorkspace:
        return self.conversation.workspace

    @property
    def hash(self) -> str:
        return self.conversation.message_hashes[self.ts]

    @property
    def subtype(self):
        if "subtype" in self._message_json:
            return self._message_json["subtype"]

    @property
    def thread_ts(self) -> Optional[SlackTs]:
        return (
            SlackTs(self._message_json["thread_ts"])
            if "thread_ts" in self._message_json
            else None
        )

    @property
    def is_thread_parent(self) -> bool:
        return self.thread_ts == self.ts

    @property
    def is_reply(self) -> bool:
        return self.thread_ts is not None and not self.is_thread_parent

    @property
    def is_thread_broadcast(self) -> bool:
        return self._message_json.get("subtype") == "thread_broadcast"

    @property
    def parent_message(self) -> Optional[SlackMessage]:
        if not self.is_reply or self.thread_ts is None:
            return None
        return self.conversation.messages.get(self.thread_ts)

    @property
    def subscribed(self) -> bool:
        return self._message_json.get("subscribed", False)

    @property
    def last_read(self) -> SlackTs:
        return self._last_read

    @last_read.setter
    def last_read(self, value: SlackTs):
        self._last_read = value
        if self.thread_buffer:
            self.thread_buffer.set_unread_and_hotlist()

    @property
    def latest_reply(self) -> Optional[SlackTs]:
        if "latest_reply" in self._message_json:
            return SlackTs(self._message_json["latest_reply"])

    @property
    def replies(self) -> Mapping[SlackTs, SlackMessage]:
        return self._replies

    @property
    def is_bot_message(self) -> bool:
        return (
            "subtype" in self._message_json
            and self._message_json["subtype"] == "bot_message"
        )

    @property
    def sender_user_id(self) -> Optional[str]:
        return self._message_json.get("user")

    @property
    def sender_bot_id(self) -> Optional[str]:
        return self._message_json.get("bot_id")

    @property
    def is_self_msg(self) -> bool:
        return self.sender_user_id == self.workspace.my_user.id

    @property
    def reactions(self) -> List[SlackMessageReaction]:
        return self._message_json.get("reactions", [])

    @property
    def muted(self) -> bool:
        parent_subscribed = (
            self.parent_message.subscribed if self.parent_message else False
        )
        return self.conversation.muted and not self.subscribed and not parent_subscribed

    @property
    def text(self) -> str:
        return self._message_json["text"]

    @property
    def deleted(self) -> bool:
        return self._deleted or self._message_json.get("subtype") == "tombstone"

    @deleted.setter
    def deleted(self, value: bool):
        self._deleted = value
        self._rendered_message = None
        self._parsed_message = None

    def update_message_json(self, message_json: SlackMessageDict):
        self._message_json.update(message_json)  # pyright: ignore [reportArgumentType, reportCallIssue]
        self._rendered_prefix = None
        self._rendered_message = None
        self._parsed_message = None

        if "last_read" in message_json:
            self.last_read = SlackTs(message_json["last_read"])

    def update_message_json_room(self, room: SlackMessageSubtypeHuddleThreadRoom):
        if "room" in self._message_json:
            self._message_json["room"] = room
        self._rendered_message = None
        self._parsed_message = None

    async def update_subscribed(
        self, subscribed: bool, subscription: SlackThreadSubscription
    ):
        self._message_json["subscribed"] = subscribed  # pyright: ignore [reportGeneralTypeIssues]
        self.last_read = SlackTs(subscription["last_read"])
        await self.conversation.rerender_message(self)
        if subscribed:
            await self.handle_thread_notify_and_auto_open()

    def _get_reaction(self, reaction_name: str):
        for reaction in self._message_json.get("reactions", []):
            if reaction["name"] == reaction_name:
                return reaction

    def reaction_add(self, reaction_name: str, user_id: str):
        reaction = self._get_reaction(reaction_name)
        if reaction:
            if user_id not in reaction["users"]:
                reaction["users"].append(user_id)
                reaction["count"] += 1
        else:
            if "reactions" not in self._message_json:
                self._message_json["reactions"] = []
            self._message_json["reactions"].append(
                {"name": reaction_name, "users": [user_id], "count": 1}
            )
        self._rendered_message = None

    def reaction_remove(self, reaction_name: str, user_id: str):
        reaction = self._get_reaction(reaction_name)
        if reaction and user_id in reaction["users"]:
            reaction["users"].remove(user_id)
            reaction["count"] -= 1
            self._rendered_message = None

    def has_reacted(self, reaction_name: str) -> bool:
        reaction = self._get_reaction(reaction_name)
        return reaction is not None and self.workspace.my_user.id in reaction["users"]

    def should_highlight(
        self, *, only_mention: bool = False, only_personal: bool = False
    ) -> bool:
        parsed_message = self.parse_message_text()

        for item in parsed_message:
            if isinstance(item, PendingMessageItem):
                if item.should_highlight(
                    only_mention=only_mention, only_personal=only_personal
                ):
                    return True
            elif not only_mention:
                if (
                    self.workspace.global_keywords_regex is not None
                    and self.workspace.global_keywords_regex.search(item)
                ):
                    return True

        return False

    def priority(self, context: MessageContext) -> MessagePriority:
        if (
            context != "thread"
            and self.muted
            and shared.config.look.muted_conversations_notify.value == "none"
        ):
            return MessagePriority.NONE
        elif self.should_highlight(
            only_personal=(
                self.muted
                and shared.config.look.muted_conversations_notify.value
                == "personal_highlights"
            )
        ):
            return MessagePriority.HIGHLIGHT
        elif (
            context != "thread"
            and self.muted
            and shared.config.look.muted_conversations_notify.value != "all"
        ):
            return MessagePriority.NONE
        elif self.subtype in [
            "channel_join",
            "group_join",
            "channel_leave",
            "group_leave",
        ]:
            return MessagePriority.LOW
        elif self.conversation.buffer_type == "private":
            return MessagePriority.PRIVATE
        else:
            return MessagePriority.MESSAGE

    def priority_notify_tag(self, context: MessageContext) -> Optional[str]:
        priority = self.priority(context)
        if priority == MessagePriority.HIGHLIGHT:
            return "notify_highlight"
        elif priority == MessagePriority.PRIVATE:
            return "notify_private"
        elif priority == MessagePriority.MESSAGE:
            return "notify_message"
        elif priority == MessagePriority.LOW:
            return None
        elif priority == MessagePriority.NONE:
            tags = ["notify_none"]
            if self.should_highlight():
                tags.append(shared.highlight_tag)
            return ",".join(tags)
        else:
            assert_never(priority)

    async def tags(self, context: MessageContext, backlog: bool) -> str:
        nick = await self.nick()
        tags = [f"{ts_tag_prefix}{self.ts}", f"nick_{nick.raw_nick}"]

        if self.sender_user_id:
            tags.append(f"slack_user_id_{self.sender_user_id}")
        if self.sender_bot_id:
            tags.append(f"slack_bot_id_{self.sender_bot_id}")

        if self._message_json.get("subtype") in ["channel_join", "group_join"]:
            tags.append("slack_join")
            log_tags = ["log4"]
        elif self._message_json.get("subtype") in ["channel_leave", "group_leave"]:
            tags.append("slack_part")
            log_tags = ["log4"]
        else:
            tags.append("slack_privmsg")
            if self.is_bot_message:
                tags.append("bot_message")

            if self._message_json.get("subtype") == "me_message":
                tags.append("slack_action")
            else:
                if shared.weechat_version >= 0x04000000:
                    tags.append(f"prefix_nick_{nick.color}")

            if self.is_self_msg:
                tags.append("self_msg")

            log_tags = ["log1"]

        if backlog:
            tags += ["no_highlight", "notify_none", "logger_backlog", "no_log"]
        else:
            if self.is_self_msg:
                log_tags += ["notify_none", "no_highlight"]
            else:
                notify_tag = self.priority_notify_tag(context)
                if notify_tag:
                    log_tags.append(notify_tag)

            tags += log_tags

        return ",".join(tags)

    async def get_thread_replies(
        self, only_if_later_than_ts: Optional[SlackTs] = None
    ) -> Optional[List[SlackMessage]]:
        if self.thread_ts is None:
            return

        if self.latest_reply:
            latest_reply_ts = self.latest_reply
        elif self.replies_tss:
            latest_reply_ts = self.replies_tss[-1]
        else:
            _, replies = await self.conversation.fetch_replies(self.thread_ts)
            if not replies:
                return
            latest_reply_ts = replies[-1].ts

        if (
            only_if_later_than_ts is not None
            and latest_reply_ts <= only_if_later_than_ts
        ):
            return

        _, replies = await self.conversation.fetch_replies(self.thread_ts)
        return replies

    async def handle_thread_auto_open(self):
        if not self.conversation.auto_open_threads():
            return

        if (
            not self.subscribed
            and self.conversation.auto_open_threads_only_subscribed()
        ):
            return

        last_read = (
            self.last_read
            if self.conversation.auto_open_threads_only_unread()
            else None
        )

        replies = await self.get_thread_replies(last_read)
        if not replies:
            return

        await self.conversation.open_thread(self.hash)

    async def handle_thread_notify(self):
        notify_subscribed_threads = shared.config.look.notify_subscribed_threads.value
        if (
            not self.is_thread_parent
            or not self.subscribed
            or notify_subscribed_threads == "never"
        ):
            return

        if (
            notify_subscribed_threads == "auto"
            or notify_subscribed_threads == "unless_thread_buffer"
        ) and (self.thread_buffer is not None and self.thread_buffer.buffer_is_open):
            return

        if (
            notify_subscribed_threads == "auto"
            and self.conversation.display_thread_replies()
            and not self.conversation.muted
        ):
            return

        replies_after_ts = max(self.last_read, self._last_thread_notify)
        replies = await self.get_thread_replies(replies_after_ts)
        if not replies:
            return

        replies_after_last_read_and_notify = [
            reply for reply in replies if reply.ts > replies_after_ts
        ]

        if all(reply.is_self_msg for reply in replies_after_last_read_and_notify):
            return

        channel_name = self.conversation.name_with_prefix("short_name_without_padding")
        if any(
            reply.should_highlight(only_mention=True)
            for reply in replies_after_last_read_and_notify
        ):
            self.workspace.print(
                f"You were mentioned in thread {self.hash} in channel {channel_name}"
            )
        else:
            self.workspace.print(
                f"New message in subscribed thread {self.hash} in channel {channel_name}"
            )

        self._last_thread_notify = replies[-1].ts

    async def handle_thread_notify_and_auto_open(self):
        await self.handle_thread_auto_open()
        await self.handle_thread_notify()

    async def render(
        self,
        context: MessageContext,
    ) -> str:
        prefix_coro = self.render_prefix()
        message_coro = self.render_message(context)
        prefix, message = await gather(prefix_coro, message_coro)
        self._rendered = f"{prefix}\t{message}"
        return self._rendered

    async def nick(self) -> Nick:
        if "user_profile" in self._message_json:
            # TODO: is_external
            nick = name_from_user_profile(
                self.workspace,
                self._message_json["user_profile"],
                username=self._message_json["user_profile"]["name"],
            )
            return get_user_nick(nick, is_self=self.is_self_msg)
        if "user" in self._message_json:
            try:
                user = await self.workspace.users[self._message_json["user"]]
                return user.nick
            except (SlackApiError, SlackError) as e:
                if not is_not_found_error(e):
                    raise e
        username = self._message_json.get("username")
        if username:
            return get_bot_nick(username)
        if "bot_profile" in self._message_json:
            return get_bot_nick(self._message_json["bot_profile"]["name"])
        if "bot_id" in self._message_json:
            try:
                bot = await self.workspace.bots[self._message_json["bot_id"]]
                return bot.nick
            except (SlackApiError, SlackError) as e:
                if not is_not_found_error(e):
                    raise e
        return Nick("", "Unknown", "", "unknown")

    async def _render_prefix(self) -> str:
        if self._message_json.get("subtype") in ["channel_join", "group_join"]:
            return removesuffix(weechat.prefix("join"), "\t")
        elif self._message_json.get("subtype") in ["channel_leave", "group_leave"]:
            return removesuffix(weechat.prefix("quit"), "\t")
        elif self._message_json.get("subtype") == "me_message":
            return removesuffix(weechat.prefix("action"), "\t")
        else:
            nick = await self.nick()
            return nick.format(colorize=True)

    async def render_prefix(self) -> str:
        if self._rendered_prefix is not None:
            return self._rendered_prefix
        self._rendered_prefix = await self._render_prefix()
        return self._rendered_prefix

    def parse_message_text(
        self, update: bool = False
    ) -> List[Union[str, PendingMessageItem]]:
        if self._parsed_message is not None and not update:
            return self._parsed_message

        if self.deleted:
            self._parsed_message = [
                with_color(shared.config.color.deleted_message.value, "(deleted)")
            ]

        elif self._message_json.get("subtype") in [
            "channel_join",
            "group_join",
            "channel_leave",
            "group_leave",
        ]:
            is_join = self._message_json.get("subtype") in [
                "channel_join",
                "group_join",
            ]
            text_action = (
                f"{with_color(shared.config.color.message_join.value, 'has joined')}"
                if is_join
                else f"{with_color(shared.config.color.message_quit.value, 'has left')}"
            )
            conversation_item = PendingMessageItem(
                self, "conversation", self.conversation.id, "chat"
            )

            inviter_id = self._message_json.get("inviter")
            if is_join and inviter_id:
                inviter_items = [
                    " by invitation from ",
                    PendingMessageItem(self, "user", inviter_id, "chat"),
                ]
            else:
                inviter_items = []

            self._parsed_message = [
                PendingMessageItem(self, "message_nick", ""),
                " ",
                text_action,
                " ",
                conversation_item,
            ] + inviter_items

        elif (
            "subtype" in self._message_json
            and self._message_json["subtype"] == "huddle_thread"
        ):
            room = self._message_json["room"]
            team = self._message_json.get("team", self.workspace.id)

            huddle_text = "Huddle started" if not room["has_ended"] else "Huddle ended"
            name_text = f", name: {room['name']}" if room["name"] else ""
            texts: List[Union[str, PendingMessageItem]] = [huddle_text + name_text]

            for channel_id in room["channels"]:
                texts.append(
                    f"\nhttps://app.slack.com/client/{team}/{channel_id}?open=start_huddle"
                )
            self._parsed_message = texts

        else:
            if "blocks" in self._message_json:
                texts = self._render_blocks(self._message_json["blocks"])
            else:
                items = self._unfurl_refs(self._message_json["text"])
                texts = [
                    unhtmlescape(item) if isinstance(item, str) else item
                    for item in items
                ]

            files = self._render_files(self._message_json.get("files", []), bool(texts))
            attachment_items = self._render_attachments(texts)
            self._parsed_message = texts + files + attachment_items

        return self._parsed_message

    async def _render_message(self, rerender: bool = False) -> str:
        if self._rendered_message is not None and not rerender:
            return self._rendered_message

        try:
            me_prefix = (
                f"{(await self.nick()).format(colorize=True)} "
                if self._message_json.get("subtype") == "me_message"
                else ""
            )

            parsed_message = self.parse_message_text(rerender)
            text = "".join(
                [
                    text if isinstance(text, str) else await text.resolve()
                    for text in parsed_message
                ]
            )
            text_edited = (
                f" {with_color(shared.config.color.edited_message_suffix.value, '(edited)')}"
                if self._message_json.get("edited")
                else ""
            )
            reactions = await self._create_reactions_string()
            self._rendered_message = me_prefix + text + text_edited + reactions
        except Exception as e:
            uncaught_error = UncaughtError(e)
            print_error(store_and_format_uncaught_error(uncaught_error))
            text = f"<Error rendering message {self.ts}, error id: {uncaught_error.id}>"
            self._rendered_message = with_color(
                shared.config.color.render_error.value, text
            )

        return self._rendered_message

    async def render_message(
        self,
        context: MessageContext,
        rerender: bool = False,
    ) -> str:
        text = await self._render_message(rerender=rerender)
        thread_prefix = self._create_thread_prefix(context)
        thread_info = self._create_thread_string() if context == "conversation" else ""
        return thread_prefix + text + thread_info

    def _resolve_ref(
        self, item_id: str, fallback_name: Optional[str]
    ) -> Union[str, PendingMessageItem]:
        if item_id.startswith("#"):
            return PendingMessageItem(
                self,
                "conversation",
                removeprefix(item_id, "#"),
                "mention",
                fallback_name,
            )
        elif item_id.startswith("@"):
            return PendingMessageItem(
                self, "user", removeprefix(item_id, "@"), "mention", fallback_name
            )
        elif item_id.startswith("!subteam^"):
            return PendingMessageItem(
                self,
                "usergroup",
                removeprefix(item_id, "!subteam^"),
                "mention",
                fallback_name,
            )
        elif item_id in ["!channel", "!everyone", "!group", "!here"]:
            return PendingMessageItem(
                self, "broadcast", removeprefix(item_id, "!"), "mention", fallback_name
            )
        elif item_id.startswith("!date"):
            parts = item_id.split("^")
            timestamp = int(parts[1])
            link = parts[3] if len(parts) > 3 else None
            return format_date(timestamp, parts[2], link)
        else:
            return format_url(item_id, fallback_name)

    def _unfurl_refs(
        self, message: str
    ) -> Generator[Union[str, PendingMessageItem], None, None]:
        re_ref = re.compile(r"<(?P<id>[^|>]+)(?:\|(?P<fallback_name>[^>]*))?>")

        i = 0
        for match in re_ref.finditer(message):
            if i < match.start(0):
                yield message[i : match.start(0)]
            yield self._resolve_ref(match["id"], match["fallback_name"])
            i = match.end(0)

        if i < len(message):
            yield message[i:]

    def _unfurl_and_unescape(
        self, items: Iterable[Union[str, PendingMessageItem]]
    ) -> Generator[Union[str, PendingMessageItem], None, None]:
        for item in items:
            if isinstance(item, str):
                for sub_item in self._unfurl_refs(item):
                    if isinstance(sub_item, str):
                        yield unhtmlescape(sub_item)
                    else:
                        yield sub_item
            else:
                yield item

    async def _create_reaction_string(self, reaction: SlackMessageReaction) -> str:
        if self.conversation.display_reaction_nicks():
            users = await gather(
                *(self.workspace.users[user_id] for user_id in reaction["users"])
            )
            nicks = [user.nick.format() for user in users]
            nicks_extra = (
                ["and others"] if len(reaction["users"]) < reaction["count"] else []
            )
            users_str = f"({', '.join(nicks + nicks_extra)})"
        else:
            users_str = ""

        reaction_string = f"{get_emoji(reaction['name'])}{reaction['count']}{users_str}"

        if self.workspace.my_user.id in reaction["users"]:
            return with_color(
                shared.config.color.reaction_self_suffix.value,
                reaction_string,
                reset_color=shared.config.color.reaction_suffix.value,
            )
        else:
            return reaction_string

    async def _create_reactions_string(self) -> str:
        reactions = self._message_json.get("reactions", [])
        reactions_with_users = [
            reaction for reaction in reactions if reaction["count"] > 0
        ]
        reaction_strings = await gather(
            *(
                self._create_reaction_string(reaction)
                for reaction in reactions_with_users
            )
        )
        reactions_string = " ".join(reaction_strings)
        if reactions_string:
            return " " + with_color(
                shared.config.color.reaction_suffix.value, f"[{reactions_string}]"
            )
        else:
            return ""

    def _create_thread_prefix(self, context: MessageContext) -> str:
        if not self.is_reply or self.thread_ts is None:
            return ""
        thread_hash = self.conversation.message_hashes[self.thread_ts]

        broadcast_text = (
            shared.config.look.thread_broadcast_prefix.value
            if self.is_thread_broadcast
            else None
        )
        thread_text = thread_hash if context == "conversation" else None
        text = " ".join(x for x in [broadcast_text, thread_text] if x)
        if not text:
            return ""
        return with_color(nick_color(thread_hash), f"[{text}]") + " "

    def _create_thread_string(self) -> str:
        if "reply_count" not in self._message_json:
            return ""

        reply_count = self._message_json["reply_count"]
        if not reply_count:
            return ""

        subscribed_text = " Subscribed" if self.subscribed else ""
        text = f"[ Thread: {self.hash} Replies: {reply_count}{subscribed_text} ]"
        return " " + with_color(nick_color(str(self.hash)), text)

    def _render_blocks(
        self, blocks: List[SlackMessageBlock]
    ) -> List[Union[str, PendingMessageItem]]:
        block_lines: List[List[Union[str, PendingMessageItem]]] = []

        for block in blocks:
            try:
                if block["type"] == "section":
                    fields = block.get("fields", [])
                    if "text" in block:
                        fields.insert(0, block["text"])
                    block_lines.extend(
                        self._render_block_element(field) for field in fields
                    )
                elif block["type"] == "actions":
                    items: List[Union[str, PendingMessageItem]] = []
                    for element in block["elements"]:
                        if element["type"] == "button":
                            items.extend(self._render_block_element(element["text"]))
                            if "url" in element:
                                items.append(format_url(element["url"]))
                        else:
                            text = (
                                f'<Unsupported block action type "{element["type"]}">'
                            )
                            items.append(
                                with_color(shared.config.color.render_error.value, text)
                            )
                    block_lines.append(intersperse(items, " | "))
                elif block["type"] == "call":
                    url = block["call"]["v1"]["join_url"]
                    block_lines.append(["Join via " + format_url(url)])
                elif block["type"] == "divider":
                    block_lines.append(["---"])
                elif block["type"] == "context":
                    items = [
                        item
                        for element in block["elements"]
                        for item in self._render_block_element(element)
                    ]
                    block_lines.append(intersperse(items, " | "))
                elif block["type"] == "image":
                    if "title" in block:
                        block_lines.append(self._render_block_element(block["title"]))
                    block_lines.append(self._render_block_element(block))
                elif block["type"] == "rich_text":
                    for element in block.get("elements", []):
                        if element["type"] == "rich_text_section":
                            rendered = self._render_block_rich_text_section(element)
                            if rendered:
                                block_lines.append(rendered)
                        elif element["type"] == "rich_text_list":
                            lines = [
                                [
                                    "    " * element.get("indent", 0),
                                    self._render_block_rich_text_list_prefix(
                                        element, item_index
                                    ),
                                    " ",
                                ]
                                + self._render_block_rich_text_section(item_element)
                                for item_index, item_element in enumerate(
                                    element["elements"]
                                )
                            ]
                            block_lines.extend(lines)
                        elif element["type"] == "rich_text_quote":
                            quote_str = "> "
                            items = [quote_str] + [
                                self._render_block_rich_text_element(
                                    sub_element, quote_str
                                )
                                for sub_element in element["elements"]
                            ]
                            block_lines.append(items)
                        elif element["type"] == "rich_text_preformatted":
                            texts: List[str] = [
                                sub_element["text"]
                                if "text" in sub_element
                                else sub_element["url"]
                                for sub_element in element["elements"]
                            ]
                            if texts:
                                block_lines.append([f"```\n{''.join(texts)}\n```"])
                        else:
                            text = f'<Unsupported rich text type "{element["type"]}">'
                            block_lines.append(
                                [
                                    with_color(
                                        shared.config.color.render_error.value, text
                                    )
                                ]
                            )
                else:
                    text = f'<Unsupported block type "{block["type"]}">'
                    block_lines.append(
                        [with_color(shared.config.color.render_error.value, text)]
                    )
            except Exception as e:
                uncaught_error = UncaughtError(e)
                print_error(store_and_format_uncaught_error(uncaught_error))
                text = f"<Error rendering message {self.ts}, error id: {uncaught_error.id}>"
                block_lines.append(
                    [with_color(shared.config.color.render_error.value, text)]
                )

        return [item for items in intersperse(block_lines, ["\n"]) for item in items]

    def _render_block_rich_text_section(
        self, section: SlackMessageBlockRichTextSection, lines_prepend: str = ""
    ) -> List[Union[str, PendingMessageItem]]:
        texts: List[Union[str, PendingMessageItem]] = []
        prev_element: SlackMessageBlockRichTextElement = {"type": "text", "text": ""}
        for element in section["elements"] + [prev_element.copy()]:
            colors_apply: List[str] = []
            colors_remove: List[str] = []
            characters_apply: List[str] = []
            characters_remove: List[str] = []
            prev_style = prev_element.get("style", {})
            cur_style = element.get("style", {})
            if cur_style.get("code", False) != prev_style.get("code", False):
                if cur_style.get("code"):
                    characters_apply.append("`")
                else:
                    characters_remove.append("`")
            if cur_style.get("bold", False) != prev_style.get("bold", False):
                if cur_style.get("bold"):
                    colors_apply.append(weechat.color("bold"))
                    characters_apply.append("*")
                else:
                    colors_remove.append(weechat.color("-bold"))
                    characters_remove.append("*")
            if cur_style.get("italic", False) != prev_style.get("italic", False):
                if cur_style.get("italic"):
                    colors_apply.append(weechat.color("italic"))
                    characters_apply.append("_")
                else:
                    colors_remove.append(weechat.color("-italic"))
                    characters_remove.append("_")
            if cur_style.get("strike", False) != prev_style.get("strike", False):
                if cur_style.get("strike"):
                    characters_apply.append("~")
                else:
                    characters_remove.append("~")

            prepend = "".join(
                characters_remove[::-1]
                + colors_remove[::-1]
                + colors_apply
                + characters_apply
            )
            if prepend:
                texts.append(prepend)
            text = self._render_block_rich_text_element(element, lines_prepend)
            if text:
                texts.append(text)
            prev_element = element

        if texts and isinstance(texts[-1], str) and texts[-1].endswith("\n"):
            texts[-1] = texts[-1][:-1]

        return texts

    def _render_block_rich_text_element(
        self, element: SlackMessageBlockRichTextElement, lines_prepend: str = ""
    ) -> Union[str, PendingMessageItem]:
        if element["type"] == "text":
            return element["text"].replace("\n", "\n" + lines_prepend)
        elif element["type"] == "link":
            if element.get("style", {}).get("code"):
                if "text" in element:
                    return element["text"]
                else:
                    return element["url"]
            else:
                return format_url(unhtmlescape(element["url"]), element.get("text"))
        elif element["type"] == "emoji":
            return get_emoji(element["name"], element.get("skin_tone"))
        elif element["type"] == "color":
            rgb_int = int(element["value"].lstrip("#"), 16)
            weechat_color = weechat.info_get("color_rgb2term", str(rgb_int))
            return f"{element['value']} {with_color(weechat_color, '■')}"
        elif element["type"] == "date":
            return format_date(element["timestamp"], element["format"])
        elif element["type"] == "channel":
            return PendingMessageItem(self, "conversation", element["channel_id"])
        elif element["type"] == "user":
            return PendingMessageItem(self, "user", element["user_id"])
        elif element["type"] == "usergroup":
            return PendingMessageItem(self, "usergroup", element["usergroup_id"])
        elif element["type"] == "broadcast":
            return PendingMessageItem(self, "broadcast", element["range"])
        else:
            text = f'<Unsupported rich text element type "{element["type"]}">'
            return with_color(shared.config.color.render_error.value, text)

    def _render_block_element(
        self,
        element: Union[SlackMessageBlockCompositionText, SlackMessageBlockElementImage],
    ) -> List[Union[str, PendingMessageItem]]:
        if element["type"] == "plain_text" or element["type"] == "mrkdwn":
            # TODO: Support markdown, and verbatim and emoji properties
            # Looks like emoji and verbatim are only used when posting, so we don't need to care about them.
            # We do have to resolve refs (users, dates etc.) and emojis for both plain_text and mrkdwn though.
            # See a message for a poll from polly
            # Should I run unhtmlescape here?
            items = self._unfurl_refs(element["text"])
            return [
                unhtmlescape(item) if isinstance(item, str) else item for item in items
            ]
        elif element["type"] == "image":
            return [format_url(element["image_url"], element.get("alt_text"))]
        else:
            text = f'<Unsupported block element type "{element["type"]}">'
            return [with_color(shared.config.color.render_error.value, text)]

    def _render_block_rich_text_list_prefix(
        self, list_element: SlackMessageBlockRichTextList, item_index: int
    ) -> str:
        index = list_element.get("offset", 0) + item_index + 1
        if list_element["style"] == "ordered":
            if list_element["indent"] == 0 or list_element["indent"] == 3:
                return f"{index}."
            elif list_element["indent"] == 1 or list_element["indent"] == 4:
                return f"{convert_int_to_letter(index)}."
            else:
                return f"{convert_int_to_roman(index)}."
        else:
            if list_element["indent"] == 0 or list_element["indent"] == 3:
                return "•"
            elif list_element["indent"] == 1 or list_element["indent"] == 4:
                return "◦"
            else:
                return "▪︎"

    def _render_files(
        self, files: List[SlackFile], has_items_before: bool
    ) -> List[Union[str, PendingMessageItem]]:
        items = [
            PendingMessageItem(self, "file", file["id"], file=file) for file in files
        ]
        before = ["\n"] if has_items_before and items else []
        return before + intersperse(items, "\n")

    # TODO: Check if mentions in attachments should highlight
    def _render_attachments(
        self, items_before: List[Union[str, PendingMessageItem]]
    ) -> List[Union[str, PendingMessageItem]]:
        if "attachments" not in self._message_json:
            return []

        attachments: List[List[Union[str, PendingMessageItem]]] = []
        if any(items_before):
            attachments.append([])

        for attachment in self._message_json["attachments"]:
            # Attachments should be rendered roughly like:
            #
            # $pretext
            # $author: (if rest of line is non-empty) $title ($title_link) OR $from_url
            # $author: (if no $author on previous line) $text
            # $fields

            if (
                shared.config.look.display_link_previews.value != "always"
                and ("original_url" in attachment or attachment.get("is_app_unfurl"))
                and not attachment.get("is_msg_unfurl")
            ):
                continue

            if (
                shared.config.look.display_link_previews.value == "never"
                and attachment.get("is_msg_unfurl")
            ):
                continue

            lines: List[List[Union[str, PendingMessageItem]]] = []
            prepend_title_text = ""
            if "author_name" in attachment:
                prepend_title_text = attachment["author_name"] + ": "
            if "pretext" in attachment:
                lines.append([attachment["pretext"]])
            link_shown = False
            title = attachment.get("title")
            title_link = attachment.get("title_link", "")
            if title_link and any(
                isinstance(text, str) and title_link in text for text in items_before
            ):
                title_link = ""
                link_shown = True
            if title and title_link:
                lines.append(
                    [f"{prepend_title_text}{format_url(htmlescape(title_link), title)}"]
                )
                prepend_title_text = ""
            elif title and not title_link:
                lines.append([f"{prepend_title_text}{title}"])
                prepend_title_text = ""
            from_url = unhtmlescape(attachment.get("from_url", ""))
            if (
                not any(
                    isinstance(text, str) and from_url in text for text in items_before
                )
                and from_url != title_link
            ):
                lines.append([format_url(htmlescape(from_url))])
            elif from_url:
                link_shown = True

            atext = attachment.get("text")
            if atext:
                tx = re.sub(r" *\n[\n ]+", "\n", atext)
                lines.append([prepend_title_text + tx])
                prepend_title_text = ""

            image_url = attachment.get("image_url", "")
            if (
                not any(
                    isinstance(text, str) and image_url in text for text in items_before
                )
                and image_url != from_url
                and image_url != title_link
            ):
                lines.append([format_url(htmlescape(image_url))])
            elif image_url:
                link_shown = True

            for field in attachment.get("fields", []):
                if field.get("title"):
                    lines.append([f"{field['title']}: {field['value']}"])
                else:
                    lines.append([field["value"]])

            lines = [
                [item for item in self._unfurl_and_unescape(line)] for line in lines
            ]

            files = self._render_files(attachment.get("files", []), False)
            if files:
                lines.append(files)

            # TODO: Don't render both text and blocks
            blocks_items = self._render_blocks(attachment.get("blocks", []))
            if blocks_items:
                lines.append(blocks_items)

            if "is_msg_unfurl" in attachment and attachment["is_msg_unfurl"]:
                channel_name = PendingMessageItem(
                    self, "conversation", attachment["channel_id"], "chat"
                )
                if attachment.get("is_reply_unfurl"):
                    footer = ["From a thread in ", channel_name]
                else:
                    footer = ["Posted in ", channel_name]
            elif attachment.get("footer"):
                footer: List[Union[str, PendingMessageItem]] = [
                    attachment.get("footer")
                ]
            else:
                footer = []

            if footer:
                ts = attachment.get("ts")
                if ts:
                    ts_int = ts if isinstance(ts, int) else SlackTs(ts).major
                    if ts_int > 100000000000:
                        # The Slack web interface interprets very large timestamps
                        # as milliseconds after the epoch instead of regular Unix
                        # timestamps. We use the same heuristic here.
                        ts_int = ts_int // 1000
                    time_string = ""
                    if date.today() - date.fromtimestamp(ts_int) <= timedelta(days=1):
                        time_string = " at {time}"
                    timestamp_formatted = format_date(
                        ts_int, "{date_short_pretty}" + time_string
                    )
                    footer.append(f" | {timestamp_formatted.capitalize()}")

                lines.append([item for item in self._unfurl_and_unescape(footer)])

            fallback = attachment.get("fallback")
            if not any(lines) and fallback and not link_shown:
                lines.append([fallback])

            items = [item for items in intersperse(lines, ["\n"]) for item in items]

            texts_separate_newlines = [
                item_separate_newline
                for item in items
                for item_separate_newline in (
                    intersperse(item.split("\n"), "\n")
                    if isinstance(item, str)
                    else [item]
                )
            ]

            if texts_separate_newlines:
                prefix = "|"
                line_color = None
                color = attachment.get("color")
                if (
                    color
                    and shared.config.look.color_message_attachments.value != "none"
                ):
                    weechat_color = weechat.info_get(
                        "color_rgb2term", str(int(color.lstrip("#"), 16))
                    )
                    if shared.config.look.color_message_attachments.value == "prefix":
                        prefix = with_color(weechat_color, prefix)
                    elif shared.config.look.color_message_attachments.value == "all":
                        line_color = weechat_color

                texts_with_prefix = [f"{prefix} "] + [
                    f"\n{prefix} " if item == "\n" else item
                    for item in texts_separate_newlines
                ]

                attachment_texts: List[Union[str, PendingMessageItem]] = []
                if line_color:
                    attachment_texts.append(weechat.color(line_color))
                attachment_texts.extend(texts_with_prefix)
                if line_color:
                    attachment_texts.append(weechat.color("reset"))
                attachments.append(attachment_texts)

        return [item for items in intersperse(attachments, ["\n"]) for item in items]


class SlackMessageReplies(Mapping[SlackTs, SlackMessage]):
    def __init__(self, parent: SlackMessage):
        super().__init__()
        self._parent = parent

    def __getitem__(self, key: SlackTs) -> SlackMessage:
        if key == self._parent.ts:
            return self._parent
        return self._parent.conversation.messages[key]

    def __iter__(self) -> Generator[SlackTs, None, None]:
        yield self._parent.ts
        for ts in self._parent.replies_tss:
            yield ts

    def __len__(self) -> int:
        return 1 + len(self._parent.replies_tss)
