from __future__ import annotations

from typing import TYPE_CHECKING, Union

import weechat

from slack.error import SlackError
from slack.shared import shared
from slack.slack_emoji import get_emoji
from slack.util import with_color

if TYPE_CHECKING:
    from slack_api.slack_bots_info import SlackBotInfo
    from slack_api.slack_conversations_history import SlackMessageUserProfile
    from slack_api.slack_usergroups_info import SlackUsergroupInfo
    from slack_api.slack_users_info import SlackProfile, SlackUserInfo

    from slack.slack_workspace import SlackWorkspace


def nick_color(nick: str, is_self: bool = False) -> str:
    if is_self:
        return weechat.config_string(weechat.config_get("weechat.color.chat_nick_self"))

    return weechat.info_get("nick_color_name", nick)


# TODO: Probably need to do some mapping here based on the existing users, in case some has been changed to avoid duplicate names
def name_from_user_profile(
    workspace: SlackWorkspace,
    profile: Union[SlackProfile, SlackMessageUserProfile],
    fallback_name: str,
) -> str:
    display_name = profile.get("display_name")
    if display_name and not workspace.config.use_real_names:
        return display_name

    return profile.get("display_name") or profile.get("real_name") or fallback_name


def name_from_user_info(workspace: SlackWorkspace, info: SlackUserInfo) -> str:
    return name_from_user_profile(
        workspace, info["profile"], info.get("real_name") or info["name"]
    )


def format_user_nick(
    nick: str,
    colorize: bool = False,
    only_nick: bool = False,
    is_external: bool = False,
    is_self: bool = False,
) -> str:
    nick = nick.replace(" ", shared.config.look.replace_space_in_nicks_with.value)

    if colorize:
        nick = with_color(nick_color(nick, is_self), nick)

    if not only_nick and is_external:
        nick += shared.config.look.external_user_suffix.value

    return nick


def format_bot_nick(nick: str, colorize: bool = False, only_nick: bool = False) -> str:
    nick = nick.replace(" ", shared.config.look.replace_space_in_nicks_with.value)

    if colorize:
        nick = with_color(nick_color(nick), nick)

    if not only_nick:
        nick += shared.config.look.bot_user_suffix.value

    return nick


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

    def nick(self, colorize: bool = False, only_nick: bool = False) -> str:
        nick = name_from_user_info(self.workspace, self._info)
        return format_user_nick(
            nick, colorize, only_nick, self.is_external, self.is_self
        )

    def nick_color(self) -> str:
        return nick_color(self.nick(colorize=False, only_nick=True), self.is_self)

    def update_info_json(self, info_json: SlackUserInfo):
        self._info.update(info_json)  # pyright: ignore [reportGeneralTypeIssues]
        self._rendered_prefix = None
        self._rendered_message = None
        self._parsed_message = None


class SlackBot:
    def __init__(self, workspace: SlackWorkspace, info: SlackBotInfo):
        self.workspace = workspace
        self._info = info

    @classmethod
    async def create(cls, workspace: SlackWorkspace, id: str):
        info_response = await workspace.api.fetch_bot_info(id)
        return cls(workspace, info_response["bot"])

    def nick(self, colorize: bool = False, only_nick: bool = False) -> str:
        return format_bot_nick(
            self._info["name"], colorize=colorize, only_nick=only_nick
        )

    def nick_color(self):
        return nick_color(self.nick(colorize=False, only_nick=True))


class SlackUsergroup:
    def __init__(self, workspace: SlackWorkspace, info: SlackUsergroupInfo):
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
