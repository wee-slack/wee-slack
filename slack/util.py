from __future__ import annotations

from functools import partial
from itertools import islice
from typing import (
    TYPE_CHECKING,
    Callable,
    Iterable,
    Iterator,
    List,
    Optional,
    Sequence,
    TypeVar,
    Union,
)
from urllib.parse import quote, unquote

import weechat

from slack.shared import WeechatCallbackReturnType, shared

if TYPE_CHECKING:
    from slack.task import Future

T = TypeVar("T")
T2 = TypeVar("T2")


def get_callback_name(callback: Callable[..., WeechatCallbackReturnType]) -> str:
    callback_id = f"{callback.__name__}-{id(callback)}"
    shared.weechat_callbacks[callback_id] = callback
    return callback_id


def get_resolved_futures(futures: Iterable[Future[T]]) -> List[T]:
    return [future.result() for future in futures if future.done_with_result()]


def with_color(color: Optional[str], string: str, reset_color: str = "default"):
    if color:
        return f"{weechat.color(color)}{string}{weechat.color(reset_color)}"
    else:
        return string


# Escape chars that have special meaning to Slack. Note that we do not
# (and should not) perform full HTML entity-encoding here.
# See https://api.slack.com/reference/surfaces/formatting#escaping for details.
def htmlescape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def unhtmlescape(text: str) -> str:
    return text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")


def url_encode_if_not_encoded(value: str) -> str:
    is_encoded = value != unquote(value)
    if is_encoded:
        return value
    else:
        return quote(value)


def get_cookies(cookie_config: str) -> str:
    cookie_pairs = [
        cookie.split("=", maxsplit=1) for cookie in cookie_config.split(";")
    ]
    if len(cookie_pairs) == 1 and len(cookie_pairs[0]) == 1:
        cookie_pairs[0].insert(0, "d")
    for cookie_pair in cookie_pairs:
        cookie_pair[0] = cookie_pair[0].strip()
        cookie_pair[1] = url_encode_if_not_encoded(cookie_pair[1].strip())
    return "; ".join("=".join(cookie_pair) for cookie_pair in cookie_pairs)


# From https://github.com/more-itertools/more-itertools/blob/v10.1.0/more_itertools/recipes.py#L93-L106
def take(n: int, iterable: Iterable[T]) -> List[T]:
    """Return first *n* items of the iterable as a list.

        >>> take(3, range(10))
        [0, 1, 2]

    If there are fewer than *n* items in the iterable, all of them are
    returned.

        >>> take(10, range(3))
        [0, 1, 2]

    """
    return list(islice(iterable, n))


# Modified from https://github.com/more-itertools/more-itertools/blob/v10.1.0/more_itertools/more.py#L149-L181
def chunked(iterable: Iterable[T], n: int, strict: bool = False) -> Iterator[List[T]]:
    """Break *iterable* into lists of length *n*:

        >>> list(chunked([1, 2, 3, 4, 5, 6], 3))
        [[1, 2, 3], [4, 5, 6]]

    The last yielded list will have fewer than *n* elements
    if the length of *iterable* is not divisible by *n*:

        >>> list(chunked([1, 2, 3, 4, 5, 6, 7, 8], 3))
        [[1, 2, 3], [4, 5, 6], [7, 8]]

    To use a fill-in value instead, see the :func:`grouper` recipe.

    """
    return iter(partial(take, n, iter(iterable)), [])


# From https://stackoverflow.com/a/5921708
def intersperse(lst: Sequence[Union[T, T2]], item: T2) -> List[Union[T, T2]]:
    """Inserts item between each item in lst"""
    result: List[Union[T, T2]] = [item] * (len(lst) * 2 - 1)
    result[0::2] = lst
    return result
