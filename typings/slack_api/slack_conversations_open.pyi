from __future__ import annotations

from slack_api.slack_common import SlackErrorResponse
from slack_api.slack_conversations_info import (
    SlackConversationsInfoIm,
    SlackConversationsInfoMpim,
)
from typing_extensions import Literal, NotRequired, TypedDict, final

@final
class SlackConversationsOpenSuccessResponse(TypedDict):
    ok: Literal[True]
    no_op: NotRequired[bool]  # Not returned when specifying multiple users
    already_open: NotRequired[bool]  # Not returned when specifying multiple users
    channel: (
        SlackConversationsInfoIm | SlackConversationsInfoMpim
    )  # only when specifying return_im=True

SlackConversationsOpenResponse = (
    SlackConversationsOpenSuccessResponse | SlackErrorResponse
)
