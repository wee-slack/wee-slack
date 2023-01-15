from __future__ import annotations

from typing import TYPE_CHECKING

import weechat

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

    @property
    def nick(self) -> str:
        nick = self._nick_from_profile()
        return nick.replace(" ", "")

    async def init(self):
        info = await self._api.fetch_users_info(self)
        if info["ok"] is False:
            # TODO: Handle error
            raise Exception("Failed fetching user info")
        self._info = info["user"]

    def formatted_name(self, prepend: str = "", enable_color: bool = True):
        name = prepend + self.nick
        if enable_color:
            return with_color(self._nick_color(name), name)
        else:
            return name

    def _nick_from_profile(self) -> str:
        if self.workspace.config.use_real_names.value:
            return self._info["real_name"]

        display_name = self._info["profile"].get("display_name")
        return display_name or self._info["real_name"]

    def _nick_color(self, nick: str) -> str:
        if self.id == self.workspace.my_user.id:
            return weechat.config_string(
                weechat.config_get("weechat.color.chat_nick_self")
            )

        return weechat.info_get("nick_color_name", nick)
