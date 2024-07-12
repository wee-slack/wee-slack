from typing import List

from slack_api.slack_common import SlackErrorResponse
from slack_api.slack_conversations_info import SlackConversationsInfoPublic
from typing_extensions import Literal, NotRequired, TypedDict

class SlackChannelsSearchSuccessResponse(TypedDict):
    ok: Literal[True]
    results: List[SlackConversationsInfoPublic]  # Might not be exactly correct
    member_channels: NotRequired[List[str]]

SlackChannelsSearchResponse = SlackChannelsSearchSuccessResponse | SlackErrorResponse
