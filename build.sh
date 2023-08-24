#!/bin/bash

shopt -s extglob

contents="$(cat slack/python_compatibility.py slack/util.py slack/task.py slack/!(python_compatibility|util|task).py main.py | \
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
