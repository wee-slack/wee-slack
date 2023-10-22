from typing import Dict

from slack_api.slack_common import SlackErrorResponse
from typing_extensions import Literal, TypedDict, final

@final
class SlackEmojiListSuccessResponse(TypedDict):
    ok: Literal[True]
    emoji: Dict[str, str]
    cache_ts: str

SlackEmojiListResponse = SlackEmojiListSuccessResponse | SlackErrorResponse
