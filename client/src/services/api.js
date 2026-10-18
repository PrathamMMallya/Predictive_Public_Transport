const API_URL = "http://localhost:5000/api";

async function handle(res) {
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
  return data;
}

function authHeaders(token) {
  return token ? { Authorization: `Bearer ${token}` } : {};
}

// ---------- AUTH ----------
export async function requestOtp(payload) {
  const res = await fetch(`${API_URL}/auth/request-otp`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handle(res);
}

export async function signupUser(payload) {
  const res = await fetch(`${API_URL}/auth/signup`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handle(res);
}

export async function loginUser(payload) {
  const res = await fetch(`${API_URL}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handle(res);
}

// ---------- PASSENGER ----------
export async function searchPassengerRoutes({ routetext, source, dest }) {
  const params = new URLSearchParams();
  if (routetext) params.set("routetext", routetext);
  if (source) params.set("source", source);
  if (dest) params.set("dest", dest);
  const res = await fetch(`${API_URL}/passenger/search-routes?${params}`);
  return handle(res);
}

export async function getCrowding(routeno, routeparentid) {
  const res = await fetch(`${API_URL}/passenger/crowding`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ routeno, routeparentid }),
  });
  return handle(res);
}

export async function getForecast(routeparentid, steps = 13) {
  const res = await fetch(`${API_URL}/passenger/forecast`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ routeparentid, steps }),
  });
  return handle(res);
}

export async function getRecommendation(routeparentids, horizonHours = 6) {
  const res = await fetch(`${API_URL}/passenger/recommend`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ routeparentids, horizon_hours: horizonHours }),
  });
  return handle(res);
}

// ---------- GTFS (real routes, stops, timetables, live sim) ----------
export async function gtfsSearch(routetext) {
  const res = await fetch(`${API_URL}/gtfs/search?routetext=${encodeURIComponent(routetext)}`);
  return handle(res);
}

export async function gtfsStopsAutocomplete(q) {
  const res = await fetch(`${API_URL}/gtfs/stops-autocomplete?q=${encodeURIComponent(q)}`);
  return handle(res);
}

export async function gtfsRoutesBetween(source, dest) {
  const params = new URLSearchParams({ source, dest });
  const res = await fetch(`${API_URL}/gtfs/routes-between?${params}`);
  return handle(res);
}

export async function gtfsRouteStops(routeId, direction = 0) {
  const res = await fetch(`${API_URL}/gtfs/route-stops?route_id=${routeId}&direction=${direction}`);
  return handle(res);
}

export async function gtfsRouteShape(routeId, direction = 0) {
  const res = await fetch(`${API_URL}/gtfs/route-shape?route_id=${routeId}&direction=${direction}`);
  return handle(res);
}

export async function gtfsLive(routeId, direction = 0) {
  const res = await fetch(`${API_URL}/gtfs/live?route_id=${routeId}&direction=${direction}`);
  return handle(res);
}

export async function predictCrowding({ routeId, direction = 0, targetTime, model = "arima" }) {
  const res = await fetch(`${API_URL}/passenger/predict`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      route_id: routeId,
      direction,
      target_time: targetTime,
      model,
    }),
  });
  return handle(res);
}

export async function loadGtfsRoute(token, { routeId, direction = 0, routeno }) {
  const res = await fetch(`${API_URL}/conductor/load-gtfs-route`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify({ route_id: routeId, direction, routeno }),
  });
  return handle(res);
}

export async function getBusInsights(token, routeId, direction = 0) {
  const res = await fetch(`${API_URL}/admin/bus-insights?route_id=${routeId}&direction=${direction}`, {
    headers: { ...authHeaders(token) },
  });
  return handle(res);
}

// ---------- CONDUCTOR ----------
export async function searchConductorRoutes(routetext) {
  const res = await fetch(
    `${API_URL}/search-routes?routetext=${encodeURIComponent(routetext)}`
  );
  return handle(res);
}

export async function fetchRouteStops(token, routeparentid, routeno) {
  const params = new URLSearchParams({ routeparentid });
  if (routeno) params.set("routeno", routeno);
  const res = await fetch(`${API_URL}/get-route-stops?${params}`, {
    headers: { ...authHeaders(token) },
  });
  return handle(res);
}

export async function updatePassenger(token, { routeparentid, stop_name, action, count = 1 }) {
  const res = await fetch(`${API_URL}/update-passenger`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify({ routeparentid, stop_name, action, count }),
  });
  return handle(res);
}

// ---------- CONDUCTOR: TICKETING ----------
export async function issueTicket(token, { routeparentid, source_stop, dest_stop, count = 1, client_ref }) {
  const res = await fetch(`${API_URL}/conductor/issue-ticket`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify({ routeparentid, source_stop, dest_stop, count, client_ref }),
  });
  return handle(res);
}

export async function arriveAtStop(token, { routeparentid, stop_name }) {
  const res = await fetch(`${API_URL}/conductor/arrive-stop`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify({ routeparentid, stop_name }),
  });
  return handle(res);
}

export async function getTickets(token, routeparentid) {
  const params = new URLSearchParams({ routeparentid });
  const res = await fetch(`${API_URL}/conductor/tickets?${params}`, {
    headers: { ...authHeaders(token) },
  });
  return handle(res);
}

export async function getTracking(routeparentid) {
  const params = new URLSearchParams({ routeparentid });
  const res = await fetch(`${API_URL}/get-tracking?${params}`);
  return handle(res);
}

// ---------- ADMIN ----------
export async function getAdminDashboard(token) {
  const res = await fetch(`${API_URL}/admin/dashboard`, {
    headers: { ...authHeaders(token) },
  });
  return handle(res);
}

export async function getAdminReports(token, period = "weekly") {
  const res = await fetch(`${API_URL}/admin/reports?period=${period}`, {
    headers: { ...authHeaders(token) },
  });
  return handle(res);
}

export async function getFrequencyPlan(token, days = 7) {
  const res = await fetch(`${API_URL}/admin/frequency-plan?days=${days}`, {
    headers: { ...authHeaders(token) },
  });
  return handle(res);
}
