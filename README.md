# BMTC Bus Crowding Monitor & Forecaster

An AI Product Management (AIPM) course project: a real-time bus seat/crowding
monitoring system for Bengaluru's BMTC network, with real-world conductor
ticketing, live map tracking, and **ARIMA + Prophet** forecasting over the full
BMTC GTFS network (4,434 routes · 9,960 stops · 57,836 daily trips · real
timetables & fares).

**Core product promise:** tell every passenger *which bus to board and at what
time* to avoid crowding, and tell planners *where to add or trim frequency* —
using live ticketing as ground truth and time-series models for prediction.

---

## 1. Topic Identification (Phase-1 · A)

**Chosen topic:** an AI-assisted bus crowding prediction and service-planning
product for a metropolitan bus network (BMTC, Bengaluru).

**The real-world problem.** BMTC moves millions of riders daily on ≈6,000+
buses. Commuters board buses blindly — they learn only at the door whether the
bus is jam-packed. Conductors issue tickets but the resulting occupancy data
never feeds back into planning. Planners schedule frequencies from static
assumptions, so peak buses run at 120%+ occupancy while off-peak buses run
nearly empty.

**Why this topic is appropriate for AIPM concepts.**

- **Complete AI product loop** — sensor (conductor ticketing) → data (hourly
  crowding series) → AI model (ARIMA/Prophet forecasts) → decisions (passenger
  boarding choice, admin frequency planning) → feedback (new tickets update
  the models). Every stage of the AI-product lifecycle exists and closes.
- **Three distinct personas** (passenger, conductor, admin) — forces real
  product thinking: value proposition, interaction flow, and success metric
  per user, not just a model demo.
- **Measurable KPIs** — Overcrowding Index (OCI), suggestion acceptance,
  recommended-vs-scheduled frequency delta, passenger-minutes saved.
- **Real open data** — the full BMTC GTFS feed (routes, stops, timetables,
  shapes, fares) grounds the product in a real network, not toy data.

## 2. Information Gathering (Phase-1 · B)

**Domain background.** Bengaluru's BMTC is one of India's largest city bus
operators. Crowding peaks at morning (8–10 AM) and evening (5–7 PM) office
hours; occupancy varies heavily by route, direction, and hour. GTFS (General
Transit Feed Specification) is the open-data standard for schedules; BMTC's
feed is publicly published and includes shapes and fare rules.

**Existing solutions and gaps.**

| Existing solution | What it offers | Gap we address |
|---|---|---|
| Google Maps / Transit apps | Trip planning, official timetables | No crowding information at all |
| BMTC official app | Route & fare info | No live crowding, no forecast, no conductor tooling |
| Chalo & live-tracking apps | Vehicle positions (some cities) | No crowding prediction; no planner-side decisions |
| Paper/manual frequency planning | Static schedules | Not data-driven, not reactive to demand |

**User needs identified.**

- *Commuter:* "Which bus, at what time, so I don't travel crushed?" — needs
  crowding *now* and crowding *predicted for my departure time*.
- *Conductor:* fast issue of a real ticket (time, bus no., source→dest, fare)
  with occupancy auto-updating — no separate counting chore.
- *Planner/Admin:* per-bus crowding trends and a defensible recommendation
  for trips-per-hour, with insights they can act on.

## 3. Impact Analysis (Phase-1 · C)

**Value created & expected benefits.**

- Passengers choose better trips → less crushed travel, lower wait-to-board
  uncertainty, predictable journeys.
- Conductor ticketing is digitized (idempotent, atomic, real fare rules) and
  doubles as the **crowding sensor** — no extra hardware.
- Admin gets rule-based, data-backed frequency recommendations (add/trim
  trips per hour) → efficient bus utilization and fuel/crew savings.
- System-wide feedback loop improves forecast accuracy over time.

**Target users.** Daily commuters; conductors/crew; BMTC operations planners.

**Feasibility.** Built and verified end-to-end on commodity hardware with
fully open data (GTFS + MongoDB + SQLite). No proprietary APIs required; the
live-vehicle path degrades gracefully to timetable simulation when the
public API is unreachable (disclosed in the UI).

**Risks & mitigations.**

