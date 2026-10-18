"""End-to-end smoke test: auth (3 roles), ticketing flow, conductor flow,
passenger flow (ARIMA + recommendation), admin flow."""
import re
import time
import uuid

import requests

BASE = "http://localhost:5000/api"
LOG = "/tmp/bus_server.log"
PASS = "Test@1234"
RPID = "3796"          # real route 210-N (up) from the BMTC samples
SRC = "Kempegowda Bus Station"
DST = "Town Hall"      # 5 stages after source on 210-N

results = []


def check(name, ok, detail=""):
    results.append((name, ok, detail))
    print(f"{'✅' if ok else '❌'} {name}{' — ' + str(detail)[:110] if detail else ''}")


def latest_otp(phone):
    time.sleep(0.5)
    with open(LOG) as f:
        content = f.read()
    matches = re.findall(rf"OTP sent to {phone}[^:]*: (\d{{6}})", content)
    return matches[-1] if matches else None


def register_and_login(role, phone, email=None, name="Test User"):
    requests.post(f"{BASE}/auth/request-otp", json={"role": role, "phone": phone, "email": email})
    otp = latest_otp(phone)
    assert otp, f"no OTP found in log for {phone}"
    r = requests.post(f"{BASE}/auth/signup", json={
        "role": role, "name": name, "phone": phone, "email": email,
        "badge_id": "B1", "depot": "D1", "password": PASS, "otp": otp,
    })
    assert r.status_code in (201, 409), f"signup {role}: {r.status_code} {r.text}"
    payload = {"role": role, "password": PASS}
    payload["phone" if role == "passenger" else "email"] = phone if role == "passenger" else email
    r = requests.post(f"{BASE}/auth/login", json=payload)
    assert r.status_code == 200, f"login {role}: {r.status_code} {r.text}"
    return r.json()["token"]


# ---------- AUTH ----------
pax_token = register_and_login("passenger", "9876500001", name="Test Passenger")
check("passenger signup+login", bool(pax_token))
con_token = register_and_login("conductor", "9876500002", "conductor@test.com", "Test Conductor")
check("conductor signup+login", bool(con_token))
adm_token = register_and_login("admin", "9876500003", "admin@test.com", "Test Admin")
check("admin signup+login", bool(adm_token))

HC = {"Authorization": f"Bearer {con_token}"}
HA = {"Authorization": f"Bearer {adm_token}"}

# ---------- ROUTE SEARCH (real sample data / live API) ----------
r = requests.get(f"{BASE}/search-routes", params={"routetext": "210"})
routes = r.json().get("routes", [])
check("route search '210'", r.status_code == 200 and len(routes) > 0,
      f"{len(routes)} variants (fallback={r.json().get('fallback')})")

r = requests.get(f"{BASE}/get-route-stops", params={"routeparentid": RPID, "routeno": "210-N"}, headers=HC)
j = r.json()
check("load stops for 210-N (real data)", r.status_code == 200 and SRC in j.get("stops", []) and j.get("vehicle") == "KA01F9540",
      f"{len(j.get('stops', []))} stops, vehicle={j.get('vehicle')}, trips={j.get('trips')}")

# ---------- TICKETING ----------
# Reset route state so counts are deterministic (previous runs / UI usage
# may have left tickets and counters on this route)
from db import passenger_tracking_collection, tickets_collection, counters_collection

tickets_collection.delete_many({"routeparentid": RPID})
counters_collection.delete_many({"_id": {"$regex": f"^ticket:{RPID}:"}})
passenger_tracking_collection.update_one(
    {"routeparentid": RPID},
    {"$set": {
        "currentPassengers": 0, "overcrowdingIndex": 0, "overcrowdingLevel": "LOW",
        "stops.$[].boarded": 0, "stops.$[].departed": 0,
    }},
)

r = requests.post(f"{BASE}/conductor/issue-ticket", json={
    "routeparentid": RPID, "source_stop": SRC, "dest_stop": DST, "count": 10})
check("issue-ticket requires auth", r.status_code == 401, r.status_code)

ref = str(uuid.uuid4())
r = requests.post(f"{BASE}/conductor/issue-ticket", json={
    "routeparentid": RPID, "source_stop": SRC, "dest_stop": DST, "count": 10, "client_ref": ref}, headers=HC)
j = r.json()
ticket_no = j.get("ticket_no", "")
check("issue ticket (10 pax, KBS→Town Hall)",
      r.status_code == 201 and ticket_no.startswith("KA01F9540-") and j.get("currentPassengers") == 10
      and j.get("total_fare") == 300 and j.get("status") == "ON_BUS",
      f"{ticket_no} fare=₹{j.get('total_fare')} pax={j.get('currentPassengers')} oci={j.get('overcrowdingIndex')}")

