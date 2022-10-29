#!/bin/bash

contents="$(cat slack/*.py slack.py | grep -Ev '^from slack[. ]')"

echo "$contents" | grep '^from __future__' | sort -u > combined.py
echo "$contents" | grep -v '^from __future__' | grep -E '^(import|from)' | sort -u >> combined.py
echo "$contents" | grep -Ev '^(import|from)' >> combined.py
