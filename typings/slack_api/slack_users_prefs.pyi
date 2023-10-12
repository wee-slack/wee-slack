from __future__ import annotations

from slack_api.slack_common import SlackErrorResponse
from typing_extensions import Literal, TypedDict, final

@final
class SlackUsersPrefs(TypedDict):
    muted_channels: str
    # Incomplete

@final
class SlackUsersPrefsGetSuccessResponse(TypedDict):
    ok: Literal[True]
    prefs: SlackUsersPrefs

SlackUsersPrefsGetResponse = SlackUsersPrefsGetSuccessResponse | SlackErrorResponse
