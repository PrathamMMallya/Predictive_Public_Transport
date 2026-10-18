import React, { useEffect, useRef, useState } from "react";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
} from "chart.js";
import { Line } from "react-chartjs-2";

import Header from "../components/Header";
import Footer from "../components/Footer";
import BusMap from "../components/BusMap";
import {
  gtfsSearch,
  gtfsStopsAutocomplete,
  gtfsRoutesBetween,
  gtfsRouteStops,
  gtfsRouteShape,
  gtfsLive,
  predictCrowding,
} from "../services/api";

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend);

const LEVEL_COLORS = {
  LOW: "bg-green-600",
  MEDIUM: "bg-yellow-500",
  HIGH: "bg-orange-500",
  SEVERE: "bg-red-600",
};

/* Stop-name input with autocomplete dropdown */
function StopAutocomplete({ placeholder, value, onChange, onPick }) {
  const [suggestions, setSuggestions] = useState([]);
  const [open, setOpen] = useState(false);

  const handleChange = async (text) => {
    onChange(text);
    if (text.trim().length >= 2) {
      try {
        const data = await gtfsStopsAutocomplete(text);
        const seen = new Set();
        setSuggestions(
          data.stops.filter((s) => !seen.has(s.stop_name) && seen.add(s.stop_name)).slice(0, 8)
        );
        setOpen(true);
      } catch {
        setSuggestions([]);
      }
    } else {
      setOpen(false);
    }
  };

  return (
    <div className="relative flex-1">
      <input
        value={value}
        onChange={(e) => handleChange(e.target.value)}
        onFocus={() => suggestions.length && setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 200)}
        className="border rounded px-4 py-2 w-full"
        placeholder={placeholder}
      />
      {open && suggestions.length > 0 && (
        <ul className="absolute z-20 mt-1 w-full bg-white border rounded shadow-lg max-h-56 overflow-y-auto">
          {suggestions.map((s) => (
            <li
              key={s.stop_id}
              onMouseDown={() => {
                onPick(s.stop_name);
                setOpen(false);
              }}
              className="px-4 py-2 hover:bg-indigo-50 cursor-pointer text-sm"
            >
              {s.stop_name}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function PassengerDashboard() {
  const [routeText, setRouteText] = useState("");
  const [source, setSource] = useState("");
  const [dest, setDest] = useState("");

  const [routes, setRoutes] = useState([]);
  const [selectedRoute, setSelectedRoute] = useState(null);

  const [tab, setTab] = useState("timetable");
  const [stopsData, setStopsData] = useState(null);
  const [shape, setShape] = useState([]);
  const [live, setLive] = useState(null);

  const [targetTime, setTargetTime] = useState("18:30");
  const [model, setModel] = useState("arima");
  const [prediction, setPrediction] = useState(null);
  const [predicting, setPredicting] = useState(false);

  const [loading, setLoading] = useState(false);
  const [notification, setNotification] = useState(null);
  const pollRef = useRef(null);

  const showNotification = (message, type = "info") => {
    setNotification({ message, type });
    setTimeout(() => setNotification(null), 3500);
  };

  /* ---------------- Search ---------------- */
  const search = async () => {
    setLoading(true);
    setRoutes([]);
    setSelectedRoute(null);
    setPrediction(null);
    try {
      let data;
      if (source.trim() && dest.trim()) {
        data = await gtfsRoutesBetween(source.trim(), dest.trim());
        if (!data.routes?.length) showNotification("No routes serve both stops", "error");
      } else if (routeText.trim()) {
        data = await gtfsSearch(routeText.trim());
        if (!data.routes?.length) showNotification("No routes found", "error");
      } else {
        showNotification("Enter a bus number OR source + destination", "warning");
        setLoading(false);
        return;
      }
      setRoutes(data.routes || []);
      if (data.routes?.length) {
        showNotification(`Found ${data.routes.length} route variant(s)`, "success");
      }
    } catch (err) {
      showNotification(err.message || "Search failed", "error");
    } finally {
      setLoading(false);
    }
  };

  /* ---------------- Route selection ---------------- */
  const refreshLive = async (route) => {
    try {
      const data = await gtfsLive(route.route_id, route.direction_id);
      setLive(data);
    } catch {
      /* transient poll failure — keep last state */
    }
  };

  const selectRoute = async (key) => {
    const route = routes.find((r) => `${r.route_id}:${r.direction_id}` === key);
    if (!route) return;
    setSelectedRoute(route);
    setPrediction(null);
    setLive(null);
    setLoading(true);
    try {
      const [stopsRes, shapeRes] = await Promise.all([
        gtfsRouteStops(route.route_id, route.direction_id),
        gtfsRouteShape(route.route_id, route.direction_id),
      ]);
      setStopsData(stopsRes);
      setShape(shapeRes.shape || []);
      await refreshLive(route);
    } catch (err) {
      showNotification(err.message || "Failed to load route", "error");
    } finally {
      setLoading(false);
    }
  };

  /* ---------------- Live polling (map tab only) ---------------- */
  useEffect(() => {
    if (pollRef.current) clearInterval(pollRef.current);
    if (selectedRoute && tab === "map") {
      pollRef.current = setInterval(() => refreshLive(selectedRoute), 10000);
    }
    return () => pollRef.current && clearInterval(pollRef.current);
  }, [selectedRoute, tab]);

  /* ---------------- Predict ---------------- */
  const runPrediction = async () => {
    if (!selectedRoute || !targetTime) return;
    setPredicting(true);
    setPrediction(null);
    try {
      const data = await predictCrowding({
        routeId: selectedRoute.route_id,
        direction: selectedRoute.direction_id,
        targetTime,
        model,
      });
      setPrediction(data);
    } catch (err) {
      showNotification(err.message || "Prediction failed", "error");
    } finally {
      setPredicting(false);
    }
  };

  /* ---------------- Predict chart ---------------- */
  const predictChart = prediction && {
    labels: [
      ...prediction.history.map((h) => h.time),
      ...prediction.forecast.map((f) => f.time),
    ],
    datasets: [
      {
        label: "Recent crowding (OCI %)",
        data: [...prediction.history.map((h) => h.oci), ...Array(prediction.forecast.length).fill(null)],
        borderColor: "#2563eb",
        tension: 0.3,
        pointRadius: 0,
      },
      {
        label: `${prediction.model.toUpperCase()} forecast`,
        data: [...Array(prediction.history.length).fill(null), ...prediction.forecast.map((f) => f.oci)],
        borderColor: "#9333ea",
        borderDash: [6, 6],
        tension: 0.3,
        pointRadius: 0,
      },
    ],
  };

  const current = stopsData?.current;

  return (
    <div className="min-h-screen bg-gray-100 flex flex-col">
      <Header />

      {notification && (
        <div
          className={`fixed top-5 right-5 px-5 py-3 rounded text-white z-50 max-w-md
            ${notification.type === "success" ? "bg-green-600"
              : notification.type === "error" ? "bg-red-500"
              : notification.type === "warning" ? "bg-yellow-400 text-black"
              : "bg-indigo-600"}`}
        >
          {notification.message}
        </div>
      )}

      <main className="flex-1 p-6 max-w-6xl mx-auto w-full">
        <h2 className="text-2xl font-bold mb-6">Passenger Dashboard</h2>

        {/* Search */}
        <div className="bg-white p-6 rounded-xl shadow mb-6">
          <h3 className="font-semibold mb-4">Find your bus</h3>
          <div className="flex flex-col md:flex-row gap-3">
            <input
              value={routeText}
              onChange={(e) => setRouteText(e.target.value)}
              className="border rounded px-4 py-2 md:w-44"
              placeholder="Bus no. (e.g. 210)"
            />
            <span className="self-center text-gray-400 text-sm">or</span>
            <StopAutocomplete
              placeholder="Source stop"
              value={source}
              onChange={setSource}
              onPick={setSource}
            />
            <StopAutocomplete
              placeholder="Destination stop"
              value={dest}
              onChange={setDest}
              onPick={setDest}
            />
            <button
              onClick={search}
              disabled={loading}
              className="bg-indigo-600 text-white px-6 py-2 rounded disabled:opacity-50"
            >
              Search
            </button>
          </div>
        </div>

        {/* Variants */}
        {routes.length > 0 && (
          <div className="bg-white p-6 rounded-xl shadow mb-6">
            <h3 className="font-semibold mb-4">Select Route & Direction</h3>
            <select
              className="border rounded px-4 py-2 w-full"
              value={selectedRoute ? `${selectedRoute.route_id}:${selectedRoute.direction_id}` : ""}
              onChange={(e) => selectRoute(e.target.value)}
            >
              <option value="">-- Select --</option>
              {routes.map((r) => (
                <option key={`${r.route_id}:${r.direction_id}`} value={`${r.route_id}:${r.direction_id}`}>
                  {r.routeno} — {r.fromstation} → {r.tostation}
                  {r.trip_count ? ` (${r.trip_count} trips/day)` : ""}
                </option>
              ))}
            </select>
          </div>
        )}

        {selectedRoute && stopsData && (
          <>
            {/* Live status strip */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
              <div className="bg-white p-4 rounded-xl shadow text-center">
                <p className="text-xs text-gray-500">Route</p>
                <p className="font-bold">{selectedRoute.routeno}</p>
              </div>
              <div className="bg-white p-4 rounded-xl shadow text-center">
                <p className="text-xs text-gray-500">On road now</p>
                <p className="font-bold">{live?.buses?.length ?? "—"} bus(es)</p>
              </div>
              <div className="bg-white p-4 rounded-xl shadow text-center">
                <p className="text-xs text-gray-500">Crowding now</p>
                <span className={`inline-block mt-1 px-3 py-0.5 rounded text-white text-sm font-semibold ${LEVEL_COLORS[current?.level] || "bg-gray-400"}`}>
                  {current ? `${current.oci}% ${current.level}` : "—"}
                </span>
              </div>
              <div className="bg-white p-4 rounded-xl shadow text-center">
                <p className="text-xs text-gray-500">Next departure</p>
                <p className="font-bold">
                  {live?.upcoming?.length
                    ? `${live.upcoming[0].start} (in ${live.upcoming[0].in_min}m)`
                    : "—"}
                </p>
              </div>
            </div>

            {/* Tabs */}
            <div className="flex gap-2 mb-4">
              {[
                ["timetable", "🕐 Timetable"],
                ["map", "🗺️ Live Map"],
                ["predict", "🔮 Predict Crowding"],
              ].map(([key, label]) => (
                <button
                  key={key}
                  onClick={() => setTab(key)}
                  className={`px-4 py-2 rounded-lg font-medium ${
                    tab === key ? "bg-indigo-600 text-white" : "bg-white text-gray-700 shadow"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>

            {/* TIMETABLE TAB */}
            {tab === "timetable" && (
              <div className="bg-white p-6 rounded-xl shadow mb-6">
                <h3 className="font-semibold mb-1">Stops & bus times</h3>
                <p className="text-xs text-gray-500 mb-4">
                  {stopsData.trips.length} trips scheduled today · times a bus departs each stop
                </p>
                <div className="overflow-x-auto max-h-[28rem] overflow-y-auto">
                  <table className="w-full text-sm border-collapse">
                    <thead className="bg-gray-100 sticky top-0">
                      <tr>
                        <th className="p-2">#</th>
                        <th className="p-2 text-left">Stop</th>
                        <th className="p-2 text-left">Bus times</th>
                      </tr>
                    </thead>
                    <tbody>
                      {stopsData.stops.map((s) => (
                        <tr key={s.stop_id} className="border-t align-top">
                          <td className="p-2 text-center text-gray-400">{s.sequence}</td>
                          <td className="p-2 font-medium">{s.name}</td>
                          <td className="p-2">
                            <div className="flex flex-wrap gap-1">
                              {s.times.map((t) => (
                                <span key={t} className="px-1.5 py-0.5 bg-indigo-50 text-indigo-800 rounded text-xs">
                                  {t}
                                </span>
                              ))}
                              {s.times_truncated && <span className="text-xs text-gray-400">…</span>}
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* MAP TAB */}
            {tab === "map" && (
              <div className="bg-white p-6 rounded-xl shadow mb-6">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="font-semibold">Live tracking</h3>
                  <span className="text-xs text-gray-500">
                    auto-refresh 10s · {live?.server_time ?? ""}
                    {live?.realTracking ? " · real conductor data" : " · simulated positions"}
                  </span>
                </div>
                <BusMap
                  shape={shape}
                  stops={stopsData.stops}
                  buses={live?.buses || []}
                  height={460}
                />
                {live?.buses?.length === 0 && (
                  <p className="text-sm text-gray-500 mt-3">
                    No buses on the road right now per the schedule.
                    {live?.upcoming?.length > 0 &&
                      ` Next departure: ${live.upcoming[0].start} (in ${live.upcoming[0].in_min} min).`}
                  </p>
                )}
                {live?.buses?.length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {live.buses.map((b) => (
                      <span
                        key={b.trip_id}
                        className={`px-2 py-1 rounded text-white text-xs font-mono ${LEVEL_COLORS[b.level]}`}
                        title={`Next: ${b.next_stop ?? "terminus"}`}
                      >
                        {b.vehicle} · {b.oci}%
                      </span>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* PREDICT TAB */}
            {tab === "predict" && (
              <div className="bg-white p-6 rounded-xl shadow mb-6">
                <h3 className="font-semibold mb-4">Predict crowding at a specific time</h3>
                <div className="flex flex-wrap items-center gap-4 mb-4">
                  <label className="text-sm text-gray-600">
                    Time:
                    <input
                      type="time"
                      value={targetTime}
                      onChange={(e) => setTargetTime(e.target.value)}
                      className="ml-2 border rounded px-3 py-1.5"
                    />
                  </label>
                  <div className="flex gap-3 text-sm">
                    {["arima", "prophet"].map((m) => (
                      <label key={m} className="flex items-center gap-1.5">
                        <input
                          type="radio"
                          checked={model === m}
                          onChange={() => setModel(m)}
                        />
                        <span className="uppercase font-medium">{m}</span>
                      </label>
                    ))}
                  </div>
                  <button
                    onClick={runPrediction}
                    disabled={predicting}
                    className="bg-purple-600 text-white px-6 py-2 rounded font-semibold disabled:opacity-50"
                  >
                    {predicting ? "Training model…" : "Predict"}
                  </button>
                </div>

                {prediction && (
                  <>
                    <div className="grid md:grid-cols-3 gap-4 mb-4">
                      <div className="bg-purple-50 border border-purple-200 rounded-lg p-4 text-center">
                        <p className="text-xs text-gray-500">
                          Predicted crowding at {prediction.target_time} ({prediction.model.toUpperCase()})
                        </p>
                        <p className="text-3xl font-bold">{prediction.predicted_oci}%</p>
                        <span className={`inline-block mt-1 px-3 py-0.5 rounded text-white text-sm font-semibold ${LEVEL_COLORS[prediction.level]}`}>
                          {prediction.level}
                        </span>
                      </div>
                      <div className="md:col-span-2 bg-indigo-50 border border-indigo-200 rounded-lg p-4">
                        <p className="text-sm font-medium text-indigo-900">💡 {prediction.suggestion || "No better nearby trip found."}</p>
                        {prediction.trips_near.length > 0 && (
                          <div className="mt-2 flex flex-wrap gap-2">
                            {prediction.trips_near.map((t) => (
                              <span
                                key={t.trip_id}
                                className={`px-2 py-1 rounded text-white text-xs ${LEVEL_COLORS[t.level]}`}
                              >
                                {t.start} → ~{t.predicted_oci}%
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                    <Line
                      data={predictChart}
                      options={{
                        responsive: true,
                        plugins: { legend: { position: "top" } },
                        scales: { y: { min: 0, suggestedMax: 120 } },
                      }}
                    />
                  </>
                )}
              </div>
            )}
          </>
        )}
      </main>

      <Footer />
    </div>
  );
}
