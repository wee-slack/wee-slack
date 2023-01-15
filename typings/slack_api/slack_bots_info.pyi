from typing import Dict, List, Literal, TypedDict, final

from slack_api.slack_error import SlackErrorResponse
from typing_extensions import NotRequired

class SlackBotInfo(TypedDict):
    id: str
    deleted: bool
    name: str
    updated: int
    app_id: str
    user_id: NotRequired[str]
    icons: Dict[str, str]

@final
class SlackBotInfoSuccessResponse(TypedDict):
    ok: Literal[True]
    bot: SlackBotInfo

SlackBotInfoResponse = SlackBotInfoSuccessResponse | SlackErrorResponse
