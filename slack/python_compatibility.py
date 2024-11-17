from __future__ import annotations

import traceback
from typing import List


# Copied from https://peps.python.org/pep-0616/ for support for Python < 3.9
def removeprefix(self: str, prefix: str) -> str:
    if self.startswith(prefix):
        return self[len(prefix) :]
    else:
        return self[:]


# Copied from https://peps.python.org/pep-0616/ for support for Python < 3.9
def removesuffix(self: str, suffix: str) -> str:
    if suffix and self.endswith(suffix):
        return self[: -len(suffix)]
    else:
        return self[:]


def format_exception_only(exc: BaseException) -> List[str]:
    return traceback.format_exception_only(type(exc), exc)


def format_exception(exc: BaseException) -> List[str]:
    return traceback.format_exception(type(exc), exc, exc.__traceback__)
