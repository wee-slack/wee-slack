from __future__ import annotations

from typing import TYPE_CHECKING

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
    def nick(self):
        return self._info["name"]

    async def init(self):
        info = await self._api.fetch_users_info(self)
        if info["ok"] is False:
            # TODO: Handle error
            raise Exception("Failed fetching user info")
        self._info = info["user"]