r = requests.post(f"{BASE}/conductor/issue-ticket", json={
    "routeparentid": RPID, "source_stop": SRC, "dest_stop": DST, "count": 10, "client_ref": ref}, headers=HC)
j = r.json()
check("idempotent retry returns same ticket", r.status_code == 200 and j.get("duplicate") is True
      and j.get("ticket_no") == ticket_no, j.get("ticket_no"))

r = requests.get(f"{BASE}/get-tracking", params={"routeparentid": RPID})
check("count not doubled by retry", r.json().get("currentPassengers") == 10, r.json().get("currentPassengers"))

r = requests.post(f"{BASE}/conductor/issue-ticket", json={
    "routeparentid": RPID, "source_stop": DST, "dest_stop": SRC, "count": 1}, headers=HC)
check("dest-before-source rejected", r.status_code == 400, r.json().get("error", "")[:60])

# second ticket: 5 pax KR Circle → Majestic-area stop (St Marthas Hospital)
r = requests.post(f"{BASE}/conductor/issue-ticket", json={
    "routeparentid": RPID, "source_stop": "KR Circle", "dest_stop": "Town Hall", "count": 5}, headers=HC)
j2 = r.json()
check("second ticket (5 pax)", r.status_code == 201 and j2.get("currentPassengers") == 15,
      f"{j2.get('ticket_no')} fare=₹{j2.get('total_fare')}")

r = requests.post(f"{BASE}/conductor/arrive-stop", json={"routeparentid": RPID, "stop_name": DST}, headers=HC)
j = r.json()
check("arrive at Town Hall auto-alights", r.status_code == 200 and j.get("alighted") == 15
      and j.get("currentPassengers") == 0 and len(j.get("ticketsCompleted")) == 2,
      f"alighted={j.get('alighted')} completed={j.get('ticketsCompleted')}")

r = requests.post(f"{BASE}/conductor/arrive-stop", json={"routeparentid": RPID, "stop_name": DST}, headers=HC)
check("second arrival alights nobody", r.status_code == 200 and r.json().get("alighted") == 0)

r = requests.get(f"{BASE}/conductor/tickets", params={"routeparentid": RPID}, headers=HC)
j = r.json()
s = j.get("summary", {})
check("ticket dashboard data", r.status_code == 200 and s.get("issuedToday") == 2
      and s.get("passengersToday") == 15 and s.get("revenueToday") == 300 + j2.get("total_fare", 0)
      and s.get("onBus") == 0 and s.get("completed") == 2,
      f"summary={s}")

# ---------- PASSENGER (uses ticket-fed history) ----------
r = requests.post(f"{BASE}/passenger/crowding", json={"routeno": "210-N", "routeparentid": RPID})
j = r.json()
check("crowding dataset (ticket-fed)", r.status_code == 200 and len(j["dataset"]) == 13
      and j.get("current", {}).get("passengers") == 0,
      f"synthetic={j.get('synthetic')}")

r = requests.post(f"{BASE}/passenger/forecast", json={"routeparentid": RPID, "steps": 6})
j = r.json()
check("ARIMA forecast", r.status_code == 200 and len(j["forecast"]) == 6, j.get("forecast"))

r = requests.post(f"{BASE}/passenger/recommend", json={"routeparentids": [RPID], "horizon_hours": 8})
j = r.json()
opt = (j.get("options") or [{}])[0]
check("recommendation with scheduled trips",
      r.status_code == 200 and bool(j.get("suggestion")) and len(opt.get("scheduledTrips", [])) > 0,
      f"{j.get('suggestion')} | scheduled={[t['departAt'] for t in opt.get('scheduledTrips', [])]}")

# ---------- ADMIN ----------
r = requests.get(f"{BASE}/admin/dashboard", headers=HA)
j = r.json()
check("admin dashboard", r.status_code == 200 and j["totalBuses"] >= 6,
      f"buses={j.get('totalBuses')} pax={j.get('totalPassengers')}")

r = requests.get(f"{BASE}/admin/frequency-plan", headers=HA)
j = r.json()
plan210 = next((p for p in j.get("plan", []) if p["routeparentid"] == RPID), None)
check("admin frequency plan (210-N)", r.status_code == 200 and plan210 and plan210["hasHistory"],
      f"{plan210['currentDailyTrips']}→{plan210['recommendedDailyTrips']} trips/day" if plan210 else "missing")

