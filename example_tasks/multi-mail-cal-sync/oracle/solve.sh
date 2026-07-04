#!/usr/bin/env bash
set -euo pipefail

# ─── Helper: find event ID by keyword in summary ────────────────────────
find_event_id() {
    local keyword="$1"
    gws calendar events list \
      --params '{"calendarId": "primary", "maxResults": 100}' 2>/dev/null \
      | python3 -c "
import sys, json
data = json.load(sys.stdin)
kw = '${keyword}'.lower()
for e in data.get('items', []):
    if kw in e.get('summary', '').lower():
        print(e['id'])
        break
" || true
}

# ─── Helper: get event JSON ─────────────────────────────────────────────
get_event() {
    local event_id="$1"
    gws calendar events get \
      --params "{\"calendarId\": \"primary\", \"eventId\": \"$event_id\"}"
}

# ─── Helper: compute date N days from today ─────────────────────────────
date_offset() {
    python3 -c "
from datetime import datetime, timedelta, timezone
d = datetime.now(timezone.utc) + timedelta(days=$1)
print(d.strftime('%Y-%m-%d'))
"
}

# ─── CREATE 1: Coffee chat — Thu 3pm, Blue Bottle ──────────────────────
THU=$(python3 -c "
from datetime import datetime, timedelta, timezone
now = datetime.now(timezone.utc)
days_ahead = (3 - now.weekday()) % 7  # Thursday=3
if days_ahead == 0: days_ahead = 7
d = now + timedelta(days=days_ahead)
print(d.strftime('%Y-%m-%d'))
")

gws calendar events insert \
  --params '{"calendarId": "primary"}' \
  --json "{
    \"summary\": \"Coffee chat with Dana\",
    \"location\": \"Blue Bottle, Mint St\",
    \"description\": \"Coffee catch-up.\",
    \"start\": {\"dateTime\": \"${THU}T15:00:00\", \"timeZone\": \"America/Los_Angeles\"},
    \"end\": {\"dateTime\": \"${THU}T16:00:00\", \"timeZone\": \"America/Los_Angeles\"},
    \"attendees\": [{\"email\": \"dana@nexus.test\"}]
  }" > /dev/null

echo "Created: Coffee chat Thu 3pm"

# ─── CREATE 2: Lunch Monday — 12pm, Flour+Water ────────────────────────
MON=$(python3 -c "
from datetime import datetime, timedelta, timezone
now = datetime.now(timezone.utc)
days_ahead = (0 - now.weekday()) % 7  # Monday=0
if days_ahead == 0: days_ahead = 7
d = now + timedelta(days=days_ahead)
print(d.strftime('%Y-%m-%d'))
")

gws calendar events insert \
  --params '{"calendarId": "primary"}' \
  --json "{
    \"summary\": \"Lunch with Marcus\",
    \"location\": \"Flour+Water\",
    \"description\": \"Lunch catch-up.\",
    \"start\": {\"dateTime\": \"${MON}T12:00:00\", \"timeZone\": \"America/Los_Angeles\"},
    \"end\": {\"dateTime\": \"${MON}T13:00:00\", \"timeZone\": \"America/Los_Angeles\"},
    \"attendees\": [{\"email\": \"marcus@nexus.test\"}]
  }" > /dev/null

echo "Created: Lunch Monday 12pm"

# ─── CREATE 3: Dentist — next Mon 9:30am, 450 Sutter ─────────────────────
gws calendar events insert \
  --params '{"calendarId": "primary"}' \
  --json "{
    \"summary\": \"Dentist — Cleaning\",
    \"location\": \"450 Sutter St, Suite 800, San Francisco\",
    \"description\": \"Dental cleaning appointment.\",
    \"start\": {\"dateTime\": \"${MON}T11:00:00\", \"timeZone\": \"America/Los_Angeles\"},
    \"end\": {\"dateTime\": \"${MON}T12:00:00\", \"timeZone\": \"America/Los_Angeles\"}
  }" > /dev/null

echo "Created: Dentist Mon 11am"

# ─── CREATE 4: Hike Lands End — Sat 8am ────────────────────────────────
SAT=$(python3 -c "
from datetime import datetime, timedelta, timezone
now = datetime.now(timezone.utc)
days_ahead = (5 - now.weekday()) % 7  # Saturday=5
if days_ahead == 0: days_ahead = 7
d = now + timedelta(days=days_ahead)
print(d.strftime('%Y-%m-%d'))
")

gws calendar events insert \
  --params '{"calendarId": "primary"}' \
  --json "{
    \"summary\": \"Hike — Lands End\",
    \"location\": \"Lands End Trailhead\",
    \"description\": \"Group hike with Priya and James.\",
    \"start\": {\"dateTime\": \"${SAT}T08:00:00\", \"timeZone\": \"America/Los_Angeles\"},
    \"end\": {\"dateTime\": \"${SAT}T10:00:00\", \"timeZone\": \"America/Los_Angeles\"},
    \"attendees\": [{\"email\": \"priya@nexus.test\"}, {\"email\": \"james@nexus.test\"}]
  }" > /dev/null

