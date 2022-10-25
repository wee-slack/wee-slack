#!/bin/bash

contents="$(cat slack/globals.py slack/log.py slack/util.py slack/task.py slack/http.py slack/api.py slack/config.py slack/main.py slack.py | grep -Ev '^from (\.|slack)' | sed 's/G\.//')"

echo "$contents" | grep '^from __future__' | sort -u > combined.py
echo "$contents" | grep -v '^from __future__' | grep -E '^(import|from)' | sort -u >> combined.py
echo "$contents" | grep -Ev '^(import|from)' >> combined.py
