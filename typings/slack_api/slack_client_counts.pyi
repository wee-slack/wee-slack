from __future__ import annotations

from typing import List

from slack_api.slack_common import SlackErrorResponse
from typing_extensions import Literal, TypedDict, final

@final
class SlackClientCountsThreads(TypedDict):
    has_unreads: bool
    mention_count: int

@final
class SlackClientCountsConversation(TypedDict):
    id: str
    last_read: str
    latest: str
    updated: str
    history_invalid: str
    mention_count: int
    has_unreads: bool

@final
class SlackClientCountsChannelBadges(TypedDict):
    channels: int
    dms: int
    app_dms: int
    thread_mentions: int
    thread_unreads: int

@final
class SlackClientCountsAlerts(TypedDict):
    pass

@final
class SlackClientCountsSaved(TypedDict):
    uncompleted_count: int
    uncompleted_overdue_count: int

@final
class SlackClientCountsSuccessResponse(TypedDict):
    ok: Literal[True]
    threads: SlackClientCountsThreads
    channels: List[SlackClientCountsConversation]
    mpims: List[SlackClientCountsConversation]
    ims: List[SlackClientCountsConversation]
    channel_badges: SlackClientCountsChannelBadges
    alerts: SlackClientCountsAlerts
    saved: SlackClientCountsSaved

SlackClientCountsResponse = SlackClientCountsSuccessResponse | SlackErrorResponse