| Risk | Mitigation |
|---|---|
| Live BMTC API unreachable on some networks | GTFS static data + timetable-based simulation, clearly labeled |
| Sparse history for rarely-serviced routes | Lazy 7-day history seeding + hour-of-day profile fallback |
| Model drift as demand shifts | Models retrain per request on a rolling 7-day window |

**Ethical, legal, security considerations.**

- *Privacy:* tickets carry no personal identity — only counts, times, and
  stops. No PII is stored in the crowding pipeline.
- *Transparency:* simulated positions/occupancy are always labeled as such in
  the UI; real conductor data overrides simulation.
- *Security:* JWT + role-based access control (passenger/conductor/admin),
  OTP-verified signup, idempotent ticket issue (`client_ref`) to prevent
  double charging, atomic ticket numbering.
- *Legal/licensing:* uses the public BMTC GTFS feed and open-source stacks.

## 4. AI Tool Identification (Phase-1 · D)

| Tool / framework | Role in product | Why chosen |
|---|---|---|
| **ARIMA** (statsmodels) | Short-horizon crowding forecast | Interpretable, fast, well-suited to hourly count series; order chosen by AIC grid search with naive fallbacks |
| **Prophet** (Facebook) | Daily-seasonality forecast at a chosen time | Robust to missing data and strong daily cycles; handles gap-filled series gracefully; cached fits for responsiveness |
| **GTFS + SQLite** | Domain data backbone | GTFS is the transit-industry standard; SQLite gives indexed relational joins (e.g., source→dest trip matching) over 1.5M stop_times |
| **MongoDB** | Dynamic state & time series | Flexible documents for tickets, live tracking, hourly OCI buckets; unique indexes enforce idempotency |
| **Leaflet + react-leaflet** | Live map views | Lightweight open-source mapping with route shapes and bus markers |
| **Flask + React/Vite** | Product surface | REST API with JWT/OTP auth; responsive SPA with timetable/map/predict tabs |

**Model usage strategy.** Both models train per route-direction on a
**contiguous hourly OCI series** (7 days, gaps filled from the route's own
hour-of-day profile — critical for Prophet stability). ARIMA searches
candidate (p,d,q) orders by AIC; Prophet uses daily seasonality with clipped
outputs. If either model can't fit (short series), a deterministic
hour-of-day profile fallback is used so the product never shows a blank.

**Overcrowding Index (OCI)** = `passengers on board / capacity × 100`, with
levels LOW ≤ 50, MEDIUM ≤ 75, HIGH ≤ 100, SEVERE > 100.

## 5. Features

- **Passenger**
  - Search by **bus number** (e.g. "210" → 15 real variants) or
    **source + destination** with stop autocomplete (9,960 stops), returning
    all connecting routes.
  - **Timetable view** — every stop on the chosen variant with the actual
    times buses depart it today.
  - **Live Map view** — route shape, stops, and buses moving along the route
    in real time, colored by crowding level, with next stop/ETA popups.
  - **Predict Crowding** — pick a time + model (ARIMA or Prophet) → predicted
    OCI, crowding level, a "board this trip instead" suggestion, and a
    history + forecast chart.
- **Conductor**
  - Load any GTFS route (all real stops) and issue **real-world bus tickets**
    — ticket number `VEHICLE-YYYYMMDD-####`, timestamp, bus number,
    source→destination, GTFS fare-rule pricing (stage-estimate fallback).
  - Tickets **auto-board** at the source; "Arrive at stop" **auto-alights**
    everyone destined there; occupancy and OCI update atomically.
  - Ticket dashboard: revenue, on-board count, hourly demand chart, full log.
- **Admin**
  - Per-bus **insights**: live map, 7-day crowding-by-hour profile,
    **scheduled vs recommended trips/hour** with add/trim/keep decisions.
  - Rule-based insight cards (e.g. "Peak crowding 95% at 18:00 — add 2 trips").
  - Fleet-wide counters, stop-wise board/alight charts, PDF report export.

## 6. Functional Requirements (Phase-1 · E)

