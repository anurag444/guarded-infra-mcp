#!/usr/bin/env bash
# Regenerates docs/demo.gif from docs/demo.sh.
# Needs: asciinema, agg  (brew install asciinema agg)
set -euo pipefail
cd "$(dirname "$0")/.."
rm -f docs/demo.cast docs/demo.gif
asciinema rec --window-size 100x22 --command "docs/demo.sh" --overwrite docs/demo.cast
# --idle-time-limit must exceed the longest Sleep in demo.sh, or agg
# compresses the pauses and the output scrolls past unreadably fast.
agg --font-size 20 --theme asciinema --speed 1.0 --idle-time-limit 10 \
    docs/demo.cast docs/demo.gif
rm -f docs/demo.cast
ls -lh docs/demo.gif
