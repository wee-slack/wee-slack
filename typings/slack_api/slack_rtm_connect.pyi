from __future__ import annotations

from slack_api.slack_common import SlackErrorResponse
from typing_extensions import Literal, NotRequired, TypedDict, final

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
