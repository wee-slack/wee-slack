from __future__ import annotations

import re
from collections import OrderedDict
from datetime import date, datetime, timedelta
from enum import Enum
from typing import TYPE_CHECKING, List, Match, Optional, Tuple, Union

import weechat

from slack.error import (
    SlackError,
    UncaughtError,
    store_and_format_uncaught_error,
    store_uncaught_error,
)
from slack.log import print_error, print_exception_once
from slack.python_compatibility import removeprefix, removesuffix
from slack.shared import shared
from slack.slack_user import SlackBot, SlackUser, format_bot_nick, nick_color
from slack.task import gather
from slack.util import with_color
from slack.weechat_config import WeeChatColor

if TYPE_CHECKING:
    from slack_api.slack_conversations_history import SlackMessage as SlackMessageDict
    from slack_api.slack_conversations_history import (
        SlackMessageBlock,
        SlackMessageBlockCompositionText,
        SlackMessageBlockElementImage,
        SlackMessageBlockRichTextElement,
        SlackMessageBlockRichTextElementBroadcast,
        SlackMessageBlockRichTextElementUser,
        SlackMessageBlockRichTextElementUsergroup,
        SlackMessageBlockRichTextList,
        SlackMessageBlockRichTextSection,
        SlackMessageFile,
        SlackMessageReaction,
        SlackMessageSubtypeHuddleThreadRoom,
    )
    from typing_extensions import Literal, assert_never

    from slack.slack_conversation import SlackConversation
    from slack.slack_thread import SlackThread
    from slack.slack_workspace import SlackWorkspace

    Mentions = List[
        Union[
            SlackMessageBlockRichTextElementUser,
            SlackMessageBlockRichTextElementUsergroup,
            SlackMessageBlockRichTextElementBroadcast,
        ]
    ]


def unhtmlescape(text: str) -> str:
    return text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")


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


class MessagePriority(Enum):
    LOW = 0
    MESSAGE = 1
    PRIVATE = 2
    HIGHLIGHT = 3


class SlackTs(str):
    def __init__(self, ts: str):
        self.major, self.minor = [int(x) for x in ts.split(".", 1)]

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


