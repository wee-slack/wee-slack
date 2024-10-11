from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Union

import weechat

from slack.error import SlackError
from slack.shared import shared
from slack.slack_emoji import get_emoji
from slack.util import with_color

if TYPE_CHECKING:
    from slack_api.slack_bots_info import SlackBotInfo
    from slack_api.slack_conversations_history import SlackMessageUserProfile
    from slack_api.slack_profile import SlackProfile
    from slack_api.slack_usergroups_info import SlackUsergroupInfo
    from slack_api.slack_users_info import SlackUserInfo
    from slack_rtm.slack_rtm_message import SlackSubteam
    from typing_extensions import Literal, assert_never

    from slack.slack_workspace import SlackWorkspace


@dataclass
class Nick:
    color: str
    raw_nick: str
    suffix: str
    type: Literal["user", "bot", "unknown"]

    def __hash__(self) -> int:
        return hash(self.raw_nick)

    def format(self, colorize: bool = False) -> str:
        color = self.color if colorize else ""
        return with_color(color, self.raw_nick) + self.suffix


def nick_color(nick: str, is_self: bool = False) -> str:
    if is_self:
        return weechat.config_string(weechat.config_get("weechat.color.chat_nick_self"))

    return weechat.info_get("nick_color_name", nick)


# TODO: Probably need to do some mapping here based on the existing users, in case some has been changed to avoid duplicate names
def name_from_user_profile(
    workspace: SlackWorkspace,
    profile: Union[SlackProfile, SlackMessageUserProfile],
    username: str,
) -> str:
    nick_source = workspace.config.nick_source.value
    display_name = profile.get("display_name")
    real_name = profile.get("real_name")
    if nick_source == "display_name":
        return display_name or real_name or username
    elif nick_source == "real_name":
        return real_name or display_name or username
    elif nick_source == "username":
        return username
    else:
        assert_never(nick_source)


def name_from_user_info(workspace: SlackWorkspace, info: SlackUserInfo) -> str:
    return name_from_user_profile(workspace, info["profile"], info["name"])


def get_user_nick(
    nick: str,
    is_external: bool = False,
    is_self: bool = False,
) -> Nick:
    nick = nick.replace(" ", shared.config.look.replace_space_in_nicks_with.value)
    suffix = shared.config.look.external_user_suffix.value if is_external else ""
    return Nick(
        nick_color(nick, is_self),
        nick,
        suffix,
        "user",
    )


def get_bot_nick(nick: str) -> Nick:
    nick = nick.replace(" ", shared.config.look.replace_space_in_nicks_with.value)
    return Nick(
        nick_color(nick),
        nick,
        shared.config.look.bot_user_suffix.value,
        "bot",
    )


class SlackUser:
    def __init__(self, workspace: SlackWorkspace, info: SlackUserInfo):
        self.workspace = workspace
        self._info = info

    @classmethod
    async def create(cls, workspace: SlackWorkspace, id: str):
        info_response = await workspace.api.fetch_user_info(id)
        return cls(workspace, info_response["user"])

    @property
    def id(self) -> str:
        return self._info["id"]

    @property
    def is_self(self) -> bool:
        return self.id == self.workspace.my_user.id

    @property
    def is_external(self) -> bool:
        return self._info["profile"]["team"] != self.workspace.id and (
            "enterprise_user" not in self._info
            or self._info["enterprise_user"]["enterprise_id"]
            != self.workspace.enterprise_id
        )

    @property
    def status_text(self) -> str:
        return self._info["profile"].get("status_text", "") or ""

    @property
    def status_emoji(self) -> str:
        status_emoji = self._info["profile"].get("status_emoji")
        if not status_emoji:
            return ""
        return get_emoji(status_emoji.strip(":"))

    @property
    def real_name(self) -> str:
        return self._info["profile"].get("real_name") or name_from_user_info(
            self.workspace, self._info
        )

    @property
    def nick(self) -> Nick:
        nick = name_from_user_info(self.workspace, self._info)
        return get_user_nick(nick, self.is_external, self.is_self)

    def update_info_json(self, info_json: SlackUserInfo):
        self._info.update(info_json)  # pyright: ignore [reportArgumentType, reportCallIssue]

        for conversation in self.workspace.open_conversations.values():
            if conversation.im_user_id == self.id:
                conversation.update_buffer_props()


class SlackBot:
    def __init__(self, workspace: SlackWorkspace, info: SlackBotInfo):
        self.workspace = workspace
        self._info = info

    @classmethod
    async def create(cls, workspace: SlackWorkspace, id: str):
        info_response = await workspace.api.fetch_bot_info(id)
        return cls(workspace, info_response["bot"])

    @property
    def nick(self) -> Nick:
        return get_bot_nick(self._info["name"])


class SlackUsergroup:
    def __init__(
        self, workspace: SlackWorkspace, info: Union[SlackUsergroupInfo, SlackSubteam]
    ):
        self.workspace = workspace
        self._info = info

    @classmethod
    async def create(cls, workspace: SlackWorkspace, id: str):
        info_response = await workspace.api.edgeapi.fetch_usergroups_info([id])
        if not info_response["results"] or info_response["results"][0]["id"] != id:
            raise SlackError(workspace, "usergroup_not_found")
        return cls(workspace, info_response["results"][0])

    def handle(self) -> str:
        return self._info["handle"]

    def update_info_json(self, info_json: Union[SlackUsergroupInfo, SlackSubteam]):
        self._info.update(info_json)
