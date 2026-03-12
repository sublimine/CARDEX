"use client";

import { useEffect, useState, useRef } from "react";

export default function Dashboard() {
  const [opportunities, setOpportunities] = useState([]);
  const [wsStatus, setWsStatus] = useState("DISCONNECTED");
  const wsRef = useRef(null);

  useEffect(() => {
    const token = typeof window !== "undefined" ? localStorage.getItem("cardex_token") : null;

    const fetchHistoricalData = async () => {
      const res = await fetch("/api/assets");
      if (res.ok) {
        const historicalAssets = await res.json();
        setOpportunities(historicalAssets);
      }
    };
    fetchHistoricalData();

    const wsUrl = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8084/ws";
    wsRef.current = new WebSocket(wsUrl);

    wsRef.current.onopen = () => setWsStatus("CONNECTED");
    wsRef.current.onclose = () => setWsStatus("DISCONNECTED");
    wsRef.current.onmessage = (event) => {
      try {
        const newAsset = JSON.parse(event.data);
        setOpportunities((prev) => [newAsset, ...prev]);
      } catch {
        // Ignorar payloads inválidos
      }
    };

    return () => {
      if (wsRef.current) wsRef.current.close();
    };
  }, []);

  return (
    <main>
      <header
        style={{
          borderBottom: "1px solid #333",
          paddingBottom: "10px",
          marginBottom: "20px",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-end",
        }}
      >
        <div>
          <h1 style={{ color: "#00ffcc", margin: 0 }}>
            [ CARDEX ] MESA DE DECISIONES B2B
          </h1>
          <p style={{ margin: "5px 0 0 0", fontSize: "12px", color: "#888" }}>
            {opportunities.length} ACTIVOS EN DARK POOL
          </p>
        </div>
        <div
          style={{
            fontSize: "12px",
            color: wsStatus === "CONNECTED" ? "#00ffcc" : "#ff0033",
            fontFamily: "monospace",
            fontWeight: "bold",
          }}
        >
          ● WSS STATUS: {wsStatus}
        </div>
      </header>

      <table
        style={{
          width: "100%",
          textAlign: "left",
          borderCollapse: "collapse",
        }}
      >
        <thead>
          <tr style={{ borderBottom: "1px solid #333", color: "#888", fontSize: "11px" }}>
            <th style={{ padding: "10px", width: "80px" }}>VISUAL</th>
            <th style={{ padding: "10px" }}>VEHÍCULO (ASSET)</th>
            <th style={{ padding: "10px" }}>VIN / ID</th>
            <th style={{ padding: "10px" }}>NET LANDED COST</th>
            <th style={{ padding: "10px" }}>STATUS LEGAL</th>
            <th style={{ padding: "10px", textAlign: "right" }}>PAYLOAD_ID</th>
          </tr>
        </thead>
        <tbody>
          {opportunities.map((opp, idx) => (
            <tr
              key={opp.quote_id || idx}
              style={{
                borderBottom: "1px solid #222",
                backgroundColor: idx === 0 ? "rgba(0, 255, 204, 0.05)" : "transparent",
                transition: "background-color 0.5s",
              }}
            >
              <td style={{ padding: "10px" }}>
                <img 
                  src={opp.image_url || "https://via.placeholder.com/150x100/111111/444444?text=NO+IMAGE"} 
                  alt={opp.title || "Vehículo sin imagen"} 
                  style={{ width: "80px", height: "50px", objectFit: "cover", borderRadius: "4px", border: "1px solid #333" }}
                  onError={(e) => { e.target.onerror = null; e.target.src = "https://via.placeholder.com/150x100/111111/444444?text=ERROR" }}
                />
              </td>
              <td style={{ padding: "10px", fontWeight: "bold", color: "#eee" }}>
                {opp.title || "MODELO DESCONOCIDO"}
                <div style={{ fontSize: "10px", color: "#666", marginTop: "4px" }}>
                  <a href={opp.source_url} target="_blank" rel="noreferrer" style={{ color: "#00ffcc", textDecoration: "none" }}>[ VER ORIGEN ]</a>
                </div>
              </td>
              <td style={{ padding: "10px", fontFamily: "monospace", fontSize: "12px", color: "#999" }}>
                {opp.vin}
              </td>
              <td style={{ padding: "10px", color: "#00ffcc", fontWeight: "bold" }}>
                {opp.nlc && opp.nlc > 0 ? new Intl.NumberFormat('es-ES', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 }).format(opp.nlc) : "CALCULATING..."}
              </td>
              <td
                style={{
                  padding: "10px",
                  fontSize: "11px",
                  fontWeight: "bold",
                  color: opp.legal_status === "VAT_DEDUCTIBLE" ? "#00ffcc" : "#ffaa00",
                }}
              >
                {opp.legal_status || "PENDING_NLP"}
              </td>
              <td
                style={{
                  padding: "10px",
                  fontSize: "10px",
                  color: "#444",
                  fontFamily: "monospace",
                  textAlign: "right"
                }}
              >
                {opp.quote_id}
              </td>
            </tr>
          ))}
          {opportunities.length === 0 && (
            <tr>
              <td
                colSpan="6"
                style={{
                  padding: "40px",
                  textAlign: "center",
                  color: "#444",
                  fontFamily: "monospace"
                }}
              >
                [ ] ESPERANDO TRANSMISIÓN HFT DESDE DARK POOL...
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </main>
  );
}
