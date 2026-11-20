#!/bin/sh
# Runs the NEO demo click path headless on a preview and saves one screenshot per step.
# usage: sh docs/demo-shots.sh https://<preview>.vercel.app   (bypass from ~/.local/state/neo/bypass)
set -u
U=${1:?preview url}
S=$(cd "$(dirname "$0")" && pwd)/shots
mkdir -p "$S"
B=$(cat ~/.local/state/neo/bypass)
ab() { agent-browser --session neo-demo "$@"; }
replies() { ab eval "document.querySelectorAll('.msg.neo .body').length" | tr -d '"'; }
idle() { [ "$(ab eval "document.querySelector('.chat .card-h .end')?.textContent")" = '"Eve agent"' ]; }
ask() { n=$(replies); ab find role button click --name "$1" >/dev/null; until [ "$(replies)" -gt "$n" ] && idle; do sleep 2; done; }
ab close >/dev/null 2>&1
ab set viewport 1440 900 >/dev/null
ab open "$U/?x-vercel-protection-bypass=$B&x-vercel-set-bypass-cookie=true" >/dev/null
sleep 3; ab screenshot "$S/01-open.png" >/dev/null
ask "Attack our demo app"; sleep 2; ab screenshot "$S/02-attack.png" >/dev/null
ask "What did you find?"; sleep 2; ab screenshot "$S/03-finding.png" >/dev/null
ab find role link click --name "Incident" >/dev/null; sleep 2; ab screenshot "$S/04-red-twin.png" >/dev/null
ab find role link click --name "Overview" >/dev/null; sleep 1
ask "Fix it"; sleep 3; ab screenshot "$S/05-fixed.png" >/dev/null
ab find role link click --name "Incident" >/dev/null; sleep 2; ab screenshot "$S/06-green-twin.png" >/dev/null
ab find role link click --name "Overview" >/dev/null; sleep 1
ask "Approved"; sleep 2; ab screenshot "$S/07-approved.png" >/dev/null
ab find role link click --name "Numbers" >/dev/null; sleep 2.5; ab screenshot "$S/08-numbers.png" >/dev/null
ab find role link click --name "Radar" >/dev/null; sleep 2; ab screenshot "$S/09-radar.png" >/dev/null
ab find role link click --name "Overview" >/dev/null; sleep 1
ab eval "[...document.querySelectorAll('.msg.neo .body')].map(e=>e.textContent).join(' || ')"
ls "$S"
