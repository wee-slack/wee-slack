#!/bin/sh
# Script to build the unified slack.py file.
# This reads stdin and then repeatedly expands it by:
# - collecting __future__ imports in a separate buffer;
# - replacing `from src.foo import ...` imports with the contents of src/foo
#   iff it hasn't seen an import of that file before;
# - deleting `from src.foo import ...` imports that it has seen before;
# - and setting WEECHAT_SCRIPT_SPLIT to False so the script itself knows that
#   it has been unified.
#
# When no more __future__ or src.foo imports exist, it prepends all the saved
# __future__ imports and emits the result.

set -e
shopt -s lastpipe

declare -A FUTURE_IMPORTS
declare -A FILE_IMPORTS

function replace_imports() {
  local nrof_imports=0
  >"$2"
  cat "$1" | while IFS='' read -r line; do
    case "$line" in
      "WEECHAT_SCRIPT_SPLIT = True")
        echo "WEECHAT_SCRIPT_SPLIT = False" >> "$2"
        ;;
      "from __future__ import"*)
        FUTURE_IMPORTS["$line"]="$line"
        ;;
      "from src."*" import "*)
        local import="$(echo "$line" | sed -E 's,from src\.([^ ]+) import .*,\1,')"
        if [[ ! "${FILE_IMPORTS[$import]}" ]]; then
          # Haven't seen this one before.
          FILE_IMPORTS["$import"]="$import"
          cat "src/$import.py" >> "$2"
          ((++nrof_imports))
        fi
        ;;
      *)
        printf '%s\n' "$line" >> "$2"
        ;;
    esac
  done
  return $nrof_imports
}

cat > /tmp/$$.in

while ! replace_imports /tmp/$$.in /tmp/$$.out; do
  mv /tmp/$$.out /tmp/$$.in
done

printf '%s\n' "${FUTURE_IMPORTS[@]}"
cat /tmp/$$.out
