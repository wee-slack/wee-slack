from __future__ import annotations

from typing import Literal, TypedDict, final

from slack_api.slack_error import SlackErrorResponse
from typing_extensions import NotRequired

@final
class SlackRtmConnectTeam(TypedDict):
    id: str
    name: str
    domain: str
    enterprise_id: NotRequired[str]
    enterprise_name: NotRequired[str]

@final
class SlackRtmConnectSelf(TypedDict):
    id: str
    name: str

@final
class SlackRtmConnectSuccessResponse(TypedDict):
    ok: Literal[True]
    url: str
    team: SlackRtmConnectTeam
    self: SlackRtmConnectSelf

SlackRtmConnectResponse = SlackRtmConnectSuccessResponse | SlackErrorResponse
