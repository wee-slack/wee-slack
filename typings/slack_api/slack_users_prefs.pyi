from __future__ import annotations

from slack_api.slack_common import SlackErrorResponse
from typing_extensions import Literal, NotRequired, TypedDict, final

NotificationType = Literal["everything", "mentions_dms", "nothing"]

class AllNotificationsPrefsChannel(TypedDict):
    desktop: NotificationType
    mobile: NotificationType
    follow_all_threads: NotRequired[bool]
    muted: bool
    suppress_at_channel: bool

class AllNotificationsPrefsGlobal(TypedDict):
    desktop_sound: str
    global_desktop: NotificationType
    global_keywords: str  # Comma-separated list of keywords
    global_mobile: NotificationType
    global_mpdm_desktop: NotificationType
    global_mpdm_mobile: NotificationType
    mobile_sound: str
    no_text_in_notifications: bool
    push_idle_wait: int
    push_show_preview: bool
    threads_everything: bool

AllNotificationsPrefs = TypedDict(
    "AllNotificationsPrefs",
    {
        "channels": dict[str, AllNotificationsPrefsChannel],
        "global": AllNotificationsPrefsGlobal,
    },
)

@final
class SlackUsersPrefs(TypedDict):
    muted_channels: str  # Commaseparated list of channel IDs
    all_notifications_prefs: str  # JSON string of AllNotificationsPrefs
    # Incomplete

@final
class SlackUsersPrefsGetSuccessResponse(TypedDict):
    ok: Literal[True]
    prefs: SlackUsersPrefs

SlackUsersPrefsGetResponse = SlackUsersPrefsGetSuccessResponse | SlackErrorResponse
