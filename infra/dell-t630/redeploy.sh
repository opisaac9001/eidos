#!/bin/sh
# Ship src/ and tests/ to the Dell, run the fast checks there, and restart his world without
# losing time: pause, restart the service (systemd brings it back), catch his clock up to
# the time of day, resume. Stops at the first failed check.
#
# Needs a tunnel to the observatory: ssh -N -L 127.0.0.1:28767:127.0.0.1:8767 isaac@pathos-server
# The operator token is read from the Dell each run, never stored here.
set -e
cd "$(dirname "$0")/../.."
HOST=${EIDOS_DELL:-isaac@pathos-server}
URL=${EIDOS_TUNNEL:-http://127.0.0.1:28767}
H="Host: 127.0.0.1:8767"
SSH="ssh -o BatchMode=yes $HOST"

TOKEN=$($SSH 'cut -d= -f2- /var/lib/eidos/operator.env')
rsync -az --delete --exclude __pycache__ src/ "$HOST:/srv/eidos/src/"
rsync -az --delete --exclude __pycache__ tests/ "$HOST:/srv/eidos/tests/"

CHECKS="test_folding test_web test_always_on_stream test_body test_providers test_impulses
  test_grounded_mind test_waking test_sleep_schedule test_reaching_out_for_a_reason
  test_fresh_thinking test_npc_cognition test_stream_variety test_day_rhythm test_world_news
  test_world_exploration test_natural_npcs test_daily_rhythm test_concerns_and_loops
  test_alertness test_gossip test_group_chat test_time_feel test_happenings test_life_lately
  test_believability test_self_interview test_feelings test_say_and_do test_memory_life
  test_http_gateway test_opinions test_messaging_you test_outreach test_life_story test_providers test_warm_voice test_daydreams
  test_group_plans test_day_recall test_inbound_invitations test_repair_jobs test_discretion test_british test_meal_drift test_nourishment
  test_mood_label test_timed_todos test_failure_isolation test_stream_ruts test_opinions
  test_freelance test_life_story"
FILES=$(for name in $CHECKS; do printf 'tests/%s.py ' "$name"; done)
RESULT=$($SSH "cd /srv/eidos && PYTHONPATH=src nice -n 10 .venv/bin/python -m pytest -q -p no:cacheprovider $FILES 2>&1 | tail -1")
echo "$RESULT"
case "$RESULT" in
  *failed*|*error*) echo "checks failed on the Dell; not restarting"; exit 1 ;;
  *passed*) ;;
  *) echo "checks did not report; not restarting"; exit 1 ;;
esac

control() {
  curl -s -m 600 -X POST -H "$H" -H "Content-Type: application/json" \
    -H "X-Eidos-Operator: $TOKEN" -d "$1" "$URL/api/control" >/dev/null
}
control '{"running": false, "minutes_per_tick": 15, "clock_mode": "realtime"}'
$SSH 'kill -KILL $(systemctl show -p MainPID --value eidos.service)'
sleep 15
i=0
until curl -s -m 5 -H "$H" "$URL/health" >/dev/null; do
  i=$((i + 1)); [ $i -gt 40 ] && { echo "service did not come back"; exit 1; }; sleep 5
done
HOURS=$(curl -s -m 300 -H "$H" "$URL/api/state" | python3 -c "
import json, sys
from datetime import datetime, timezone
his = datetime.fromisoformat(json.load(sys.stdin)['time']); now = datetime.now(timezone.utc)
gap = ((now.hour * 3600 + now.minute * 60 + now.second)
       - (his.hour * 3600 + his.minute * 60 + his.second)) / 3600
print(round(gap % 24 if gap > -1 else 0.001, 4) or 0.001)")
curl -s -m 900 -X POST -H "$H" -H "Content-Type: application/json" -H "X-Eidos-Operator: $TOKEN" \
  -d "{\"hours\": $HOURS}" "$URL/api/step" >/dev/null
control '{"running": true, "minutes_per_tick": 15, "clock_mode": "realtime"}'
curl -s -m 60 -H "$H" "$URL/api/state" | python3 -c "
import json, sys; s = json.load(sys.stdin); print('running', s['config']['running'], 'his time', s['time'])"
