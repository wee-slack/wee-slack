from __future__ import annotations

from typing import Literal, TypedDict

from slack_api.slack_error import SlackErrorResponse

class SlackRtmConnectTeam(TypedDict):
    id: str
    name: str
    domain: str

class SlackRtmConnectSelf(TypedDict):
    id: str
    name: str

class SlackRtmConnectSuccessResponse(TypedDict):
    ok: Literal[True]
    url: str
    team: SlackRtmConnectTeam
    self: SlackRtmConnectSelf

SlackRtmConnectResponse = SlackRtmConnectSuccessResponse | SlackErrorResponse
