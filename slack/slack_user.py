from __future__ import annotations

from typing import TYPE_CHECKING

import weechat

from slack.shared import shared
from slack.util import with_color

if TYPE_CHECKING:
    from slack_api.slack_bots_info import SlackBotInfo
    from slack_api.slack_usergroups_info import SlackUsergroupInfo
    from slack_api.slack_users_info import SlackUserInfo

    from slack.slack_workspace import SlackWorkspace


def nick_color(nick: str) -> str:
    return weechat.info_get("nick_color_name", nick)


# TODO: Probably need to do some mapping here based on the existing users, in case some has been changed to avoid duplicate names
def _name_from_user_info(workspace: SlackWorkspace, info: SlackUserInfo) -> str:
    display_name = info["profile"].get("display_name")
    if display_name and not workspace.config.use_real_names.value:
        return display_name

    return info["profile"].get("display_name") or info.get("real_name") or info["name"]


def name_from_user_info_without_spaces(
    workspace: SlackWorkspace, info: SlackUserInfo
) -> str:
    return _name_from_user_info(workspace, info).replace(" ", "")


def format_bot_nick(nick: str, colorize: bool = False) -> str:
    nick = nick.replace(" ", "")

    if colorize:
        nick = with_color(nick_color(nick), nick)

    return nick + shared.config.look.bot_user_suffix.value


class SlackUser:
    def __init__(self, workspace: SlackWorkspace, info: SlackUserInfo):
        self.workspace = workspace
        self._info = info

    @classmethod
    async def create(cls, workspace: SlackWorkspace, id: str):
        info_response = await workspace.api.fetch_user_info(id)
        return cls(workspace, info_response["user"])

    def nick(self, colorize: bool = False) -> str:
        nick = self._name_without_spaces()

        if colorize:
            nick = with_color(self._nick_color(), nick)

        if self._info["profile"]["team"] != self.workspace.id:
            nick += shared.config.look.external_user_suffix.value

        return nick

    def _name_without_spaces(self) -> str:
        return name_from_user_info_without_spaces(self.workspace, self._info)

    def _nick_color(self) -> str:
        if self._info["id"] == self.workspace.my_user._info["id"]:
            return weechat.config_string(
                weechat.config_get("weechat.color.chat_nick_self")
            )

        return nick_color(self._name_without_spaces())


class SlackBot:
    def __init__(self, workspace: SlackWorkspace, info: SlackBotInfo):
        self.workspace = workspace
        self._info = info

    @classmethod
    async def create(cls, workspace: SlackWorkspace, id: str):
        info_response = await workspace.api.fetch_bot_info(id)
        return cls(workspace, info_response["bot"])

    def nick(self, colorize: bool = False) -> str:
        return format_bot_nick(self._info["name"], colorize)


class SlackUsergroup:
    def __init__(self, workspace: SlackWorkspace, info: SlackUsergroupInfo):
        self.workspace = workspace
        self._info = info

    @classmethod
    async def create(cls, workspace: SlackWorkspace, id: str):
        info_response = await workspace.api.fetch_usergroups_info([id])
        # TODO: Handle failed ids
        usergroup_info = info_response["results"][0]
        return cls(workspace, usergroup_info)

    def handle(self) -> str:
        return self._info["handle"]
