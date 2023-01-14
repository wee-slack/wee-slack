from __future__ import annotations

from typing import Literal, TypedDict

class SlackRtmConnectTeam(TypedDict):
    id: str
    name: str
    domain: str

class SlackRtmConnectSelf(TypedDict):
    id: str
    name: str

class SlackRtmConnectErrorResponse(TypedDict):
    ok: Literal[False]
    error: str

class SlackRtmConnectSuccessResponse(TypedDict):
    ok: Literal[True]
    url: str
    team: SlackRtmConnectTeam
    self: SlackRtmConnectSelf

SlackRtmConnectResponse = SlackRtmConnectSuccessResponse | SlackRtmConnectErrorResponse
