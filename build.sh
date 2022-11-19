#!/bin/bash

contents="$(cat slack/*.py main.py | grep -Ev '^from slack[. ]')"

echo "$contents" | grep '^from __future__' | sort -u > build/slack.py
echo "$contents" | grep -v '^from __future__' | grep -E '^(import|from)' | sort -u >> build/slack.py
echo "$contents" | grep -Ev '^(import|from)' >> build/slack.py
