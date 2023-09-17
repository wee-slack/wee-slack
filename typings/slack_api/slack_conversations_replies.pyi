from typing import List

from slack_api.slack_common import SlackErrorResponse, SlackResponseMetadata
from slack_api.slack_conversations_history import (
    SlackMessageStandardCommon,
    SlackMessageThreadBroadcastFinal,
    SlackMessageThreadParentNotSubscribedFinal,
    SlackMessageThreadParentSubscribedFinal,
)
from typing_extensions import Literal, NotRequired, TypedDict, final

class SlackMessageThreadCommon(SlackMessageStandardCommon):
    thread_ts: str

@final
class SlackMessageThread(SlackMessageThreadCommon):
    parent_user_id: str

@final
class SlackConversationsRepliesSuccessResponse(TypedDict):
    ok: Literal[True]
    messages: List[
        SlackMessageThreadParentNotSubscribedFinal
        | SlackMessageThreadParentSubscribedFinal
        | SlackMessageThreadBroadcastFinal
        | SlackMessageThread
    ]
    has_more: bool
    response_metadata: NotRequired[SlackResponseMetadata]

SlackConversationsRepliesResponse = (
    SlackConversationsRepliesSuccessResponse | SlackErrorResponse
)