| ID | Requirement | Role |
|---|---|---|
| FR1 | Authenticate via OTP signup + login; role-based access (JWT) | All |
| FR2 | Search routes by bus number, returning all variants/directions | Passenger |
| FR3 | Search routes between a source and destination stop | Passenger |
| FR4 | Show per-stop timetable (departure times) for a variant | Passenger |
| FR5 | Show live map with moving buses colored by crowding | Passenger/Admin |
| FR6 | Predict crowding at a user-chosen time using ARIMA or Prophet | Passenger |
| FR7 | Recommend the best trip to board (minimizes crowding + wait) | Passenger |
| FR8 | Issue real tickets (auto-board, fare, idempotent) | Conductor |
| FR9 | Record stop arrivals; auto-alight passengers; update OCI | Conductor |
| FR10 | Show ticket dashboard (revenue, counts, hourly demand) | Conductor |
| FR11 | Per-bus crowding profile and insights | Admin |
| FR12 | Frequency recommendation (scheduled vs recommended trips/hour) | Admin |
| FR13 | Export crowding reports (PDF) | Admin |

**Non-functional:** predictions < ~2 s (model cache), idempotent + atomic
ticketing, role-protected APIs, graceful degradation when external APIs are
unreachable, deterministic reset for repeatable demos/tests.

**High-level user interaction flow.**

1. User signs up with OTP and logs in as passenger / conductor / admin.
2. *Passenger:* search (bus no. **or** source+dest) → pick variant →
   Timetable / Live Map / Predict → follow the boarding suggestion.
3. *Conductor:* load GTFS route → issue tickets (occupancy auto-updates) →
   mark stop arrivals (auto-alight) → monitor dashboard.
4. *Admin:* pick route → view insights + live map → act on the frequency
   decision table → export PDF.

## 7. System Architecture (Phase-1 · F: workflow overview)

```
┌──────────────────────┐      ┌───────────────────────────────────────┐
│  React SPA (Vite)    │ HTTP │  Flask REST API (JWT + OTP + RBAC)    │
│  · Timetable tab     │─────▶│  Blueprints: passenger · conductor ·  │
│  · Leaflet live map  │◀─────│  admin · ticketing · gtfs · auth      │
│  · Predict tab       │      └──────────┬─────────────────┬──────────┘
└──────────────────────┘                 │                 │
                            ┌────────────▼─────┐  ┌────────▼─────────────┐
                            │  MongoDB         │  │  SQLite (GTFS)       │
                            │  users · tickets │  │  routes · stops      │
                            │  tracking · OCI  │  │  trips · stop_times  │
                            │  hourly series   │  │  shapes · fares      │
                            └────────────┬─────┘  └────────▲─────────────┘
                                         │                 │ import_gtfs.py
                            ┌────────────▼──────────────────┐│ (BMTC GTFS feed)
                            │  APScheduler                  │└──────────────────
                            │  · sim feed every 5 min       │
                            │  · daily reset 00:05 IST      │
                            └────────────┬──────────────────┘
                                         │ feeds
                            ┌────────────▼──────────────────┐
                            │  Forecasting engine           │
                            │  ARIMA (AIC grid) + Prophet   │
                            │  on contiguous hourly OCI     │
                            └───────────────────────────────┘
```

**Data flow.**

1. `import_gtfs.py` loads the BMTC GTFS feed into SQLite (4,434 routes,
   9,960 stops, 57,836 trips, 1.54M stop_times, 2.49M shape points, 170k
   fare rules).
2. Static queries (search, timetable, source→dest matching, shapes, fares)
   hit SQLite; dynamic state (users, tickets, tracking, hourly OCI buckets)
   lives in MongoDB.
3. Conductor tickets — and, where no conductor is active, a 5-minute
   simulation feed — recompute occupancy and persist hourly OCI buckets.
4. Prediction requests load the route's contiguous hourly series and run
   ARIMA/Prophet → predicted OCI + level + trip suggestion.
5. Admin insights aggregate 7-day profiles into frequency recommendations.

**Stack.** Flask · MongoDB · SQLite (GTFS) · statsmodels ARIMA · Facebook
Prophet · React (Vite) + Tailwind + Leaflet + Chart.js/Recharts · APScheduler.

## 8. Data Requirements (Phase-1 · F)

