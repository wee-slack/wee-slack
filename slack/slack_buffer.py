from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from slack.slack_api import SlackApi
    from slack.slack_workspace import SlackWorkspace


class SlackBuffer(ABC):
    def __init__(self):
        self._buffer_pointer: Optional[str] = None

    @property
    @abstractmethod
    def workspace(self) -> SlackWorkspace:
        raise NotImplementedError()

    @property
    def api(self) -> SlackApi:
        return self.workspace.api

    @property
    def buffer_pointer(self) -> Optional[str]:
        return self._buffer_pointer

    @property
    def buffer_is_open(self) -> bool:
        return self.buffer_pointer is not None
