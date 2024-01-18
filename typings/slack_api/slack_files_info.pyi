from __future__ import annotations

from slack_api.slack_common import SlackErrorResponse
from typing_extensions import Literal, NotRequired, TypedDict, final

@final
class SlackFile(TypedDict):
    id: str
    created: int
    timestamp: int
    name: NotRequired[str]
    title: NotRequired[str]
    mimetype: NotRequired[str]
    filetype: str
    pretty_type: NotRequired[str]
    user: str
    user_team: NotRequired[str]
    editable: NotRequired[bool]
    size: NotRequired[int]
    mode: NotRequired[str]
    is_external: NotRequired[bool]
    external_type: NotRequired[str]
    is_public: NotRequired[bool]
    public_url_shared: NotRequired[bool]
    display_as_bot: NotRequired[bool]
    username: NotRequired[str]
    url_private: NotRequired[str]
    url_private_download: NotRequired[str]
    permalink: NotRequired[str]
    permalink_public: NotRequired[str]
    preview: NotRequired[str]
    editor: NotRequired[None]
    last_editor: NotRequired[str]
    non_owner_editable: NotRequired[bool]
    updated: NotRequired[int]
    is_starred: NotRequired[bool]
    has_rich_preview: NotRequired[bool]
    file_access: Literal["visible", "check_file_info", "file_not_found"]

    # only from files.info, not in conversations.history:
    # update_notification
    # shares
    # channels
    # groups
    # ims
    # has_more_shares
    # comments_count

@final
class SlackFilesInfoSuccessResponse(TypedDict):
    ok: Literal[True]
    content_html: str
    file: SlackFile
    # comments
    comments_count: int

SlackFilesInfoResponse = SlackFilesInfoSuccessResponse | SlackErrorResponse
