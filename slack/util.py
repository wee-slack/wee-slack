from __future__ import annotations

from functools import partial
from itertools import islice
from typing import Callable, Iterable, Iterator, List, Optional, TypeVar

import weechat

from slack.shared import WeechatCallbackReturnType, shared

T = TypeVar("T")


def get_callback_name(callback: Callable[..., WeechatCallbackReturnType]) -> str:
    callback_id = f"{callback.__name__}-{id(callback)}"
    shared.weechat_callbacks[callback_id] = callback
    return callback_id


def with_color(color: Optional[str], string: str, reset_color: str = "reset"):
    if color:
        return f"{weechat.color(color)}{string}{weechat.color(reset_color)}"
    else:
        return string


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
