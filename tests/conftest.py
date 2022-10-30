import importlib
import importlib.machinery
import sys

from slack.shared import shared


# Copied from https://stackoverflow.com/a/72721573
def import_stub(stubs_path: str, module_name: str):
    sys.path_hooks.insert(
        0,
        importlib.machinery.FileFinder.path_hook(
            (importlib.machinery.SourceFileLoader, [".pyi"])
        ),
    )
    sys.path.insert(0, stubs_path)

    try:
        return importlib.import_module(module_name)
    finally:
        sys.path.pop(0)
        sys.path_hooks.pop(0)


import_stub("typings", "weechat")

shared.weechat_version = 0x3080000
shared.weechat_callbacks = {}