- **GTFS static feed** ([Vonter/bmtc-gtfs](https://github.com/Vonter/bmtc-gtfs))
  → `server/data/gtfs/` → imported into `server/data/bmtc_gtfs.db`.
- **Sample API captures**
  ([traffic-kowshik/traffic-data-bengaluru](https://github.com/traffic-kowshik/traffic-data-bengaluru))
  → `server/data/bmtc_samples/` — offline catalog + real vehicle/timetable.
- **Generated series** — 7 days of hourly OCI history per route
  (`history_seed.py`), plus live buckets from ticketing/simulation.
- **Config** — `server/.env` with `MONGO_URI`, `DB_NAME`, `SECRET_KEY`
  (local dev only; never commit secrets).

## 9. Course of Action — Implementation Plan (Phase-1 · F)

**Gantt chart (Phase-2 development, 6 weeks).**

```
Week →                          1    2    3    4    5    6
─────────────────────────────────────────────────────────────
GTFS data import & DB design    ████
Auth, OTP & role management          ████
Conductor ticketing module                ████
Live tracking & map views                      ████
ARIMA / Prophet forecast engine                ████ ████
Admin insights & frequency plan                          ████
Testing (smoke suite) & hardening                  ████ ████
Docs, demo prep & presentation                                ████
```

**Step-by-step plan.**

1. **Data:** obtain GTFS feed; build importer; verify row counts & integrity.
2. **Foundation:** Flask app, MongoDB schemas, OTP/JWT auth, three roles.
3. **Ticketing:** real-ticket issue (idempotent, atomic) + stop arrivals;
   wire ticket counts into occupancy and hourly OCI series.
4. **Tracking:** position interpolation along GTFS shapes from stop_times;
   Leaflet map views; crowding-colored markers.
5. **Forecasting:** contiguous-series pipeline; ARIMA (AIC grid) + Prophet
   with caching and fallbacks; predict-at-time endpoint + suggestions.
6. **Admin product:** 7-day profiles, frequency recommendation engine,
   insight cards, PDF export.
7. **Verification & demo:** 32-check end-to-end smoke suite; demo script;
   docs (this README).

**Tools/platforms required.** macOS/Linux with Python 3.11+, Node 18+,
MongoDB Community, and an internet connection only for initial data
download and map tiles.

## 10. Running the Project

### Prerequisites

- Python 3.11+, Node.js 18+, and MongoDB Community running locally.

### 1) Start MongoDB

```bash
brew install mongodb-community   # once
brew services start mongodb-community
```

### 2) Backend (Flask, port 5000)

```bash
cd server
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python import_gtfs.py      # one-time: GTFS → SQLite (~15 s)
python seed_history.py     # one-time: 7 days of history for catalog routes

python -u app.py           # run server → http://localhost:5000
```

- `python -u` (unbuffered) matters: OTP codes print to the server console.
- Tail backend logs: `tail -f /tmp/bus_server.log`

### 3) Frontend (React + Vite, port 5173)

```bash
cd client
npm install
npm run dev                # → http://localhost:5173
```

### 4) Verify everything works

```bash
cd server && .venv/bin/python smoke_test.py   # 32 end-to-end checks
```

### Test accounts (password `Test@1234`)

| Role | Login |
|---|---|
| Passenger | phone `9876500001` |
| Conductor | `conductor@test.com` |
| Admin | `admin@test.com` |

New accounts can be signed up in the UI — the OTP appears in the server
console (`tail -f /tmp/bus_server.log`).

## 11. Demo Script (5 minutes)

1. **Passenger** — log in → search `500` → pick **500-A** →
   *Timetable* (real bus times per stop) → *Live Map* (buses moving) →
   *Predict* at 18:30 with Prophet vs ARIMA → see the boarding suggestion.
2. **Passenger, source→dest** — search `Kempegowda` → `Jayanagar` →
   pick a connecting route.
3. **Conductor** — search `500` → load 500-A → issue tickets (real ticket
   card appears) → "Arrive at stop" → watch occupancy auto-alight and the
   ticket dashboard update.
4. **Admin** — search `500` → 500-A → insight cards, live map, 7-day
   profile, frequency decision table → export a PDF.

## 12. Limitations & Honest Disclosures

- The BMTC live-vehicle API is unreachable on some networks (HTTP 403);
  when it is, bus positions and occupancy are **simulated from the GTFS
  timetable** and always labeled as simulated in the UI. Real conductor
  ticketing overrides simulation per route.
- Crowding history starts from seed + live accumulation; forecasts improve
  as the series grows.
- Fares follow GTFS fare rules where available, with a disclosed stage-based
  estimate otherwise.
