#!/bin/sh
# Plays the stage path with the presenter key only (Space) at a given size and saves one screenshot per beat.
# usage: sh screens/shoot.sh <url> <out-dir> [width height]   (sign in first in the same agent-browser session for live)
set -u
U=$1; S=$2; W=${3:-1920}; H=${4:-1080}; SES=${SES:-neo-final}
mkdir -p "$S"
ab() { agent-browser --session "$SES" "$@"; }
idle() { [ "$(ab eval "(document.querySelector('.chat .card-h .end')?.textContent === 'Eve agent') && !document.querySelector('[data-playing]')")" = "true" ]; }
replies() { ab eval "document.querySelectorAll('.msg.neo .body').length" | tr -d '"'; }
press() { ab press Space >/dev/null; }
talk() { n=$(replies); press; until [ "$(replies)" -gt "$n" ] && idle; do sleep 2; done; sleep 2; }
ab set viewport "$W" "$H" >/dev/null
ab open "$U/" >/dev/null; sleep 3; ab screenshot "$S/0-open.png" >/dev/null
talk; ab screenshot "$S/1-attack.png" >/dev/null
talk; ab screenshot "$S/2-finding.png" >/dev/null
press; sleep 2.5; ab screenshot "$S/3-red-twin.png" >/dev/null
talk; ab screenshot "$S/4-fix.png" >/dev/null
press; sleep 2.5; ab screenshot "$S/5-green-twin.png" >/dev/null
talk; ab screenshot "$S/6-approve.png" >/dev/null
press; sleep 3; ab screenshot "$S/7-numbers.png" >/dev/null
press; sleep 2.5; ab screenshot "$S/8-radar.png" >/dev/null
ab eval "[...document.querySelectorAll('.msg.neo .body')].map(e=>e.textContent).join(' || ')"
