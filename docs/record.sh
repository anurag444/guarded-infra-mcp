#!/usr/bin/env bash
# Regenerates docs/demo.gif from docs/demo.sh.
# Needs: asciinema, agg  (brew install asciinema agg)
set -euo pipefail
cd "$(dirname "$0")/.."
# --idle-time-limit must exceed the longest pause in the scripts, or agg
# compresses them and the output scrolls past unreadably fast.

# 1. README demo: the policy, the gate, the audit trail, the eval scores.
rm -f docs/demo.cast docs/demo.gif
asciinema rec --window-size 100x22 --command "docs/demo.sh" --overwrite docs/demo.cast
agg --font-size 20 --theme asciinema --speed 1.0 --idle-time-limit 10 \
    docs/demo.cast docs/demo.gif
rm -f docs/demo.cast

# 2. Social clip: one agent triage session, two refusals. MP4 because
#    LinkedIn and most feeds will not animate a GIF.
rm -f docs/agent.cast docs/agent-demo.gif docs/agent-demo.mp4
asciinema rec --window-size 108x20 --command ".venv/bin/python docs/agent_demo.py 2>/dev/null" \
    --overwrite docs/agent.cast
agg --font-size 20 --theme asciinema --speed 1.0 --idle-time-limit 10 \
    docs/agent.cast docs/agent-demo.gif
# yuv420p + even dimensions: required by most players, including LinkedIn's.
ffmpeg -v error -y -i docs/agent-demo.gif \
    -vf "scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p" \
    -movflags +faststart docs/agent-demo.mp4
rm -f docs/agent.cast

ls -lh docs/demo.gif docs/agent-demo.gif docs/agent-demo.mp4
