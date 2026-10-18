import React, { useMemo } from "react";
import { MapContainer, TileLayer, Polyline, CircleMarker, Marker, Tooltip, Popup } from "react-leaflet";
import L from "leaflet";

const LEVEL_COLORS = {
  LOW: "#16a34a",
  MEDIUM: "#ca8a04",
  HIGH: "#ea580c",
  SEVERE: "#dc2626",
};

function busIcon(level, bearing = 0) {
  const color = LEVEL_COLORS[level] || "#2563eb";
  return L.divIcon({
    className: "",
    html: `
      <div style="position:relative;width:34px;height:34px;">
        <div style="
          position:absolute;inset:0;background:${color};border:2.5px solid #fff;
          border-radius:50%;box-shadow:0 1px 5px rgba(0,0,0,.45);
          display:flex;align-items:center;justify-content:center;
          font-size:15px;color:#fff;transform:rotate(${bearing}deg);
        ">➤</div>
      </div>`,
    iconSize: [34, 34],
    iconAnchor: [17, 17],
  });
}

/**
 * Shared live map: route shape, stops, and moving buses colored by crowding.
 * Parents poll the live endpoint and pass fresh `buses`.
 */
export default function BusMap({ shape = [], stops = [], buses = [], height = 420, children }) {
  const center = useMemo(() => {
    if (shape.length) return shape[Math.floor(shape.length / 2)];
    if (stops.length) return [stops[0].lat, stops[0].lon];
    if (buses.length) return [buses[0].lat, buses[0].lon];
    return [12.9716, 77.5946]; // Bengaluru
  }, [shape, stops, buses]);

  return (
    <div style={{ height }} className="rounded-xl overflow-hidden border shadow">
      <MapContainer
        center={center}
        zoom={12}
        style={{ height: "100%", width: "100%" }}
        scrollWheelZoom
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />

        {shape.length > 1 && (
          <Polyline positions={shape} pathOptions={{ color: "#2563eb", weight: 4, opacity: 0.65 }} />
        )}

        {stops.map((s, i) => (
          <CircleMarker
            key={`${s.name}-${i}`}
            center={[s.lat, s.lon]}
            radius={5}
            pathOptions={{ color: "#1e40af", fillColor: "#fff", fillOpacity: 1, weight: 2 }}
          >
            <Tooltip direction="top">
              <span>
                {i + 1}. {s.name}
                {s.times?.length > 0 && (
                  <span className="block text-xs text-gray-500">
                    Buses: {s.times.slice(0, 6).join(", ")}
                    {s.times.length > 6 ? "…" : ""}
                  </span>
                )}
              </span>
            </Tooltip>
          </CircleMarker>
        ))}

        {buses.map((b) => (
          <Marker key={b.trip_id} position={[b.lat, b.lon]} icon={busIcon(b.level, b.bearing)}>
            <Popup>
              <div className="text-sm">
                <p className="font-semibold font-mono">{b.vehicle}</p>
                <p>
                  Crowding: <b>{b.oci}%</b> ({b.level})
                  {b.simulated && <span className="text-gray-400"> · simulated</span>}
                </p>
                <p>
                  {b.status === "AT_STOP"
                    ? `At stop: ${b.current_stop}`
                    : `Next: ${b.next_stop ?? "terminus"}${b.eta_min ? ` in ~${b.eta_min} min` : ""}`}
                </p>
                <p className="text-gray-500">Trip progress: {b.progress}%</p>
              </div>
            </Popup>
          </Marker>
        ))}

        {children}
      </MapContainer>
    </div>
  );
}