echo "Created: Hike Sat 8am"

# ─── CREATE 5: Product Demo — Wed 11am, 30min, Zoom ────────────────────
WED=$(python3 -c "
from datetime import datetime, timedelta, timezone
now = datetime.now(timezone.utc)
days_ahead = (2 - now.weekday()) % 7  # Wednesday=2
if days_ahead == 0: days_ahead = 7
d = now + timedelta(days=days_ahead)
print(d.strftime('%Y-%m-%d'))
")

gws calendar events insert \
  --params '{"calendarId": "primary"}' \
  --json "{
    \"summary\": \"Product Demo\",
    \"location\": \"Zoom — https://zoom.us/j/98765432100\",
    \"description\": \"Demo with Lisa.\",
    \"start\": {\"dateTime\": \"${WED}T11:00:00\", \"timeZone\": \"America/Los_Angeles\"},
    \"end\": {\"dateTime\": \"${WED}T11:30:00\", \"timeZone\": \"America/Los_Angeles\"},
    \"attendees\": [{\"email\": \"lisa@nexus.test\"}]
  }" > /dev/null

echo "Created: Demo Wed 11am"

# ─── UPDATE 6: 1:1 with Sarah — move to 4pm ────────────────────────────
EVENT_ID=$(find_event_id "1:1 with Sarah")
if [ -n "$EVENT_ID" ]; then
    EXISTING=$(get_event "$EVENT_ID")
    START_DATE=$(echo "$EXISTING" | python3 -c "
import sys, json
e = json.load(sys.stdin)
dt = e['start'].get('dateTime', e['start'].get('date', ''))
print(dt.split('T')[0])
")
    gws calendar events patch \
      --params "{\"calendarId\": \"primary\", \"eventId\": \"$EVENT_ID\"}" \
      --json "{
        \"start\": {\"dateTime\": \"${START_DATE}T16:00:00\", \"timeZone\": \"America/Los_Angeles\"},
        \"end\": {\"dateTime\": \"${START_DATE}T16:30:00\", \"timeZone\": \"America/Los_Angeles\"},
        \"location\": \"Room 4A\"
      }" > /dev/null
    echo "Updated: 1:1 with Sarah → 4pm, Room 4A"
else
    echo "WARN: Could not find '1:1 with Sarah' event"
fi

# ─── UPDATE 7: Design Review with Priya — move to 3pm ──────────────────
EVENT_ID=$(find_event_id "Design Review")
if [ -n "$EVENT_ID" ]; then
    EXISTING=$(get_event "$EVENT_ID")
    START_DATE=$(echo "$EXISTING" | python3 -c "
import sys, json
e = json.load(sys.stdin)
dt = e['start'].get('dateTime', e['start'].get('date', ''))
print(dt.split('T')[0])
")
    gws calendar events patch \
      --params "{\"calendarId\": \"primary\", \"eventId\": \"$EVENT_ID\"}" \
      --json "{
        \"start\": {\"dateTime\": \"${START_DATE}T15:00:00\", \"timeZone\": \"America/Los_Angeles\"},
        \"end\": {\"dateTime\": \"${START_DATE}T16:00:00\", \"timeZone\": \"America/Los_Angeles\"}
      }" > /dev/null
    echo "Updated: Design Review → 3pm"
else
    echo "WARN: Could not find 'Design Review' event"
fi

# ─── UPDATE 8: Board Prep Session — Room B → Room A ────────────────────
EVENT_ID=$(find_event_id "Board Prep")
if [ -n "$EVENT_ID" ]; then
    gws calendar events patch \
      --params "{\"calendarId\": \"primary\", \"eventId\": \"$EVENT_ID\"}" \
      --json '{"location": "Conference Room C"}' > /dev/null
    echo "Updated: Board Prep → Room C"
else
    echo "WARN: Could not find 'Board Prep' event"
fi

# ─── DELETE 9: Friday Drinks ────────────────────────────────────────────
EVENT_ID=$(find_event_id "Friday Drinks")
if [ -n "$EVENT_ID" ]; then
    gws calendar events delete \
      --params "{\"calendarId\": \"primary\", \"eventId\": \"$EVENT_ID\"}" > /dev/null
    echo "Deleted: Friday Drinks"
else
    echo "WARN: Could not find 'Friday Drinks' event"
fi

# ─── DELETE 10: Client Call — Acme Corp ─────────────────────────────────
EVENT_ID=$(find_event_id "Client Call")
if [ -n "$EVENT_ID" ]; then
    gws calendar events delete \
      --params "{\"calendarId\": \"primary\", \"eventId\": \"$EVENT_ID\"}" > /dev/null
    echo "Deleted: Client Call — Acme Corp"
else
    echo "WARN: Could not find 'Client Call' event"
fi

echo ""
echo "Oracle complete: 5 created, 3 updated, 2 deleted."
