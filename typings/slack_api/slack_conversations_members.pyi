from typing import List

from slack_api.slack_common import SlackResponseMetadata
from slack_api.slack_error import SlackErrorResponse
from typing_extensions import Literal, TypedDict, final

@final
class SlackConversationsMembersSuccessResponse(TypedDict):
    ok: Literal[True]
    members: List[str]
    response_metadata: SlackResponseMetadata

SlackConversationsMembersResponse = (
    SlackConversationsMembersSuccessResponse | SlackErrorResponse
)
