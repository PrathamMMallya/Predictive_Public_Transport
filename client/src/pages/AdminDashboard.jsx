import { Fragment, useEffect, useRef, useState } from "react";
import Header from "../components/Header";
import Footer from "../components/Footer";
import BusMap from "../components/BusMap";
import html2canvas from "html2canvas";
import jsPDF from "jspdf";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import { useAuth } from "../context/AuthContext";
import {
  getAdminDashboard,
  gtfsSearch,
  gtfsLive,
  getBusInsights,
} from "../services/api";

const INSIGHT_STYLES = {
  critical: "border-red-300 bg-red-50 text-red-900",
  saving: "border-green-300 bg-green-50 text-green-900",
  info: "border-blue-300 bg-blue-50 text-blue-900",
  live: "border-purple-300 bg-purple-50 text-purple-900",
};

export default function AdminDashboard() {
  const { token } = useAuth();

  // fleet-wide (existing)
  const [buses, setBuses] = useState([]);
  const [stats, setStats] = useState({ totalBuses: 0, totalPassengers: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [sortByOvercrowding, setSortByOvercrowding] = useState(false);

  // per-bus insights (new)
  const [routeText, setRouteText] = useState("");
  const [variants, setVariants] = useState([]);
  const [selected, setSelected] = useState(null);
  const [insights, setInsights] = useState(null);
  const [insightsLoading, setInsightsLoading] = useState(false);
  const livePollRef = useRef(null);

  useEffect(() => {
    (async () => {
      try {
        const dashboard = await getAdminDashboard(token);
        setBuses(Array.isArray(dashboard.buses) ? dashboard.buses : []);
        setStats({
          totalBuses: dashboard.totalBuses ?? 0,
          totalPassengers: dashboard.totalPassengers ?? 0,
        });
      } catch (err) {
        setError(err.message || "Unable to load admin dashboard data");
      } finally {
        setLoading(false);
      }
    })();
  }, [token]);

  /* -------- per-bus insights -------- */
  const searchRoutes = async () => {
    if (!routeText.trim()) return;
    const data = await gtfsSearch(routeText.trim());
    setVariants(data.routes || []);
    setSelected(null);
    setInsights(null);
  };

  const loadInsights = async (key) => {
    const variant = variants.find((v) => `${v.route_id}:${v.direction_id}` === key);
    if (!variant) return;
    setSelected(variant);
    setInsightsLoading(true);
    try {
      const data = await getBusInsights(token, variant.route_id, variant.direction_id);
      setInsights(data);
    } catch (err) {
      alert(err.message || "Failed to load insights");
    } finally {
      setInsightsLoading(false);
    }
  };

  // live refresh of the insight map every 15s
  useEffect(() => {
    if (livePollRef.current) clearInterval(livePollRef.current);
    if (selected && insights) {
      livePollRef.current = setInterval(async () => {
        try {
          const live = await gtfsLive(selected.route_id, selected.direction_id);
          setInsights((prev) => (prev ? { ...prev, live } : prev));
        } catch {
          /* keep last state */
        }
      }, 15000);
    }
    return () => livePollRef.current && clearInterval(livePollRef.current);
  }, [selected, insights?.route_id]);

  /* -------- PDF -------- */
  const downloadBusReport = async (bus, period) => {
    const element = document.getElementById(`bus-${bus.routeparentid}`);
    if (!element) return alert("Unable to generate PDF. Element not found.");
    const canvas = await html2canvas(element, { scale: 2, useCORS: true, backgroundColor: "#ffffff" });
    const imgData = canvas.toDataURL("image/png");
    const pdf = new jsPDF("landscape", "mm", "a4");
    pdf.setFontSize(16);
    pdf.text("BMTC Overcrowding Report", 14, 15);
    pdf.setFontSize(11);
    pdf.text(`Route No: ${bus.routeno ?? "N/A"}`, 14, 25);
    pdf.text(`Report Type: ${period}`, 14, 32);
    pdf.text(`Passengers: ${bus.currentPassengers ?? 0}/${bus.capacity ?? 0}`, 14, 39);
    pdf.addImage(imgData, "PNG", 10, 45, 275, 130);
    pdf.save(`BMTC_${bus.routeno}_${period}_report.pdf`);
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center text-lg">
        Loading Admin Dashboard...
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen flex flex-col bg-gray-100">
        <Header />
        <main className="flex-1 flex items-center justify-center text-red-600 font-semibold">
          {error}
        </main>
        <Footer />
      </div>
    );
  }

  const sortedBuses = [...buses];
  if (sortByOvercrowding) {
    sortedBuses.sort((a, b) => (b.overcrowdingIndex ?? 0) - (a.overcrowdingIndex ?? 0));
  }

  return (
    <div className="min-h-screen flex flex-col bg-gray-100">
      <Header />

      <main className="flex-1 p-6 max-w-7xl mx-auto w-full">
        <h2 className="text-2xl font-bold mb-6">Admin Dashboard</h2>

        {/* Stats */}
        <div className="grid md:grid-cols-2 gap-6 mb-8">
          <div className="bg-white p-6 rounded-xl shadow">
            <h4 className="text-gray-500 text-sm mb-1">Tracked Routes</h4>
            <p className="text-3xl font-bold">{stats.totalBuses}</p>
          </div>
          <div className="bg-white p-6 rounded-xl shadow">
            <h4 className="text-gray-500 text-sm mb-1">Passengers in System</h4>
            <p className="text-3xl font-bold">{stats.totalPassengers}</p>
          </div>
        </div>

        {/* ============ PER-BUS INSIGHTS ============ */}
        <div className="bg-white rounded-xl shadow p-6 mb-8">
          <h3 className="text-lg font-semibold mb-1">🔍 Bus Insights & Frequency Decisions</h3>
          <p className="text-sm text-gray-500 mb-4">
            Pick a route to see live crowding, scheduled vs recommended frequency, and decision insights.
          </p>

          <div className="flex flex-col md:flex-row gap-3 mb-4">
            <input
              value={routeText}
              onChange={(e) => setRouteText(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && searchRoutes()}
              className="border rounded px-4 py-2 flex-1"
              placeholder="Enter bus number (e.g. 210, 500, 335)"
            />
            <button onClick={searchRoutes} className="bg-indigo-600 text-white px-6 py-2 rounded">
              Search
            </button>
            {variants.length > 0 && (
              <select
                className="border rounded px-4 py-2 flex-1"
                value={selected ? `${selected.route_id}:${selected.direction_id}` : ""}
                onChange={(e) => loadInsights(e.target.value)}
              >
                <option value="">-- Select variant --</option>
                {variants.map((v) => (
                  <option key={`${v.route_id}:${v.direction_id}`} value={`${v.route_id}:${v.direction_id}`}>
                    {v.routeno} — {v.fromstation} → {v.tostation}
                  </option>
                ))}
              </select>
            )}
          </div>

          {insightsLoading && <p className="text-gray-500 py-6 text-center">Analyzing route…</p>}

          {insights && !insightsLoading && (
            <>
              {/* Insight cards */}
              <div className="grid md:grid-cols-2 gap-3 mb-5">
                {insights.insights.map((ins, i) => (
                  <div key={i} className={`border rounded-lg p-3 text-sm ${INSIGHT_STYLES[ins.type] || INSIGHT_STYLES.info}`}>
                    <span className="font-semibold uppercase text-xs mr-2">{ins.type}</span>
                    {ins.text}
                  </div>
                ))}
              </div>

              <div className="grid lg:grid-cols-2 gap-6 mb-5">
                {/* Live map */}
                <div>
                  <h4 className="font-medium mb-2 text-sm text-gray-600">
                    Live map ({insights.live.buses.length} bus(es) on road)
                  </h4>
                  <BusMap
                    shape={insights.shape}
                    stops={insights.stops}
                    buses={insights.live.buses}
                    height={380}
                  />
                </div>

                {/* 7-day profile */}
                <div>
                  <h4 className="font-medium mb-2 text-sm text-gray-600">
                    Average crowding by hour (last 7 days)
                  </h4>
                  <div className="w-full h-[380px]">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={insights.profile_7d}>
                        <XAxis dataKey="hour" fontSize={11} />
                        <YAxis domain={[0, 130]} fontSize={11} />
                        <Tooltip />
                        <Bar dataKey="avgOci" fill="#6366f1" name="Avg OCI %" />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              </div>

              {/* Frequency decision table */}
              <h4 className="font-medium mb-2 text-sm text-gray-600">
                Scheduled vs recommended trips/hour
                <span className={`ml-3 font-semibold ${insights.totals.delta > 0 ? "text-red-600" : insights.totals.delta < 0 ? "text-green-600" : "text-gray-500"}`}>
                  daily: {insights.totals.scheduled} → {insights.totals.recommended}
                  ({insights.totals.delta > 0 ? "+" : ""}{insights.totals.delta})
                </span>
              </h4>
              <div className="overflow-x-auto max-h-72 overflow-y-auto">
                <table className="w-full text-sm border-collapse">
                  <thead className="bg-gray-100 sticky top-0">
                    <tr>
                      <th className="p-2">Hour</th>
                      <th className="p-2 text-center">Avg crowding</th>
                      <th className="p-2 text-center">Scheduled trips</th>
                      <th className="p-2 text-center">Recommended</th>
                      <th className="p-2 text-center">Decision</th>
                    </tr>
                  </thead>
                  <tbody>
                    {insights.frequency.map((f) => {
                      const delta = f.recommendedTrips - f.scheduledTrips;
                      return (
                        <tr key={f.hour} className="border-t">
                          <td className="p-2">{f.hour}</td>
                          <td className="p-2 text-center">{f.avgOci}%</td>
                          <td className="p-2 text-center">{f.scheduledTrips}</td>
                          <td className="p-2 text-center">{f.recommendedTrips}</td>
                          <td className={`p-2 text-center font-semibold ${delta > 0 ? "text-red-600" : delta < 0 ? "text-green-600" : "text-gray-400"}`}>
                            {delta > 0 ? `+${delta} add` : delta < 0 ? `${delta} trim` : "keep"}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>

        {/* ============ FLEET-WIDE ============ */}
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-xl font-semibold">Tracked Routes (live counters)</h3>
          <button
            className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700"
            onClick={() => setSortByOvercrowding((p) => !p)}
          >
            {sortByOvercrowding ? "Unsort" : "Sort by Overcrowding"}
          </button>
        </div>

        {sortedBuses.length === 0 ? (
          <div className="p-6 text-center text-gray-500 bg-white rounded-xl shadow">
            No active buses found
          </div>
        ) : (
          sortedBuses.map((bus) => (
            <div
              key={bus.routeparentid}
              id={`bus-${bus.routeparentid}`}
              className="bg-white rounded-xl shadow mb-8 p-4"
            >
              <div className="flex justify-between items-center mb-3">
                <h3 className="text-lg font-semibold">
                  {bus.routeno || bus.routeparentid} ({bus.currentPassengers ?? 0}/{bus.capacity ?? 0})
                  {bus.vehicle && <span className="ml-2 text-sm font-mono text-gray-500">{bus.vehicle}</span>}
                </h3>
                <span
                  className={`px-2 py-1 rounded text-white font-medium ${
                    bus.overcrowdingIndex > 100
                      ? "bg-red-600"
                      : bus.overcrowdingIndex > 75
                        ? "bg-orange-500"
                        : "bg-green-600"
                  }`}
                >
                  {bus.overcrowdingIndex ?? 0}%
                </span>
              </div>

              <div className="flex gap-2 mb-4">
                <button onClick={() => downloadBusReport(bus, "Daily")} className="bg-gray-800 text-white px-3 py-1 rounded text-sm">
                  Daily PDF
                </button>
                <button onClick={() => downloadBusReport(bus, "Weekly")} className="bg-gray-700 text-white px-3 py-1 rounded text-sm">
                  Weekly PDF
                </button>
                <button onClick={() => downloadBusReport(bus, "Bi-Weekly")} className="bg-gray-600 text-white px-3 py-1 rounded text-sm">
                  Bi-Weekly PDF
                </button>
              </div>

              <div className="w-full h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={bus.stops || []}>
                    <XAxis dataKey="name" angle={-30} textAnchor="end" interval={0} height={60} fontSize={10} />
                    <YAxis />
                    <Tooltip />
                    <Legend />
                    <Bar dataKey="boarded" fill="#4ade80" />
                    <Bar dataKey="departed" fill="#f87171" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          ))
        )}
      </main>

      <Footer />
    </div>
  );
}
