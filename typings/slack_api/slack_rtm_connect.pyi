from __future__ import annotations

from typing import Literal, TypedDict, final

from slack_api.slack_error import SlackErrorResponse

@final
class SlackRtmConnectTeam(TypedDict):
    id: str
    name: str
    domain: str

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
