import React, { useState } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import Header from "../components/Header";
import Footer from "../components/Footer";
import { useAuth } from "../context/AuthContext";
import {
  gtfsSearch,
  loadGtfsRoute,
  issueTicket,
  arriveAtStop,
  getTickets,
  getTracking,
} from "../services/api";

const LEVEL_COLORS = {
  LOW: "bg-green-600",
  MEDIUM: "bg-yellow-500",
  HIGH: "bg-orange-500",
  SEVERE: "bg-red-600",
};

export default function ConductorDashboard() {
  const { token } = useAuth();

  const [routeText, setRouteText] = useState("");
  const [routes, setRoutes] = useState([]);
  const [selectedRoute, setSelectedRoute] = useState(null);

  const [stops, setStops] = useState([]);
  const [vehicle, setVehicle] = useState("");

  // Ticket form
  const [sourceStop, setSourceStop] = useState("");
  const [destStop, setDestStop] = useState("");
  const [count, setCount] = useState(1);
  const [clientRef, setClientRef] = useState(null);
  const [lastTicket, setLastTicket] = useState(null);

  // Trip control
  const [arriveStop, setArriveStop] = useState("");

  // Dashboard data
  const [tickets, setTickets] = useState([]);
  const [summary, setSummary] = useState(null);
  const [hourly, setHourly] = useState([]);
  const [passengersData, setPassengersData] = useState([]);
  const [liveStatus, setLiveStatus] = useState(null);

  const [notification, setNotification] = useState(null);
  const [loading, setLoading] = useState(false);

  const showNotification = (message, type = "info") => {
    setNotification({ message, type });
    setTimeout(() => setNotification(null), 3500);
  };

  /* ---------------- Route search / stops ---------------- */

  const fetchRoutes = async () => {
    if (!routeText) {
      showNotification("Enter route number (example: 210)", "warning");
      return;
    }
    setLoading(true);
    try {
      const data = await gtfsSearch(routeText);
      if (data.routes?.length) {
        setRoutes(data.routes);
        showNotification(`Found ${data.routes.length} route variants`, "success");
      } else {
        setRoutes([]);
        showNotification("No matching routes found", "error");
      }
    } catch (err) {
      showNotification(err.message || "Error fetching routes", "error");
    } finally {
      setLoading(false);
    }
  };

  const refreshDashboard = async (routeparentid) => {
    const [ticketData, tracking] = await Promise.all([
      getTickets(token, routeparentid),
      getTracking(routeparentid),
    ]);
    setTickets(ticketData.tickets || []);
    setSummary(ticketData.summary || null);
    setHourly(ticketData.hourly || []);
    setPassengersData(
      (tracking.stops || []).map((s) => ({
        name: s.name,
        boarded: s.boarded,
        departed: s.departed,
      }))
    );
    setLiveStatus({
      oci: tracking.overcrowdingIndex,
      level: tracking.overcrowdingLevel,
      current: tracking.currentPassengers,
      capacity: tracking.capacity,
    });
    if (tracking.vehicle) setVehicle(tracking.vehicle);
  };

  const fetchStops = async () => {
    if (!selectedRoute) {
      showNotification("Select a route first", "warning");
      return;
    }
    setLoading(true);
    try {
      const data = await loadGtfsRoute(token, {
        routeId: selectedRoute.route_id,
        direction: selectedRoute.direction_id,
        routeno: selectedRoute.routeno,
      });
      setStops(data.stops);
      setSelectedRoute({ ...selectedRoute, routeparentid: data.routeparentid });
      if (data.vehicle) setVehicle(data.vehicle);
      setSourceStop("");
      setDestStop("");
      setLastTicket(null);
      await refreshDashboard(data.routeparentid);
      showNotification(
        `${data.stops.length} stops loaded${data.vehicle ? ` · bus ${data.vehicle}` : ""}`,
        "success"
      );
    } catch (err) {
      showNotification(err.message || "Error fetching stops", "error");
    } finally {
      setLoading(false);
    }
  };

  /* ---------------- Ticketing ---------------- */

  const sourceIdx = stops.indexOf(sourceStop);
  const destOptions = sourceIdx >= 0 ? stops.slice(sourceIdx + 1) : [];
  const stages =
    sourceStop && destStop ? stops.indexOf(destStop) - sourceIdx : 0;
  const estFare = stages > 0 ? Math.min(5 + 5 * stages, 60) * count : 0;

  const handleIssueTicket = async () => {
    if (!sourceStop || !destStop) {
      showNotification("Select source and destination stops", "warning");
      return;
    }
    const ref = clientRef || crypto.randomUUID();
    setClientRef(ref);
    setLoading(true);
    try {
      const ticket = await issueTicket(token, {
        routeparentid: selectedRoute.routeparentid,
        source_stop: sourceStop,
        dest_stop: destStop,
        count,
        client_ref: ref,
      });
      setLastTicket(ticket);
      setClientRef(null); // next ticket = new idempotency key
      showNotification(
        ticket.duplicate
          ? `Duplicate prevented — ticket ${ticket.ticket_no} already issued`
          : `Ticket ${ticket.ticket_no} issued — ${count} pax boarded at ${sourceStop}`,
        "success"
      );
      await refreshDashboard(selectedRoute.routeparentid);
    } catch (err) {
      showNotification(err.message || "Failed to issue ticket", "error");
    } finally {
      setLoading(false);
    }
  };

  const handleArriveStop = async () => {
    if (!arriveStop) {
      showNotification("Select the stop the bus has reached", "warning");
      return;
    }
    setLoading(true);
    try {
      const res = await arriveAtStop(token, {
        routeparentid: selectedRoute.routeparentid,
        stop_name: arriveStop,
      });
      showNotification(
        res.alighted > 0
          ? `${res.alighted} passenger(s) alighted at ${arriveStop} (${res.ticketsCompleted.length} ticket(s) completed)`
          : `Arrived at ${arriveStop} — no tickets destined here`,
        res.alighted > 0 ? "success" : "info"
      );
      await refreshDashboard(selectedRoute.routeparentid);
    } catch (err) {
      showNotification(err.message || "Failed to update arrival", "error");
    } finally {
      setLoading(false);
    }
  };

  /* ---------------- UI ---------------- */

  return (
    <div className="min-h-screen flex flex-col bg-gray-100">
      <Header />

      {notification && (
        <div
          className={`fixed top-5 right-5 px-5 py-3 rounded-lg shadow-lg text-white z-50 max-w-md
            ${notification.type === "success"
              ? "bg-green-600"
              : notification.type === "error"
                ? "bg-red-500"
                : notification.type === "warning"
                  ? "bg-yellow-400 text-black"
                  : "bg-indigo-600"
            }`}
        >
          {notification.message}
        </div>
      )}

      <main className="flex-1 p-6 max-w-6xl mx-auto w-full">
        <h2 className="text-2xl font-bold mb-6">Conductor Dashboard</h2>

        {/* Route Search */}
        <div className="bg-white rounded-xl shadow p-6 mb-6">
          <h3 className="font-semibold mb-4">Search Route</h3>
          <div className="flex gap-4">
            <input
              value={routeText}
              onChange={(e) => setRouteText(e.target.value)}
              className="border rounded px-4 py-2 flex-1"
              placeholder="Enter route number (ex: 210)"
            />
            <button
              onClick={fetchRoutes}
              disabled={loading}
              className="bg-indigo-600 text-white px-6 py-2 rounded disabled:opacity-50"
            >
              Search
            </button>
          </div>
        </div>

        {/* Route Select */}
        {routes.length > 0 && (
          <div className="bg-white rounded-xl shadow p-6 mb-6">
            <h3 className="font-semibold mb-4">Select Route Variant</h3>
            <select
              className="border rounded px-4 py-2 w-full"
              value={selectedRoute ? `${selectedRoute.route_id}:${selectedRoute.direction_id}` : ""}
              onChange={(e) =>
                setSelectedRoute(
                  routes.find(
                    (r) => `${r.route_id}:${r.direction_id}` === e.target.value
                  ) || null
                )
              }
            >
              <option value="">-- Select Route --</option>
              {routes.map((r) => (
                <option
                  key={`${r.route_id}:${r.direction_id}`}
                  value={`${r.route_id}:${r.direction_id}`}
                >
                  {r.routeno || "Variant"} – {r.fromstation} → {r.tostation}
                </option>
              ))}
            </select>

            <button
              onClick={fetchStops}
              disabled={loading || !selectedRoute}
              className="mt-4 bg-blue-500 text-white px-6 py-2 rounded disabled:opacity-50"
            >
              Load Stops
            </button>
          </div>
        )}

        {stops.length > 0 && (
          <>
            {/* Issue Ticket + Trip Control */}
            <div className="grid md:grid-cols-2 gap-6 mb-6">
              {/* Issue Ticket */}
              <div className="bg-white rounded-xl shadow p-6">
                <h3 className="font-semibold mb-4">🎫 Issue Ticket</h3>
                {vehicle && (
                  <p className="text-xs text-gray-500 mb-3">
                    Bus: <span className="font-mono font-semibold">{vehicle}</span>
                    {selectedRoute?.routeno && (
                      <> · Route {selectedRoute.routeno}</>
                    )}
                  </p>
                )}
                <div className="space-y-3">
                  <select
                    className="border rounded px-4 py-2 w-full"
                    value={sourceStop}
                    onChange={(e) => {
                      setSourceStop(e.target.value);
                      setDestStop("");
                    }}
                  >
                    <option value="">-- Source stop --</option>
                    {stops.slice(0, -1).map((s, i) => (
                      <option key={i} value={s}>
                        {i + 1}. {s}
                      </option>
                    ))}
                  </select>

                  <select
                    className="border rounded px-4 py-2 w-full"
                    value={destStop}
                    onChange={(e) => setDestStop(e.target.value)}
                    disabled={!sourceStop}
                  >
                    <option value="">-- Destination stop --</option>
                    {destOptions.map((s) => (
                      <option key={s} value={s}>
                        {stops.indexOf(s) + 1}. {s}
                      </option>
                    ))}
                  </select>

                  <div className="flex gap-3 items-center">
                    <select
                      className="border rounded px-4 py-2 w-36"
                      value={count}
                      onChange={(e) => setCount(Number(e.target.value))}
                    >
                      {[1, 2, 3, 4, 5, 10, 15, 20].map((n) => (
                        <option key={n} value={n}>
                          {n} pax
                        </option>
                      ))}
                    </select>
                    {estFare > 0 && (
                      <span className="text-sm text-gray-600">
                        {stages} stage{stages > 1 ? "s" : ""} · est. fare{" "}
                        <span className="font-semibold">₹{estFare}</span>
                      </span>
                    )}
                  </div>

                  <button
                    onClick={handleIssueTicket}
                    disabled={loading || !sourceStop || !destStop}
                    className="w-full bg-green-600 text-white px-6 py-2.5 rounded font-semibold disabled:opacity-50"
                  >
                    Generate Ticket
                  </button>
                </div>
              </div>

              {/* Trip Control */}
              <div className="bg-white rounded-xl shadow p-6">
                <h3 className="font-semibold mb-4">🛑 Trip Control</h3>
                <p className="text-xs text-gray-500 mb-3">
                  When the bus reaches a stop, mark arrival — tickets destined
                  there complete automatically and passengers alight.
                </p>
                <div className="space-y-3">
                  <select
                    className="border rounded px-4 py-2 w-full"
                    value={arriveStop}
                    onChange={(e) => setArriveStop(e.target.value)}
                  >
                    <option value="">-- Bus arrived at --</option>
                    {stops.map((s, i) => (
                      <option key={i} value={s}>
                        {i + 1}. {s}
                      </option>
                    ))}
                  </select>
                  <button
                    onClick={handleArriveStop}
                    disabled={loading || !arriveStop}
                    className="w-full bg-orange-500 text-white px-6 py-2.5 rounded font-semibold disabled:opacity-50"
                  >
                    Arrive at Stop (auto-alight)
                  </button>

                  {liveStatus && (
                    <div className="pt-2 flex items-center justify-between">
                      <span className="text-sm text-gray-600">
                        On bus:{" "}
                        <b>
                          {liveStatus.current}/{liveStatus.capacity}
                        </b>
                      </span>
                      <span
                        className={`px-3 py-1 rounded text-white text-sm font-semibold ${LEVEL_COLORS[liveStatus.level]}`}
                      >
                        {liveStatus.oci}% {liveStatus.level}
                      </span>
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Last issued ticket — styled like a real bus ticket */}
            {lastTicket && (
              <div className="mb-6">
                <div className="max-w-xl mx-auto bg-yellow-50 border-2 border-dashed border-yellow-400 rounded-xl p-5 shadow">
                  <div className="flex justify-between items-center border-b border-dashed border-yellow-400 pb-2 mb-3">
                    <span className="font-bold text-yellow-800">BMTC TICKET</span>
                    <span className="font-mono text-sm text-yellow-900">
                      {lastTicket.ticket_no}
                    </span>
                  </div>
                  <div className="grid grid-cols-2 gap-y-1 text-sm text-yellow-900">
                    <span>Bus:</span>
                    <span className="font-mono font-semibold text-right">
                      {lastTicket.vehicle_no}
                    </span>
                    <span>Route:</span>
                    <span className="text-right font-semibold">
                      {lastTicket.routeno}
                    </span>
                    <span>From:</span>
                    <span className="text-right">{lastTicket.source_stop}</span>
                    <span>To:</span>
                    <span className="text-right">{lastTicket.dest_stop}</span>
                    <span>Passengers:</span>
                    <span className="text-right font-semibold">
                      {lastTicket.count}
                    </span>
                    <span>Fare:</span>
                    <span className="text-right font-bold">
                      ₹{lastTicket.total_fare}
                    </span>
                    <span>Issued:</span>
                    <span className="text-right font-mono text-xs">
                      {lastTicket.issued_at}
                    </span>
                    <span>Status:</span>
                    <span className="text-right">
                      <span
                        className={`px-2 py-0.5 rounded text-white text-xs ${
                          lastTicket.status === "ON_BUS"
                            ? "bg-green-600"
                            : "bg-gray-500"
                        }`}
                      >
                        {lastTicket.status}
                      </span>
                    </span>
                  </div>
                </div>
              </div>
            )}

            {/* Ticket Dashboard */}
            {summary && (
              <div className="bg-white rounded-xl shadow p-6 mb-6">
                <h3 className="font-semibold mb-4">📊 Ticket Dashboard (today)</h3>

                <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-6">
                  <div className="bg-indigo-50 rounded-lg p-3 text-center">
                    <p className="text-xs text-gray-500">Tickets</p>
                    <p className="text-xl font-bold">{summary.issuedToday}</p>
                  </div>
                  <div className="bg-indigo-50 rounded-lg p-3 text-center">
                    <p className="text-xs text-gray-500">Passengers</p>
                    <p className="text-xl font-bold">{summary.passengersToday}</p>
                  </div>
                  <div className="bg-green-50 rounded-lg p-3 text-center">
                    <p className="text-xs text-gray-500">On bus now</p>
                    <p className="text-xl font-bold">{summary.onBus}</p>
                  </div>
                  <div className="bg-gray-50 rounded-lg p-3 text-center">
                    <p className="text-xs text-gray-500">Completed</p>
                    <p className="text-xl font-bold">{summary.completed}</p>
                  </div>
                  <div className="bg-yellow-50 rounded-lg p-3 text-center">
                    <p className="text-xs text-gray-500">Revenue</p>
                    <p className="text-xl font-bold">₹{summary.revenueToday}</p>
                  </div>
                </div>

                {hourly.length > 0 && (
                  <div className="w-full h-48 mb-6">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={hourly}>
                        <XAxis dataKey="time" />
                        <YAxis allowDecimals={false} />
                        <Tooltip />
                        <Bar dataKey="passengers" fill="#6366f1" name="Passengers ticketed" />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                )}

                {tickets.length > 0 && (
                  <div className="overflow-x-auto max-h-72 overflow-y-auto">
                    <table className="w-full text-sm border-collapse">
                      <thead className="bg-gray-100 sticky top-0">
                        <tr>
                          <th className="p-2 text-left">Ticket No</th>
                          <th className="p-2 text-left">Time</th>
                          <th className="p-2 text-left">From → To</th>
                          <th className="p-2 text-center">Pax</th>
                          <th className="p-2 text-center">Fare</th>
                          <th className="p-2 text-center">Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {tickets.map((t) => (
                          <tr key={t._id} className="border-t">
                            <td className="p-2 font-mono text-xs">{t.ticket_no}</td>
                            <td className="p-2 text-xs">
                              {t.issued_at?.split(" ")[1]}
                            </td>
                            <td className="p-2">
                              {t.source_stop} → {t.dest_stop}
                            </td>
                            <td className="p-2 text-center">{t.count}</td>
                            <td className="p-2 text-center">₹{t.total_fare}</td>
                            <td className="p-2 text-center">
                              <span
                                className={`px-2 py-0.5 rounded text-white text-xs ${
                                  t.status === "ON_BUS"
                                    ? "bg-green-600"
                                    : "bg-gray-400"
                                }`}
                              >
                                {t.status}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}

            {/* Stop-wise tracking */}
            {passengersData.length > 0 && (
              <div className="bg-white rounded-xl shadow p-6">
                <h3 className="font-semibold mb-4">Stop-wise Tracking</h3>
                <div className="overflow-x-auto max-h-80 overflow-y-auto">
                  <table className="w-full border-collapse">
                    <thead className="bg-gray-200 sticky top-0">
                      <tr>
                        <th className="p-2">#</th>
                        <th className="p-2 text-left">Stop</th>
                        <th className="p-2">Boarded</th>
                        <th className="p-2">Departed</th>
                      </tr>
                    </thead>
                    <tbody>
                      {passengersData.map((s, i) => (
                        <tr key={i} className="border-t">
                          <td className="p-2 text-center">{i + 1}</td>
                          <td className="p-2">{s.name}</td>
                          <td className="p-2 text-center">{s.boarded}</td>
                          <td className="p-2 text-center">{s.departed}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </>
        )}
      </main>

      <Footer />
    </div>
  );
}
