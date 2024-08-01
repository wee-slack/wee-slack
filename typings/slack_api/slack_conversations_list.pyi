from typing import List

from slack_api.slack_common import SlackErrorResponse, SlackResponseMetadata
from slack_api.slack_conversations_info import SlackConversationsInfoPublic
from typing_extensions import Literal, TypedDict, final

@final
class SlackConversationsListPublicSuccessResponse(TypedDict):
    ok: Literal[True]
    channels: List[SlackConversationsInfoPublic]
    response_metadata: SlackResponseMetadata

SlackConversationsListPublicResponse = (
    SlackConversationsListPublicSuccessResponse | SlackErrorResponse
)
