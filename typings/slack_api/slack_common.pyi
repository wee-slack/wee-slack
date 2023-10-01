from typing_extensions import Literal, TypedDict, final

class SlackSuccessResponse(TypedDict):
    ok: Literal[True]

@final
class SlackErrorResponse(TypedDict):
    ok: Literal[False]
    error: str

SlackGenericResponse = SlackSuccessResponse | SlackErrorResponse

@final
class SlackResponseMetadata(TypedDict):
    next_cursor: str
