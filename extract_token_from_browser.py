#!/usr/bin/env python3

import argparse
from configparser import ConfigParser
import json
from pathlib import Path
import sqlite3
import sys

parser = argparse.ArgumentParser(
    description="Extract Slack tokens from the browser files"
)
parser.add_argument(
    "browser", help="Which browser to extract from", metavar="<browser>"
)
args = parser.parse_args()

if args.browser != "firefox":
    print("Currently only firefox is supported by this script", file=sys.stderr)
    sys.exit(1)

if sys.platform.startswith("linux"):
    firefox_path = Path.home().joinpath(".mozilla/firefox")
elif sys.platform.startswith("darwin"):
    firefox_path = Path.home().joinpath("Library/Application Support/Firefox/Profiles")
else:
    print("Currently only Linux and macOS is supported by this script", file=sys.stderr)
    sys.exit(1)

profile_path = firefox_path.joinpath("profiles.ini")
profile_data = ConfigParser()
profile_data.read(profile_path)

default_profile_path = None
for key in profile_data.sections():
    if not key.startswith("Install"):
        continue

    value = profile_data[key]
    if "Default" in value:
        default_profile_path = firefox_path.joinpath(value["Default"])
        break

if default_profile_path is None:
    print("Couldn't find the default profile for Firefox", file=sys.stderr)
    sys.exit(1)

cookies_path = default_profile_path.joinpath("cookies.sqlite")
con = sqlite3.connect(f"file:{cookies_path}?immutable=1", uri=True)
cookie_d_query = (
    "SELECT value FROM moz_cookies WHERE host = '.slack.com' AND name = 'd'"
)
cookie_d_value = con.execute(cookie_d_query).fetchone()[0]
cookie_ds_query = (
    "SELECT value FROM moz_cookies WHERE host = '.slack.com' AND name = 'd-s'"
)
cookie_ds_values = con.execute(cookie_ds_query).fetchone()
con.close()

if cookie_ds_values:
    cookie_value = f"d={cookie_d_value};d-s={cookie_ds_values[0]}"
else:
    cookie_value = cookie_d_value

local_storage_path = default_profile_path.joinpath("webappsstore.sqlite")
con = sqlite3.connect(f"file:{local_storage_path}?immutable=1", uri=True)
local_storage_query = "SELECT value FROM webappsstore2 WHERE key = 'localConfig_v2'"
local_config_str = con.execute(local_storage_query).fetchone()[0]
con.close()

local_config = json.loads(local_config_str)
teams = [
    team for team in local_config["teams"].values() if not team["id"].startswith("E")
]
register_commands = [
    f"{team['name']}:\n/slack register {team['token']}:{cookie_value}" for team in teams
]
print("\n\n".join(register_commands))
