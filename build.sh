#!/bin/bash

shopt -s extglob

mkdir -p build

contents="$(cat slack/python_compatibility.py slack/util.py slack/shared.py slack/task.py slack/slack_buffer.py slack/slack_message.py slack/slack_message_buffer.py slack/!(python_compatibility|util|shared|task|slack_buffer|slack_message|slack_message_buffer).py main.py | \
  perl -0777 -pe 's/^( *from [^(\n]+\([^)]+\))/$1=~s|\n+||gr/mge' | \
  grep -Ev '^from slack[. ]')"

(
  echo "# This is a compiled file."
  echo "# For the original source, see https://github.com/wee-slack/wee-slack"
  echo
  echo "$contents" | grep '^from __future__' | sort -u
  echo "$contents" | grep -v '^from __future__' | grep -E '^(import|from) ' | sort -u
  echo "$contents" | grep -Ev '^(import|from) ' | sed 's/^\( \+\)\(import\|from\) .*/\1pass/'
) > build/slack.py

ruff_cmd="$(poetry run sh -c 'command -v ruff' 2>/dev/null || command -v ruff)"

if [ -x "$ruff_cmd" ]; then
  "$ruff_cmd" check -q --fix-only build/slack.py
  "$ruff_cmd" format -q build/slack.py
fi
