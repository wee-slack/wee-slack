from typing import List

from slack_api.slack_common import SlackErrorResponse
from typing_extensions import Literal, NotRequired, TypedDict, final

@final
class SlackSearchMessageChannel(TypedDict):
    id: str
    name: NotRequired[str]
    is_channel: NotRequired[bool]
    is_group: NotRequired[bool]
    is_im: NotRequired[bool]
    is_private: NotRequired[bool]
    is_mpim: NotRequired[bool]

@final
class SlackSearchMessageMatch(TypedDict):
    iid: NotRequired[str]
    type: NotRequired[str]
    team: NotRequired[str]
    channel: SlackSearchMessageChannel
    user: NotRequired[str]
    username: NotRequired[str]
    ts: str
    text: str
    permalink: NotRequired[str]

@final
class SlackSearchMessagePagination(TypedDict):
    total_count: int
    page: int
    per_page: int
    page_count: int
    first: int
    last: int

@final
class SlackSearchMessages(TypedDict):
    total: int
    pagination: NotRequired[SlackSearchMessagePagination]
    matches: List[SlackSearchMessageMatch]

@final
class SlackSearchMessagesSuccessResponse(TypedDict):
    ok: Literal[True]
    query: str
    messages: SlackSearchMessages

SlackSearchMessagesResponse = SlackSearchMessagesSuccessResponse | SlackErrorResponse
