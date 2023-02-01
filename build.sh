#!/bin/bash

shopt -s extglob

contents="$(cat slack/util.py slack/task.py slack/!(util|task).py main.py | \
  awk -v RS='\\([^)]+\\)' '/from.*import/ {gsub(/[[:space:]]+/, "", RT)} {ORS=RT} 1' | \
  grep -Ev '^from slack[. ]')"

echo "$contents" | grep '^from __future__' | sort -u > build/slack.py
echo "$contents" | grep -v '^from __future__' | grep -E '^(import|from)' | sort -u >> build/slack.py
echo "$contents" | grep -Ev '^(import|from)' | sed 's/^\( \+\)\(import\|from\).*/\1pass/' >> build/slack.py
