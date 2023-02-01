from typing import Dict, List

from slack_api.slack_common import SlackErrorResponse
from typing_extensions import Literal, NotRequired, TypedDict, final

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

@final
class SlackBotsInfoSuccessResponse(TypedDict):
    ok: Literal[True]
    bots: List[SlackBotInfo]

SlackBotsInfoResponse = SlackBotsInfoSuccessResponse | SlackErrorResponse