r = requests.get(f"{BASE}/admin/reports", params={"period": "weekly"}, headers=HA)
check("admin weekly reports", r.status_code == 200 and len(r.json()["records"]) >= 35,
      f"{len(r.json().get('records', []))} daily records")

print("\n" + "=" * 50)
failed = [n for n, ok, _ in results if not ok]
print(f"{len(results) - len(failed)}/{len(results)} passed" + (f" — FAILED: {failed}" if failed else " — ALL GREEN"))

# ---------- GTFS LAYER ----------
r = requests.get(f"{BASE}/gtfs/search", params={"routetext": "210"})
j = r.json()
check("GTFS search '210'", r.status_code == 200 and len(j["routes"]) >= 5, f"{len(j['routes'])} variants")

variant = next((x for x in j["routes"] if x.get("trip_count", 0) >= 3), j["routes"][0])
RID, DIRN = variant["route_id"], variant["direction_id"]

r = requests.get(f"{BASE}/gtfs/routes-between", params={"source": "Kempegowda", "dest": "Jayanagar"})
check("GTFS source→dest search", r.status_code == 200 and r.json()["count"] > 0,
      f"{r.json()['count']} routes")

r = requests.get(f"{BASE}/gtfs/route-stops", params={"route_id": RID, "direction": DIRN})
j = r.json()
check("GTFS stops with times", r.status_code == 200 and len(j["stops"]) > 3 and j["stops"][0]["times"],
      f"{len(j['stops'])} stops, first times: {j['stops'][0]['times'][:3]}")

r = requests.get(f"{BASE}/gtfs/route-shape", params={"route_id": RID, "direction": DIRN})
check("GTFS shape polyline", r.status_code == 200 and len(r.json()["shape"]) > 10,
      f"{len(r.json()['shape'])} points")

r = requests.get(f"{BASE}/gtfs/live", params={"route_id": RID, "direction": DIRN})
j = r.json()
check("GTFS live endpoint", r.status_code == 200 and "buses" in j and "upcoming" in j,
      f"{len(j['buses'])} on road, {len(j['upcoming'])} upcoming")

r = requests.post(f"{BASE}/conductor/load-gtfs-route", json={"route_id": RID, "direction": DIRN, "routeno": variant["routeno"]}, headers=HC)
j = r.json()
check("conductor load GTFS route", r.status_code == 200 and j.get("routeparentid") == f"gtfs:{RID}:{DIRN}" and len(j.get("stops", [])) > 3,
      f"{len(j.get('stops', []))} stops, vehicle {j.get('vehicle')}")

RPID_G = j["routeparentid"]
r = requests.post(f"{BASE}/conductor/issue-ticket", json={
    "routeparentid": RPID_G, "source_stop": j["stops"][0], "dest_stop": j["stops"][4], "count": 6}, headers=HC)
t = r.json()
check("ticket on GTFS route", r.status_code == 201 and t.get("currentPassengers") == 6,
      f"{t.get('ticket_no')} fare ₹{t.get('total_fare')} ({t.get('fare_source')})")

r = requests.post(f"{BASE}/conductor/arrive-stop", json={"routeparentid": RPID_G, "stop_name": j["stops"][4]}, headers=HC)
check("arrive-stop on GTFS route", r.status_code == 200 and r.json().get("alighted") == 6)

for mdl in ("arima", "prophet"):
    r = requests.post(f"{BASE}/passenger/predict", json={
        "route_id": RID, "direction": DIRN, "target_time": "18:30", "model": mdl})
    j = r.json()
    check(f"predict ({mdl.upper()}) at 18:30",
          r.status_code == 200 and 0 <= j.get("predicted_oci", -1) <= 130 and j.get("forecast"),
          f"{j.get('predicted_oci')}% {j.get('level')}")

r = requests.get(f"{BASE}/admin/bus-insights", params={"route_id": RID, "direction": DIRN}, headers=HA)
j = r.json()
check("admin bus insights",
      r.status_code == 200 and j.get("insights") and j.get("frequency") and len(j.get("shape", [])) > 10,
      f"{len(j['insights'])} insights, {len(j['frequency'])} hourly freq rows")

r = requests.get(f"{BASE}/admin/bus-insights", params={"route_id": RID, "direction": DIRN})
check("admin insights require admin role", r.status_code == 401, r.status_code)

print("\n" + "=" * 50)
failed = [n for n, ok, _ in results if not ok]
print(f"GTFS section: {len(results) - len(failed)} passed / {len(results)} total checks" + (f" — FAILED: {failed}" if failed else ""))