class SlackMessage:
    def __init__(self, conversation: SlackConversation, message_json: SlackMessageDict):
        self._message_json = message_json
        self._rendered_prefix = None
        self._rendered_message = None
        self._mentions: Optional[Mentions] = None
        self.conversation = conversation
        self.ts = SlackTs(message_json["ts"])
        self.replies: OrderedDict[SlackTs, SlackMessage] = OrderedDict()
        self.reply_history_filled = False
        self.thread_buffer: Optional[SlackThread] = None
        self._deleted = False

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
    async def sender(self) -> Union[SlackUser, SlackBot]:
        if "user" in self._message_json:
            return await self.workspace.users[self._message_json["user"]]
        else:
            return await self.workspace.bots[self._message_json["bot_id"]]

    @property
    def priority(self) -> MessagePriority:
        return MessagePriority.MESSAGE

    @property
    def deleted(self) -> bool:
        return self._deleted or self._message_json.get("subtype") == "tombstone"

    @deleted.setter
    def deleted(self, value: bool):
        self._deleted = value
        self._rendered_message = None

    def update_message_json(self, message_json: SlackMessageDict):
        self._message_json = message_json
        self._rendered_prefix = None
        self._rendered_message = None

    def update_message_json_room(self, room: SlackMessageSubtypeHuddleThreadRoom):
        if "room" in self._message_json:
            self._message_json["room"] = room
        self._rendered_message = None

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

    async def should_highlight(self) -> bool:
        # TODO: Highlight words from user preferences
        mentions = self._mentions
        if mentions is None:
            _, mentions = await self._render_message()

        for mention in mentions:
            if mention["type"] == "user":
                if mention["user_id"] == self.workspace.my_user.id:
                    return True
            elif mention["type"] == "usergroup":
                # TODO
                pass
            elif mention["type"] == "broadcast":
                # TODO: figure out how to handle here broadcast
                return True
            else:
                assert_never(mention)

        return False

    async def tags(self, backlog: bool = False) -> str:
        nick = await self.nick(colorize=False, only_nick=True)
        tags = [f"slack_ts_{self.ts}", f"nick_{nick}"]

        if self.sender_user_id:
            tags.append(f"slack_user_id_{self.sender_user_id}")
        if self.sender_bot_id:
            tags.append(f"slack_bot_id_{self.sender_bot_id}")

        user = (
            await self.workspace.users[self.sender_user_id]
            if self.sender_user_id
            else None
        )

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
                    if user:
                        tags.append(f"prefix_nick_{user.nick_color()}")
                    else:
                        tags.append(f"prefix_nick_{nick_color(nick)}")

            if user and user.is_self:
                tags.append("self_msg")
                log_tags = ["notify_none", "no_highlight", "log1"]
            elif await self.should_highlight():
                log_tags = ["notify_highlight", "log1"]
            else:
                log_tags = ["notify_message", "log1"]

        if backlog:
            tags += ["no_highlight", "notify_none", "logger_backlog", "no_log"]
        else:
            tags += log_tags

        return ",".join(tags)

    async def render(
        self,
        context: Literal["conversation", "thread"],
    ) -> str:
        prefix_coro = self.render_prefix()
        message_coro = self.render_message(context)
        prefix, message = await gather(prefix_coro, message_coro)
        self._rendered = f"{prefix}\t{message}"
        return self._rendered

    async def nick(self, colorize: bool = True, only_nick: bool = False) -> str:
        if "user" in self._message_json:
            user = await self.workspace.users[self._message_json["user"]]
            return user.nick(colorize=colorize, only_nick=only_nick)
        else:
            username = self._message_json.get("username")
            if username:
                return format_bot_nick(username, colorize=colorize, only_nick=only_nick)
            else:
                bot = await self.workspace.bots[self._message_json["bot_id"]]
                return bot.nick(colorize=colorize, only_nick=only_nick)

    async def _render_prefix(
        self, colorize: bool = True, only_nick: bool = False
    ) -> str:
        if self._message_json.get("subtype") in ["channel_join", "group_join"]:
            return removesuffix(weechat.prefix("join"), "\t")
        elif self._message_json.get("subtype") in ["channel_leave", "group_leave"]:
            return removesuffix(weechat.prefix("quit"), "\t")
        elif self._message_json.get("subtype") == "me_message":
            return removesuffix(weechat.prefix("action"), "\t")
        else:
            return await self.nick(colorize=colorize, only_nick=only_nick)

    async def render_prefix(self) -> str:
        if self._rendered_prefix is not None:
            return self._rendered_prefix
        self._rendered_prefix = await self._render_prefix()
        return self._rendered_prefix

    async def _render_message_text(self) -> Tuple[str, Mentions]:
        if self._message_json.get("subtype") in [
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
            conversation_name = await self.conversation.name_with_prefix(
                "short_name_without_padding"
            )
            text_conversation_name = f"{with_color('chat_channel', conversation_name)}"

            inviter_id = self._message_json.get("inviter")
            if is_join and inviter_id:
                inviter_user = await self.workspace.users[inviter_id]
                inviter_text = f" by invitation from {inviter_user.nick(colorize=True)}"
            else:
                inviter_text = ""

            return (
                f"{await self.nick()} {text_action} {text_conversation_name}{inviter_text}",
                [],
            )

        elif (
            "subtype" in self._message_json
            and self._message_json["subtype"] == "huddle_thread"
        ):
            room = self._message_json["room"]
            team = self._message_json["team"]

            huddle_text = "Huddle started" if not room["has_ended"] else "Huddle ended"
            name_text = f", name: {room['name']}" if room["name"] else ""
            texts: List[str] = [huddle_text + name_text]

            for channel_id in room["channels"]:
                texts.append(
                    f"https://app.slack.com/client/{team}/{channel_id}?open=start_huddle"
                )
            return "\n".join(texts), []

        else:
            if "blocks" in self._message_json:
                texts, mentions = await self._render_blocks(
                    self._message_json["blocks"]
                )
            else:
                # TODO: highlights from text
                text = unhtmlescape(await self._unfurl_refs(self._message_json["text"]))
                texts = [text] if text else []
                mentions = []

            files_texts = self._render_files(self._message_json.get("files", []))
            text_with_files = "\n".join(texts + files_texts)

            attachment_texts = await self._render_attachments(text_with_files)
            full_text = "\n".join([text_with_files] + attachment_texts)

            if self._message_json.get("subtype") == "me_message":
                return f"{await self.nick()} {full_text}", mentions
            else:
                return full_text, mentions

    async def _render_message(self, rerender: bool = False) -> Tuple[str, Mentions]:
        if self.deleted:
            self._mentions = []
            return (
                with_color(shared.config.color.deleted_message.value, "(deleted)"),
                self._mentions,
            )
        elif (
            self._rendered_message is not None and self._mentions is not None
        ) and not rerender:
            return self._rendered_message, self._mentions
        else:
            text, self._mentions = await self._render_message_text()
            text_edited = (
                f" {with_color(shared.config.color.edited_message_suffix.value, '(edited)')}"
                if self._message_json.get("edited")
                else ""
            )
            reactions = await self._create_reactions_string()
            self._rendered_message = text + text_edited + reactions
            return self._rendered_message, self._mentions

    async def render_message(
        self,
        context: Literal["conversation", "thread"],
        rerender: bool = False,
    ) -> str:
        text, _ = await self._render_message(rerender=rerender)
        if context == "thread":
            return text
        thread_prefix = self._create_thread_prefix()
        thread = self._create_thread_string()
        return thread_prefix + text + thread

    def _item_prefix(self, item_id: str):
        if item_id.startswith("#") or item_id.startswith("@"):
            return item_id[0]
        elif item_id.startswith("!subteam^") or item_id in [
            "!here",
            "!channel",
            "!everyone",
        ]:
            return "@"
        else:
            return ""

    async def _resolve_ref(
        self, item_id: str
    ) -> Optional[Tuple[Optional[WeeChatColor], str]]:
        if item_id.startswith("#"):
            conversation = await self.workspace.conversations[
                removeprefix(item_id, "#")
            ]
            color = shared.config.color.channel_mention_color.value
            name = await conversation.name_with_prefix("short_name_without_padding")
            return (color, name)
        elif item_id.startswith("@"):
            user = await self.workspace.users[removeprefix(item_id, "@")]
            color = shared.config.color.user_mention_color.value
            return (color, self._item_prefix(item_id) + user.nick())
        elif item_id.startswith("!subteam^"):
            usergroup = await self.workspace.usergroups[
                removeprefix(item_id, "!subteam^")
            ]
            color = shared.config.color.usergroup_mention_color.value
            return (color, self._item_prefix(item_id) + usergroup.handle())
        elif item_id in ["!here", "!channel", "!everyone"]:
            color = shared.config.color.usergroup_mention_color.value
            return (color, self._item_prefix(item_id) + removeprefix(item_id, "!"))

        elif item_id.startswith("!date"):
            parts = item_id.split("^")
            ref_datetime = datetime.fromtimestamp(int(parts[1]))
            link_suffix = f" ({parts[3]})" if len(parts) > 3 else ""
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

            text = re.sub(r"{([^}]+)}", replace_token, parts[2]) + link_suffix
            return (None, text)

    async def _unfurl_refs(self, message: str) -> str:
        re_mention = re.compile(r"<(?P<id>[^|>]+)(?:\|(?P<fallback_name>[^>]*))?>")
        mention_matches = list(re_mention.finditer(message))
        mention_ids: List[str] = [match["id"] for match in mention_matches]
        items_list = await gather(
            *(self._resolve_ref(mention_id) for mention_id in mention_ids),
            return_exceptions=True,
        )
        items = dict(zip(mention_ids, items_list))

        def unfurl_ref(match: Match[str]):
            item = items[match["id"]]
            if item and not isinstance(item, BaseException):
                return with_color(item[0], item[1])
            elif match["fallback_name"]:
                prefix = self._item_prefix(match["id"])
                if match["fallback_name"].startswith(prefix):
                    return match["fallback_name"]
                else:
                    return prefix + match["fallback_name"]
            elif item:
                print_exception_once(item)
            return match[0]

        return re_mention.sub(unfurl_ref, message)

    def _get_emoji(self, emoji_name: str, skin_tone: Optional[int] = None) -> str:
        emoji_name_with_colons = f":{emoji_name}:"
        if shared.config.look.render_emoji_as.value == "name":
            return emoji_name_with_colons

        emoji_item = shared.standard_emojis.get(emoji_name)
        if emoji_item is None:
            return emoji_name_with_colons

        skin_tone_item = (
            emoji_item.get("skinVariations", {}).get(str(skin_tone))
            if skin_tone
            else None
        )
        emoji_unicode = (
            skin_tone_item["unicode"] if skin_tone_item else emoji_item["unicode"]
        )

        if shared.config.look.render_emoji_as.value == "emoji":
            return emoji_unicode
        elif shared.config.look.render_emoji_as.value == "both":
            return f"{emoji_unicode}({emoji_name_with_colons})"
        else:
            assert_never(shared.config.look.render_emoji_as.value)

    async def _create_reaction_string(self, reaction: SlackMessageReaction) -> str:
        if self.conversation.display_reaction_nicks():
            # TODO: initialize_items?
            users = await gather(
                *(self.workspace.users[user_id] for user_id in reaction["users"])
            )
            nicks = ",".join(user.nick() for user in users)
            users_str = f"({nicks})"
        else:
            users_str = ""

        reaction_string = (
            f"{self._get_emoji(reaction['name'])}{len(reaction['users'])}{users_str}"
        )

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
            reaction for reaction in reactions if len(reaction["users"]) > 0
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

    def _create_thread_prefix(self) -> str:
        if not self.is_reply or self.thread_ts is None:
            return ""
        thread_hash = self.conversation.message_hashes[self.thread_ts]

        broadcast_text = (
            shared.config.look.thread_broadcast_prefix.value
            if self.is_thread_broadcast
            else ""
        )
        text = f"[{broadcast_text}{thread_hash}]"
        return with_color(nick_color(thread_hash), text) + " "

    def _create_thread_string(self) -> str:
        if "reply_count" not in self._message_json:
            return ""

        reply_count = self._message_json["reply_count"]
        if not reply_count:
            return ""

        subscribed_text = " Subscribed" if self._message_json.get("subscribed") else ""
        text = f"[ Thread: {self.hash} Replies: {reply_count}{subscribed_text} ]"
        return " " + with_color(nick_color(str(self.hash)), text)

    def _block_element_mentions(self, elements: List[SlackMessageBlockRichTextElement]):
        for element in elements:
            if (
                element["type"] == "user"
                or element["type"] == "usergroup"
                or element["type"] == "broadcast"
            ):
                yield element

    async def _render_blocks(self, blocks: List[SlackMessageBlock]):
        block_texts: List[str] = []
        mentions: Mentions = []

        for block in blocks:
            try:
                if block["type"] == "section":
                    fields = block.get("fields", [])
                    if "text" in block:
                        fields.insert(0, block["text"])
                    block_texts.extend(
                        [await self._render_block_element(field) for field in fields]
                    )
                elif block["type"] == "actions":
                    texts: List[str] = []
                    for element in block["elements"]:
                        if element["type"] == "button":
                            texts.append(
                                await self._render_block_element(element["text"])
                            )
                            if "url" in element:
                                texts.append(element["url"])
                        else:
                            text = (
                                f'<Unsupported block action type "{element["type"]}">'
                            )
                            texts.append(
                                with_color(shared.config.color.render_error.value, text)
                            )
                    block_texts.append(" | ".join(texts))
                elif block["type"] == "call":
                    url = block["call"]["v1"]["join_url"]
                    block_texts.append("Join via " + url)
                elif block["type"] == "divider":
                    block_texts.append("---")
                elif block["type"] == "context":
                    block_texts.append(
                        " | ".join(
                            [
                                await self._render_block_element(element)
                                for element in block["elements"]
                            ]
                        )
                    )
                elif block["type"] == "image":
                    if "title" in block:
                        block_texts.append(
                            await self._render_block_element(block["title"])
                        )
                    block_texts.append(await self._render_block_element(block))
                elif block["type"] == "rich_text":
                    for element in block.get("elements", []):
                        if element["type"] == "rich_text_section":
                            rendered = await self._render_block_rich_text_section(
                                element
                            )
                            if rendered:
                                block_texts.append(rendered)
                            mentions.extend(
                                self._block_element_mentions(element["elements"])
                            )
                        elif element["type"] == "rich_text_list":
                            rendered = [
                                "{}{} {}".format(
                                    "    " * element.get("indent", 0),
                                    self._render_block_rich_text_list_prefix(
                                        element, item_index
                                    ),
                                    await self._render_block_rich_text_section(
                                        item_element
                                    ),
                                )
                                for item_index, item_element in enumerate(
                                    element["elements"]
                                )
                            ]
                            block_texts.extend(rendered)
                        elif element["type"] == "rich_text_quote":
                            lines = [
                                f"> {line}"
                                for sub_element in element["elements"]
                                for line in (
                                    await self._render_block_rich_text_element(
                                        sub_element
                                    )
                                ).split("\n")
                            ]
                            block_texts.extend(lines)
                            mentions.extend(
                                self._block_element_mentions(element["elements"])
                            )
                        elif element["type"] == "rich_text_preformatted":
                            texts = [
                                sub_element.get("text", sub_element.get("url", ""))
                                for sub_element in element["elements"]
                            ]
                            if texts:
                                block_texts.append(f"```\n{''.join(texts)}\n```")
                        else:
                            text = f'<Unsupported rich text type "{element["type"]}">'
                            block_texts.append(
                                with_color(shared.config.color.render_error.value, text)
                            )
                else:
                    text = f'<Unsupported block type "{block["type"]}">'
                    block_texts.append(
                        with_color(shared.config.color.render_error.value, text)
                    )
            except Exception as e:
                uncaught_error = UncaughtError(e)
                print_error(store_and_format_uncaught_error(uncaught_error))
                text = f"<Error rendering message, error id: {uncaught_error.id}>"
                block_texts.append(
                    with_color(shared.config.color.render_error.value, text)
                )

        return block_texts, mentions

    async def _render_block_rich_text_section(
        self, section: SlackMessageBlockRichTextSection
    ) -> str:
        texts: List[str] = []
        prev_element: SlackMessageBlockRichTextElement = {"type": "text", "text": ""}
        for element in section["elements"] + [prev_element.copy()]:
            colors_apply: List[str] = []
            colors_remove: List[str] = []
            characters_apply: List[str] = []
            characters_remove: List[str] = []
            prev_style = prev_element.get("style", {})
            cur_style = element.get("style", {})
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
            if cur_style.get("code", False) != prev_style.get("code", False):
                if cur_style.get("code"):
                    characters_apply.append("`")
                else:
                    characters_remove.append("`")

            texts.extend(reversed(characters_remove))
            texts.extend(reversed(colors_remove))
            texts.extend(colors_apply)
            texts.extend(characters_apply)
            texts.append(await self._render_block_rich_text_element(element))
            prev_element = element

        text = "".join(texts)

        if text.endswith("\n"):
            return text[:-1]
        else:
            return text

    async def _render_block_rich_text_element(
        self, element: SlackMessageBlockRichTextElement
    ) -> str:
        if element["type"] == "text":
            return element["text"]
        elif element["type"] == "link":
            if "text" in element:
                if element.get("style", {}).get("code"):
                    return element["text"]
                else:
                    return f"{element['url']} ({element['text']})"
            else:
                return element["url"]
        elif element["type"] == "emoji":
            return self._get_emoji(element["name"], element.get("skin_tone"))
        elif element["type"] == "channel":
            conversation = await self.workspace.conversations[element["channel_id"]]
            name = await conversation.name_with_prefix("short_name_without_padding")
            return with_color(shared.config.color.channel_mention_color.value, name)
        elif element["type"] == "user":
            user = await self.workspace.users[element["user_id"]]
            name = f"@{user.nick()}"
            return with_color(shared.config.color.user_mention_color.value, name)
        elif element["type"] == "usergroup":
            # TODO: Handle error
            usergroup = await self.workspace.usergroups[element["usergroup_id"]]
            name = f"@{usergroup.handle()}"
            return with_color(shared.config.color.usergroup_mention_color.value, name)
        elif element["type"] == "broadcast":
            name = f"@{element['range']}"
            return with_color(shared.config.color.usergroup_mention_color.value, name)
        else:
            text = f'<Unsupported rich text element type "{element["type"]}">'
            return with_color(shared.config.color.render_error.value, text)

    async def _render_block_element(
        self,
        element: Union[SlackMessageBlockCompositionText, SlackMessageBlockElementImage],
    ) -> str:
        if element["type"] == "plain_text" or element["type"] == "mrkdwn":
            # TODO: Support markdown, and verbatim and emoji properties
            # Looks like emoji and verbatim are only used when posting, so we don't need to care about them.
            # We do have to resolve refs (users, dates etc.) and emojis for both plain_text and mrkdwn though.
            # See a message for a poll from polly
            # return element["text"]
            return unhtmlescape(await self._unfurl_refs(element["text"]))
        elif element["type"] == "image":
            if element.get("alt_text"):
                return f"{element['image_url']} ({element['alt_text']})"
            else:
                return element["image_url"]
        else:
            text = f'<Unsupported block element type "{element["type"]}">'
            return with_color(shared.config.color.render_error.value, text)

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

    def _render_files(self, files: List[SlackMessageFile]) -> List[str]:
        texts: List[str] = []
        for file in files:
            if file.get("mode") == "tombstone":
                text = with_color(
                    shared.config.color.deleted_message.value, "(This file was deleted)"
                )
            elif file.get("mode") == "hidden_by_limit":
                text = with_color(
                    shared.config.color.deleted_message.value,
                    "(This file is not available because the workspace has passed its storage limit)",
                )
            elif file.get("mimetype") == "application/vnd.slack-docs":
                url = f"{file['permalink']}?origin_team={self.workspace.id}&origin_channel={self.conversation.id}"
                text = f"{url} ({file['title']})"
            elif file.get("url_private"):
                if file.get("title"):
                    text = f"{file['url_private']} ({file['title']})"
                else:
                    text = file["url_private"]
            else:
                error = SlackError(self.workspace, "Unsupported file", file)
                uncaught_error = UncaughtError(error)
                store_uncaught_error(uncaught_error)
                text = with_color(
                    shared.config.color.render_error.value,
                    f"<Unsupported file, error id: {uncaught_error.id}>",
                )
            texts.append(text)

        return texts

    async def _render_attachments(self, text_before: str) -> List[str]:
        if "attachments" not in self._message_json:
            return []

        text_before_unescaped = unhtmlescape(text_before)
        attachments_texts: List[str] = []
        for attachment in self._message_json["attachments"]:
            # Attachments should be rendered roughly like:
            #
            # $pretext
            # $author: (if rest of line is non-empty) $title ($title_link) OR $from_url
            # $author: (if no $author on previous line) $text
            # $fields

            if (
                attachment.get("is_app_unfurl")
                and shared.config.look.display_link_previews
            ):
                continue

            texts: List[str] = []
            prepend_title_text = ""
            if "author_name" in attachment:
                prepend_title_text = attachment["author_name"] + ": "
            if "pretext" in attachment:
                texts.append(attachment["pretext"])
            link_shown = False
            title = attachment.get("title")
            title_link = attachment.get("title_link", "")
            if title_link and (
                title_link in text_before or title_link in text_before_unescaped
            ):
                title_link = ""
                link_shown = True
            if title and title_link:
                texts.append(f"{prepend_title_text}{title} ({title_link})")
                prepend_title_text = ""
            elif title and not title_link:
                texts.append(f"{prepend_title_text}{title}")
                prepend_title_text = ""
            from_url = attachment.get("from_url", "")
            if (
                from_url not in text_before
                and from_url not in text_before_unescaped
                and from_url != title_link
            ):
                texts.append(from_url)
            elif from_url:
                link_shown = True

            atext = attachment.get("text")
            if atext:
                tx = re.sub(r" *\n[\n ]+", "\n", atext)
                texts.append(prepend_title_text + tx)
                prepend_title_text = ""

            # TODO: Don't render both text and blocks
            blocks, _ = await self._render_blocks(attachment.get("blocks", []))
            texts.extend(blocks)

            image_url = attachment.get("image_url", "")
            if (
                image_url not in text_before
                and image_url not in text_before_unescaped
                and image_url != from_url
                and image_url != title_link
            ):
                texts.append(image_url)
            elif image_url:
                link_shown = True

            for field in attachment.get("fields", []):
                if field.get("title"):
                    texts.append(f"{field['title']}: {field['value']}")
                else:
                    texts.append(field["value"])

            files = self._render_files(attachment.get("files", []))
            texts.extend(files)

            if attachment.get("is_msg_unfurl"):
                channel_name = await self.conversation.name_with_prefix(
                    "short_name_without_padding"
                )
                if attachment.get("is_reply_unfurl"):
                    footer = f"From a thread in {channel_name}"
                else:
                    footer = f"Posted in {channel_name}"
            else:
                footer = attachment.get("footer")

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
                    timestamp_item = await self._resolve_ref(
                        f"!date^{ts_int}^{{date_short_pretty}}{time_string}"
                    )
                    if timestamp_item:
                        timestamp_formatted = with_color(
                            timestamp_item[0], timestamp_item[1].capitalize()
                        )
                        footer += f" | {timestamp_formatted}"
                texts.append(footer)

            fallback = attachment.get("fallback")
            if texts == [] and fallback and not link_shown:
                texts.append(fallback)

            lines = [
                line for part in texts for line in part.strip().split("\n") if part
            ]

            if lines:
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

                attachments_texts.extend(
                    with_color(line_color, f"{prefix} {line}") for line in lines
                )

        return attachments_texts
