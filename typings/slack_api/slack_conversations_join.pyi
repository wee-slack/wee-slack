from __future__ import annotations

from slack_api.slack_common import SlackErrorResponse
from typing_extensions import Literal, TypedDict, final

@final
class SlackConversationsJoinChannel(TypedDict):
    id: str
    # incomplete

@final
class SlackConversationsJoinSuccessResponse(TypedDict):
    ok: Literal[True]
    channel: SlackConversationsJoinChannel

SlackConversationsJoinResponse = (
    SlackConversationsJoinSuccessResponse | SlackErrorResponse
)
