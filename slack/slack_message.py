from __future__ import annotations

import re
from enum import Enum
from typing import TYPE_CHECKING, List, Match, Optional, Union

import weechat

from slack.error import UncaughtError, store_and_format_uncaught_error
from slack.log import print_error, print_exception_once
from slack.python_compatibility import removeprefix, removesuffix
from slack.shared import shared
from slack.slack_user import format_bot_nick, nick_color
from slack.task import gather
from slack.util import with_color

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
    )
    from typing_extensions import assert_never

    from slack.slack_conversation import SlackConversation
    from slack.slack_workspace import SlackWorkspace


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

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SlackTs):
            return False
        return self.major == other.major and self.minor == other.minor

    def __hash__(self) -> int:
        return hash((self.major, self.minor))

    def __repr__(self) -> str:
        return f"SlackTs('{self}')"


class SlackMessage:
    def __init__(self, conversation: SlackConversation, message_json: SlackMessageDict):
        self._message_json = message_json
        self._rendered_prefix = None
        self._rendered_message = None
        self.conversation = conversation
        self.ts = SlackTs(message_json["ts"])
        self._deleted = False

    @property
    def workspace(self) -> SlackWorkspace:
        return self.conversation.workspace

    @property
    def is_bot_message(self) -> bool:
        return (
            "subtype" in self._message_json
            and self._message_json["subtype"] == "bot_message"
        )

    @property
    def sender_user_id(self) -> Optional[str]:
        if not self.is_bot_message:
            return self._message_json.get("user")

    @property
    def sender_bot_id(self) -> Optional[str]:
        if self.is_bot_message:
            return self._message_json.get("bot_id")

    @property
    def priority(self) -> MessagePriority:
        return MessagePriority.MESSAGE

    @property
    def deleted(self) -> bool:
        return self._deleted

    @deleted.setter
    def deleted(self, value: bool):
        self._deleted = value
        self._rendered_message = None

    def update_message_json(self, message_json: SlackMessageDict):
        self._message_json = message_json
        self._rendered_prefix = None
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

    async def tags(self, backlog: bool = False) -> str:
        # TODO: Add tags for highlight
        nick = await self._nick(colorize=False, only_nick=True)
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
            else:
                log_tags = ["notify_message", "log1"]

        if backlog:
            tags += ["no_highlight", "notify_none", "logger_backlog", "no_log"]
        else:
            tags += log_tags

        return ",".join(tags)

    async def render(self) -> str:
        prefix_coro = self.render_prefix()
        message_coro = self.render_message()
        prefix, message = await gather(prefix_coro, message_coro)
        self._rendered = f"{prefix}\t{message}"
        return self._rendered

    async def _nick(self, colorize: bool = True, only_nick: bool = False) -> str:
        if (
            "subtype" in self._message_json
            and self._message_json["subtype"] == "bot_message"
        ):
            username = self._message_json.get("username")
            if username:
                return format_bot_nick(username, colorize=colorize, only_nick=only_nick)
            else:
                bot = await self.workspace.bots[self._message_json["bot_id"]]
                return bot.nick(colorize=colorize, only_nick=only_nick)
        else:
            user = await self.workspace.users[self._message_json["user"]]
            return user.nick(colorize=colorize, only_nick=only_nick)

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
            return await self._nick(colorize=colorize, only_nick=only_nick)

    async def render_prefix(self) -> str:
        if self._rendered_prefix is not None:
            return self._rendered_prefix
        self._rendered_prefix = await self._render_prefix()
        return self._rendered_prefix

    async def _render_message_text(self) -> str:
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

            return f"{await self._nick()} {text_action} {text_conversation_name}{inviter_text}"

        else:
            if "blocks" in self._message_json:
                text = await self._render_blocks(self._message_json["blocks"])
            else:
                text = await self._unfurl_refs(self._message_json["text"])

            if self._message_json.get("subtype") == "me_message":
                return f"{await self._nick()} {text}"
            else:
                return text

    async def _render_message(self) -> str:
        if self._deleted:
            return with_color(shared.config.color.deleted_message.value, "(deleted)")
        else:
            text = await self._render_message_text()
            text_edited = (
                f" {with_color(shared.config.color.edited_message_suffix.value, '(edited)')}"
                if self._message_json.get("edited")
                else ""
            )
            reactions = await self._create_reactions_string()
            return text + text_edited + reactions

    async def render_message(self, rerender: bool = False) -> str:
        if self._rendered_message is not None and not rerender:
            return self._rendered_message
        self._rendered_message = await self._render_message()
        return self._rendered_message

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

    async def _lookup_item_id(self, item_id: str):
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

    async def _unfurl_refs(self, message: str) -> str:
        re_mention = re.compile(r"<(?P<id>[^|>]+)(?:\|(?P<fallback_name>[^>]*))?>")
        mention_matches = list(re_mention.finditer(message))
        mention_ids: List[str] = [match["id"] for match in mention_matches]
        items_list = await gather(
            *(self._lookup_item_id(mention_id) for mention_id in mention_ids),
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
        if shared.config.look.display_reaction_nicks.value:
            # TODO: initialize_items?
            users = await gather(
                *(self.workspace.users[user_id] for user_id in reaction["users"])
            )
            nicks = ",".join(user.nick() for user in users)
            users_str = f"({nicks})"
        else:
            users_str = len(reaction["users"])

        reaction_string = f"{self._get_emoji(reaction['name'])}{users_str}"

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

    async def _render_blocks(self, blocks: List[SlackMessageBlock]) -> str:
        block_texts: List[str] = []
        for block in blocks:
            try:
                if block["type"] == "section":
                    fields = block.get("fields", [])
                    if "text" in block:
                        fields.insert(0, block["text"])
                    block_texts.extend(
                        self._render_block_element(field) for field in fields
                    )
                elif block["type"] == "actions":
                    texts: List[str] = []
                    for element in block["elements"]:
                        if element["type"] == "button":
                            texts.append(self._render_block_element(element["text"]))
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
                            self._render_block_element(element)
                            for element in block["elements"]
                        )
                    )
                elif block["type"] == "image":
                    if "title" in block:
                        block_texts.append(self._render_block_element(block["title"]))
                    block_texts.append(self._render_block_element(block))
                elif block["type"] == "rich_text":
                    for element in block.get("elements", []):
                        if element["type"] == "rich_text_section":
                            rendered = await self._render_block_rich_text_section(
                                element
                            )
                            if rendered:
                                block_texts.append(rendered)
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

        return "\n".join(block_texts)

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

    def _render_block_element(
        self,
        element: Union[SlackMessageBlockCompositionText, SlackMessageBlockElementImage],
    ) -> str:
        if element["type"] == "plain_text" or element["type"] == "mrkdwn":
            # TODO: Support markdown, and verbatim and emoji properties
            return element["text"]
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
