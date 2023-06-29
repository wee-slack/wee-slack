#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
from contextlib import contextmanager
from pathlib import Path
from sqlite3 import OperationalError
from typing import TYPE_CHECKING, Literal, assert_never

if TYPE_CHECKING:
    from _typeshed import StrPath


class AESCipher:
    def __init__(self, key):
        self.key = key

    def decrypt(self, text):
        cipher = AES.new(self.key, AES.MODE_CBC, IV=(b" " * 16))
        return self._unpad(cipher.decrypt(text))

    def _unpad(self, s):
        return s[: -ord(s[len(s) - 1 :])]


@contextmanager
def sqlite3_connect(path: StrPath):
    con = sqlite3.connect(f"file:{path}?immutable=1", uri=True)
    try:
        yield con
    finally:
        con.close()


def get_cookies(
    cookies_path: StrPath, cookie_d_query: str, cookie_ds_query: str
) -> tuple[str, str | None]:
    with sqlite3_connect(cookies_path) as con:
        cookie_d_value = con.execute(cookie_d_query).fetchone()
        cookie_ds_value = con.execute(cookie_ds_query).fetchone()
        if cookie_d_value and cookie_ds_value:
            return cookie_d_value[0], cookie_ds_value[0]
        elif cookie_d_value:
            return cookie_d_value[0], None
        else:
            print(
                f"Couldn't find the 'd' cookie value in {cookies_path}", file=sys.stderr
            )
            sys.exit(1)


parser = argparse.ArgumentParser(
    description="Extract Slack tokens from the browser files"
)
parser.add_argument(
    "browser", help="Which browser to extract from", metavar="<browser>"
)
parser.add_argument(
    "--profile", help="Profile to look up cookies for", metavar="<profile>", nargs="?"
)
args = parser.parse_args()

browser: Literal["firefox", "chrome"]

if sys.platform.startswith("linux"):
    chrome_key_iterations = 1
    if args.browser == "firefox-snap":
        browser = "firefox"
        browser_data = Path.home().joinpath("snap/firefox/common/.mozilla/firefox")
    elif args.browser == "firefox":
        browser = "firefox"
        browser_data = Path.home().joinpath(".mozilla/firefox")
    elif args.browser == "chromium":
        browser = "chrome"
        browser_data = Path.home().joinpath(".config/chromium")
    elif args.browser in ["chrome", "chrome-beta"]:
        browser = "chrome"
        browser_data = Path.home().joinpath(".config/google-%s" % args.browser)
    else:
        print(
            f'Unsupported browser "{args.browser}" on platform Linux.', file=sys.stderr
        )
        sys.exit(1)
elif sys.platform.startswith("darwin"):
    chrome_key_iterations = 1003
    if args.browser in ["firefox", "firefox-snap"]:
        browser = "firefox"
        browser_data = Path.home().joinpath(
            "Library/Application Support/Firefox/Profiles"
        )
    elif args.browser == "chromium":
        browser = "chrome"
        browser_data = Path.home().joinpath("Library/Application Support/Chromium")
    elif args.browser in ["chrome", "chrome-beta"]:
        browser = "chrome"
        browser_data = Path.home().joinpath("Library/Application Support/Google/Chrome")
    else:
        print(
            f'Unsupported browser "{args.browser}" on platform macOS.', file=sys.stderr
        )
        sys.exit(1)
else:
    print("Currently only Linux and macOS is supported by this script", file=sys.stderr)
    sys.exit(1)

profile = args.profile

