from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from slack.slack_workspace import SlackApi, SlackWorkspace


class SlackUser:
    def __init__(self, workspace: SlackWorkspace, id: str):
        self.workspace = workspace
        self.id = id
        self.name: str

    @property
    def api(self) -> SlackApi:
        return self.workspace.api

    async def init(self):
        info = await self.api.fetch("users.info", {"user": self.id})
        self.name = info["user"]["name"]
