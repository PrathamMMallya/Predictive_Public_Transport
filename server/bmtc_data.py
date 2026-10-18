"""
BMTC route catalog built from real captured API data.

Source: https://github.com/traffic-kowshik/traffic-data-bengaluru
(data/bmtc/samples — captured responses of the official BMTC mobile API,
bundled locally in server/data/bmtc_samples/ so the app works even when the
live API is unreachable).

The live BMTC API is always tried FIRST (see ticket_collector.search_routes);
this catalog is the offline path and the source of real stop lists, vehicle
registrations and scheduled trip times for the ticketing system.

Catalog entries:
    routeno, routeparentid, fromstation, tostation, servicetype,
    vehicle      – real registration number (e.g. KA01F9540)
    stops        – ordered real stop names
    stop_meta    – {name: {stationid, distance_km}} from route details
    trips        – scheduled departure times ["18:50", ...] from the timetable
    data_source  – "bmtc-samples" (real captured data) or "supplementary"
"""

import json
import os

_DATA_DIR = os.path.join(os.path.dirname(__file__), "data", "bmtc_samples")


def _load(filename):
    with open(os.path.join(_DATA_DIR, filename)) as f:
        return json.load(f)


def _stops_from_route_details(direction_data):
    """Ordered stop names + metadata from 06_route_details.json up/down data."""
    stops, meta = [], {}
    for item in sorted(direction_data, key=lambda x: x.get("distance_on_station", 0)):
        name = item["stationname"].strip()
        stops.append(name)
        meta[name] = {
            "stationid": item.get("stationid"),
            "distance_km": round(float(item.get("distance_on_station", 0)), 2),
        }
    return stops, meta


def _scheduled_trips():
    """Scheduled start times from 05_time_table_routes.json."""
    tt = _load("05_time_table_routes.json")
    trips = []
    for entry in tt.get("data", []):
        for t in entry.get("tripdetails", []):
            if t.get("starttime"):
                trips.append(t["starttime"])
    return sorted(set(trips))


def _build_catalog():
    route_details = _load("06_route_details.json")
    vehicles = [v["vehicleregno"] for v in _load("03_vehicles.json").get("data", [])]

    up_stops, up_meta = _stops_from_route_details(route_details["up"]["data"])
    down_stops, down_meta = _stops_from_route_details(route_details["down"]["data"])

    up_info = route_details["up"]["data"][0]
    down_info = route_details["down"]["data"][0]

    # Vehicle assigned to this route in the captured live data, if present
    map_data = route_details["up"].get("mapData") or []
    route_vehicle = map_data[0].get("vehiclenumber") if map_data else None

    trips = _scheduled_trips()

    catalog = [
        # --- Real captured route: 210-N, both directions ---
        {
            "routeno": up_info["routeno"],
            "routeparentid": str(up_info["routeid"]),
            "fromstation": up_info["from"],
            "tostation": up_info["to"],
            "servicetype": "Ordinary",
            "vehicle": route_vehicle or (vehicles[0] if vehicles else "KA01F0000"),
            "stops": up_stops,
            "stop_meta": up_meta,
            "trips": trips,
            "data_source": "bmtc-samples",
        },
        {
            "routeno": down_info["routeno"],
            "routeparentid": f"{down_info['routeid']}-D",
            "fromstation": down_info["from"],
            "tostation": down_info["to"],
            "servicetype": "Ordinary",
            "vehicle": vehicles[1] if len(vehicles) > 1 else "KA57F0007",
            "stops": down_stops,
            "stop_meta": down_meta,
            "trips": trips,
            "data_source": "bmtc-samples",
        },
        # --- Supplementary routes (hand-added for search variety) ---
        {
            "routeno": "335E",
            "routeparentid": "fallback-335e-a",
            "fromstation": "Majestic",
            "tostation": "Whitefield",
            "servicetype": "Vajra AC",
            "vehicle": "KA53F0007",
            "stops": ["Majestic", "Shivajinagar", "Ulsoor", "Indiranagar",
                      "Marathahalli", "KR Puram", "Whitefield"],
            "stop_meta": {},
            "trips": [],
            "data_source": "supplementary",
        },
        {
            "routeno": "500D",
            "routeparentid": "fallback-500d-a",
            "fromstation": "Silk Board",
            "tostation": "Hebbal",
            "servicetype": "Ordinary",
            "vehicle": "KA57F0007",
            "stops": ["Silk Board", "Marathahalli", "Tin Factory",
                      "KR Puram", "Hennur", "Hebbal"],
            "stop_meta": {},
            "trips": [],
            "data_source": "supplementary",
        },
        {
            "routeno": "G-3",
            "routeparentid": "fallback-g3-a",
            "fromstation": "Jayanagar",
            "tostation": "Yeshwanthpur",
            "servicetype": "BIG-10",
            "vehicle": "KA53F0007",
            "stops": ["Jayanagar", "Basavanagudi", "Majestic",
                      "Malleshwaram", "Yeshwanthpur"],
            "stop_meta": {},
            "trips": [],
            "data_source": "supplementary",
        },
        {
            "routeno": "600F",
            "routeparentid": "fallback-600f-a",
            "fromstation": "Banashankari",
            "tostation": "Electronic City",
            "servicetype": "Ordinary",
            "vehicle": "KA57F0007",
            "stops": ["Banashankari", "JP Nagar", "BTM Layout",
                      "Silk Board", "Electronic City"],
            "stop_meta": {},
            "trips": [],
            "data_source": "supplementary",
        },
    ]
    return catalog


CATALOG = _build_catalog()


def search_catalog(routetext=None, source=None, dest=None, limit=10):
    """Filter the catalog by route number and/or station names."""
    rt = (routetext or "").strip().lower()
    src = (source or "").strip().lower()
    dst = (dest or "").strip().lower()

    results = []
    for route in CATALOG:
        if rt and rt not in route["routeno"].lower():
            continue
        if src and src not in route["fromstation"].lower() and not any(
            src in s.lower() for s in route["stops"]
        ):
            continue
        if dst and dst not in route["tostation"].lower() and not any(
            dst in s.lower() for s in route["stops"]
        ):
            continue
        results.append({
            "routeno": route["routeno"],
            "routeparentid": route["routeparentid"],
            "fromstation": route["fromstation"],
            "tostation": route["tostation"],
            "servicetype": route["servicetype"],
            "vehicle": route["vehicle"],
            "dataSource": route["data_source"],
        })
    return results[:limit]


def catalog_route(routeparentid):
    """Full catalog entry for a routeparentid, or None."""
    for route in CATALOG:
        if route["routeparentid"] == routeparentid:
            return route
    return None


def catalog_stops(routeparentid):
    """Ordered stop list for a catalog route, or None if unknown."""
    route = catalog_route(routeparentid)
    return list(route["stops"]) if route else None