if browser == "firefox":
    if not profile:
        profile = "*.default*"

    default_profile_path = max(
        [x for x in browser_data.glob(profile)], key=os.path.getctime
    )
    if not default_profile_path:
        print("Couldn't find the default profile for Firefox", file=sys.stderr)
        sys.exit(1)

    cookies_path = default_profile_path.joinpath("cookies.sqlite")
    cookie_d_query = (
        "SELECT value FROM moz_cookies WHERE host = '.slack.com' " "AND name = 'd'"
    )
    cookie_ds_query = (
        "SELECT value FROM moz_cookies WHERE host = '.slack.com' " "AND name = 'd-s'"
    )

    cookie_d_value, cookie_ds_value = get_cookies(
        cookies_path, cookie_d_query, cookie_ds_query
    )

    local_storage_path = default_profile_path.joinpath("webappsstore.sqlite")
    local_storage_query = "SELECT value FROM webappsstore2 WHERE key = 'localConfig_v2'"
    local_config = None
    try:
        with sqlite3_connect(local_storage_path) as con:
            local_config_str = con.execute(local_storage_query).fetchone()[0]
            local_config = json.loads(local_config_str)
    except (OperationalError, TypeError):
        pass

elif browser == "chrome":
    import secretstorage
    from Crypto.Cipher import AES
    from Crypto.Protocol.KDF import PBKDF2
    from plyvel import DB
    from plyvel._plyvel import IOError as pIOErr
    from secretstorage.exceptions import SecretStorageException

    if not profile:
        profile = "Default"

    default_profile_path = browser_data.joinpath(profile)

    cookies_path = default_profile_path.joinpath("Cookies")
    cookie_d_query = (
        "SELECT encrypted_value FROM cookies WHERE "
        "host_key = '.slack.com' AND name = 'd'"
    )
    cookie_ds_query = (
        "SELECT encrypted_value FROM cookies WHERE "
        "host_key = '.slack.com' AND name = 'd-s'"
    )

    cookie_d_value, cookie_ds_value = get_cookies(
        cookies_path, cookie_d_query, cookie_ds_query
    )

    bus = secretstorage.dbus_init()
    try:
        collection = secretstorage.get_default_collection(bus)
        for item in collection.get_all_items():
            if item.get_label() == "Chrome Safe Storage":
                passwd = item.get_secret()
                break
        else:
            raise Exception("Chrome password not found!")
    except SecretStorageException:
        print(
            "Error communicating org.freedesktop.secrets, trying 'peanuts' "
            "as a password",
            file=sys.stderr,
        )
        passwd = "peanuts"

    salt = b"saltysalt"
    length = 16
    key = PBKDF2(passwd, salt, length, chrome_key_iterations)
    cipher = AESCipher(key)

    cookie_d_value = cipher.decrypt(cookie_d_value[3:]).decode("utf8")
    if cookie_ds_value:
        cookie_ds_value = cipher.decrypt(cookie_ds_value[3:]).decode("utf8")

    leveldb_path = default_profile_path.joinpath("Local Storage/leveldb")
    try:
        db = DB(str(leveldb_path))
    except pIOErr:
        leveldb_copy = str(leveldb_path) + ".bak"
        os.makedirs(leveldb_copy, exist_ok=True)
        shutil.copytree(leveldb_path, leveldb_copy, dirs_exist_ok=True)
        print(
            "Leveldb was locked by a running browser - made an online copy "
            f"of it in {leveldb_copy}",
            file=sys.stderr,
        )
        db = DB(str(leveldb_copy))

    local_storage_value = db.get(b"_https://app.slack.com\x00\x01localConfig_v2")
    local_config = json.loads(local_storage_value[1:])

else:
    assert_never(browser)

if cookie_ds_value:
    cookie_value = f"d={cookie_d_value};d-s={cookie_ds_value}"
else:
    cookie_value = cookie_d_value

if local_config:
    teams = [
        team
        for team in local_config["teams"].values()
        if not team["id"].startswith("E")
    ]
else:
    teams = [
        {
            "token": "<token>",
            "name": "Couldn't find any tokens automatically, but you can try to extract it manually as described in the readme and register the team like this",
        }
    ]

register_commands = [
    f"{team['name']}:\n/slack register {team['token']}:{cookie_value}" for team in teams
]
print("\n\n".join(register_commands))
