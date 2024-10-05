from __future__ import annotations

from typing import Dict, List

from slack_api.slack_common import SlackErrorResponse
from slack_api.slack_conversations_info import SlackTopic
from slack_api.slack_users_conversations import SlackUsersConversationsNotIm
from slack_api.slack_users_info import SlackProfilePerson, SlackUserInfoCommon
from slack_api.slack_users_prefs import SlackUsersPrefs
from typing_extensions import Literal, NotRequired, TypedDict, final

@final
class SlackClientUserbootSelf(SlackUserInfoCommon):
    profile: SlackProfilePerson
    is_bot: Literal[False]
    first_login: int
    lob_sales_home_enabled: bool
    manual_presence: Literal["active"]

@final
class SlackClientUserbootTeam(TypedDict):
    id: str
    name: str
    domain: str
    # Incomplete

@final
class SlackClientUserbootIm(TypedDict):
    id: str
    created: int
    is_frozen: bool
    is_archived: bool
    is_im: Literal[True]
    is_org_shared: bool
    context_team_id: str
    updated: int
    is_shared: bool
    user: str
    last_read: str
    # latest seems to always be present, but is incorrectly set to the current timestamp for all conversations, so we delete the key and set it from client.counts instead
    latest: NotRequired[str]
    is_open: bool
    topic: NotRequired[SlackTopic]

@final
class SlackClientUserbootSubteams(TypedDict):
    self: List[str]

@final
class SlackClientUserbootSuccessResponse(TypedDict):
    ok: Literal[True]
    self: SlackClientUserbootSelf
    team: SlackClientUserbootTeam
    ims: List[SlackClientUserbootIm]
    # workspaces: List[]
    default_workspace: str
    # account_types
    # accept_tos_url
    is_open: List[str]
    # is_europe
    # translations_cache_ts
    # emoji_cache_ts
    # app_commands_cache_ts
    # cache_ts_version
    # dnd
    prefs: SlackUsersPrefs
    subteams: SlackClientUserbootSubteams
    # mobile_app_requires_upgrade
    starred: List[str]
    channels_priority: Dict[str, float]
    read_only_channels: List[str]
    non_threadable_channels: List[str]
    thread_only_channels: List[str]
    channels: List[SlackUsersConversationsNotIm]
    # cache_version
    slack_route: str
    # auth_min_last_fetched
    # can_access_client_v2
    # links

SlackClientUserbootResponse = SlackClientUserbootSuccessResponse | SlackErrorResponse
