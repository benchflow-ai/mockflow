# TODO — mock-gcal

## Web UI

The web UI (`mock_gcal/web/`) mimics Google Calendar. Core layout is done;
the items below are known gaps and planned improvements.

### Week view

- [x] **Overlap handling** — overlapping events in the same day column are
  now partitioned into side-by-side columns.
- [x] **Multi-day timed events** — continuation blocks are rendered on each
  subsequent day an event spans.
- [x] **Event detail popover** — clicking an event block opens a popover
  showing title, time, location, attendees, and calendar name.
- [ ] **Click-to-create** — clicking an empty time slot should open a quick
  event creation form.

### Additional views

- [ ] **Month view** — traditional month grid, toggle via a view switcher
  button in the header (Week | Month | Schedule).
- [ ] **Schedule/list view** — chronological list of upcoming events grouped
  by date, useful for dense calendars.

### Sidebar

- [x] **Calendar filter** — calendar checkboxes toggle visibility of that
  calendar's events in the grid.
- [x] **Mini-cal day navigation** — clicking a day in the mini calendar
  jumps to that week (implemented via anchor links).
- [ ] **Mini-cal month navigation** — clicking the month name in the mini
  calendar should navigate to month view (requires Month view first).

### General

- [ ] **Responsive layout** — the week grid is not usable on narrow
  viewports; a schedule fallback would help.
- [x] **Timezone display** — the user's timezone abbreviation is shown in
  the time gutter.

---

## Tests

- [x] Add `tests/conftest.py` with shared seeded-db and client fixtures.
- [x] Add `tests/test_api.py` covering CRUD, error semantics, admin endpoints,
  and Calendar-specific edge cases.
- [x] Add `tests/test_conformance.py` with golden fixture shape validation.
- [x] Add `tests/test_seed.py` validating scenario richness and seed invariants.
- [x] Add `tests/fixtures/gcal_api_spec.json` and `mock_coverage.json` for API
  completeness tracking.
- [x] Add `tests/fixtures/real_gcal/` imported baseline fixtures plus capture metadata.
- [x] Add `scripts/capture_fixtures.py` and `scripts/validate_seed.py`.
- [x] Surface coverage / fixtures / tests in `/dev/dashboard`.

---

## Tasks

Add at least one task-shaped fixture before expanding Calendar task coverage.
Repo-level examples live under `example_tasks/<task-name>/` with:

```
task.md
data/needles.py
environment/
  Dockerfile
verifier/
  evaluate.py
```

- [ ] Add first Calendar example task (e.g. find and reschedule a specific meeting,
  or delete all cancelled events from a calendar).
- [ ] Oracle solution must score 1.0 before release.
