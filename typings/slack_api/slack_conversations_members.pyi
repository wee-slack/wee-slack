from typing import List

from slack_api.slack_common import SlackErrorResponse, SlackResponseMetadata
from typing_extensions import Literal, TypedDict, final

@final
class SlackConversationsMembersSuccessResponse(TypedDict):
    ok: Literal[True]
    members: List[str]
    response_metadata: SlackResponseMetadata

SlackConversationsMembersResponse = (
    SlackConversationsMembersSuccessResponse | SlackErrorResponse
)
