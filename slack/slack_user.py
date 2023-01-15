from __future__ import annotations

from typing import TYPE_CHECKING

import weechat

from slack.shared import shared
from slack.util import with_color

if TYPE_CHECKING:
    from slack.slack_workspace import SlackApi, SlackWorkspace


class SlackUser:
    def __init__(self, workspace: SlackWorkspace, id: str):
        self.workspace = workspace
        self.id = id

    @property
    def _api(self) -> SlackApi:
        return self.workspace.api

    async def init(self):
        info = await self._api.fetch_users_info(self)
        if info["ok"] is False:
            # TODO: Handle error
            raise Exception("Failed fetching user info")
        self._info = info["user"]

    def nick(self, colorize: bool = False) -> str:
        nick = self._name_without_spaces()

        if colorize:
            nick = with_color(self._nick_color(), nick)

        if self._info["profile"]["team"] != self.workspace.id:
            nick += shared.config.look.external_user_suffix.value

        return nick

    def _name_from_profile(self) -> str:
        display_name = self._info["profile"].get("display_name")
        if display_name and not self.workspace.config.use_real_names.value:
            return display_name

        return (
            self._info["profile"].get("display_name")
            or self._info.get("real_name")
            or self._info["name"]
        )

    def _name_without_spaces(self) -> str:
        return self._name_from_profile().replace(" ", "")

    def _nick_color(self) -> str:
        if self.id == self.workspace.my_user.id:
            return weechat.config_string(
                weechat.config_get("weechat.color.chat_nick_self")
            )

        return weechat.info_get("nick_color_name", self._name_without_spaces())
