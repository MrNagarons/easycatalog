#!/bin/bash
set -e

# Virtual X display for nodriver (headless=False in fallback_nodriver.py).
DISPLAY_NUM="${DISPLAY_NUM:-99}"
export DISPLAY=":${DISPLAY_NUM}"

# Launch Xvfb in background; -nolisten tcp keeps it local.
Xvfb "${DISPLAY}" -screen 0 1440x2200x24 -nolisten tcp &
XVFB_PID=$!

# Wait briefly for the display socket to appear (max ~5s).
for _ in $(seq 1 50); do
    if [ -S "/tmp/.X11-unix/X${DISPLAY_NUM}" ]; then
        break
    fi
    sleep 0.1
done

# Forward termination signals to Xvfb as well.
trap 'kill -TERM "${XVFB_PID}" 2>/dev/null || true' TERM INT

# exec so uvicorn becomes PID 1 replacement and its stdout/stderr
# flow straight to docker logs.
exec "$@"
