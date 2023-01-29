from typing_extensions import TypedDict, final

@final
class SlackResponseMetadata(TypedDict):
    next_cursor: str
