from typing_extensions import Literal, TypedDict, final

@final
class SlackErrorResponse(TypedDict):
    ok: Literal[False]
    error: str
