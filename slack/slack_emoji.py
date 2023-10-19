from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING, Dict, Optional

import weechat

from slack.error import store_and_format_exception
from slack.log import print_error
from slack.shared import shared

if TYPE_CHECKING:
    from typing_extensions import NotRequired, TypedDict, assert_never

    class EmojiSkinVariation(TypedDict):
        name: str
        unicode: str

    class Emoji(TypedDict):
        aliasOf: NotRequired[str]
        name: str
        skinVariations: NotRequired[Dict[str, EmojiSkinVariation]]
        unicode: str


def load_standard_emojis() -> Dict[str, Emoji]:
    weechat_dir = weechat.info_get("weechat_data_dir", "") or weechat.info_get(
        "weechat_dir", ""
    )
    weechat_sharedir = weechat.info_get("weechat_sharedir", "")
    local_weemoji, global_weemoji = (
        f"{path}/weemoji.json" for path in (weechat_dir, weechat_sharedir)
    )
    path = (
        global_weemoji
        if os.path.exists(global_weemoji) and not os.path.exists(local_weemoji)
        else local_weemoji
    )
    if not os.path.exists(path):
        return {}

    try:
        with open(path) as f:
            emojis: Dict[str, Emoji] = json.loads(f.read())

            emojis_skin_tones: Dict[str, Emoji] = {
                skin_tone["name"]: {
                    "name": skin_tone["name"],
                    "unicode": skin_tone["unicode"],
                }
                for emoji in emojis.values()
                if "skinVariations" in emoji
                for skin_tone in emoji["skinVariations"].values()
            }

            emojis.update(emojis_skin_tones)
            return emojis
    except Exception as e:
        print_error(f"couldn't read weemoji.json: {store_and_format_exception(e)}")
        return {}


def get_emoji(emoji_name: str, skin_tone: Optional[int] = None) -> str:
    emoji_name_with_colons = f":{emoji_name}:"
    if shared.config.look.render_emoji_as.value == "name":
        return emoji_name_with_colons

    emoji_item = shared.standard_emojis.get(emoji_name)
    if emoji_item is None:
        return emoji_name_with_colons

    skin_tone_item = (
        emoji_item.get("skinVariations", {}).get(str(skin_tone)) if skin_tone else None
    )
    emoji_unicode = (
        skin_tone_item["unicode"] if skin_tone_item else emoji_item["unicode"]
    )

    if shared.config.look.render_emoji_as.value == "emoji":
        return emoji_unicode
    elif shared.config.look.render_emoji_as.value == "both":
        return f"{emoji_unicode}({emoji_name_with_colons})"
    else:
        assert_never(shared.config.look.render_emoji_as.value)
