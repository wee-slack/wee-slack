from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from slack.slack_api import SlackApi
    from slack.slack_workspace import SlackWorkspace


class SlackBuffer(ABC):
    @property
    @abstractmethod
    def workspace(self) -> SlackWorkspace:
        raise NotImplementedError()

    @property
    def api(self) -> SlackApi:
        return self.workspace.api
