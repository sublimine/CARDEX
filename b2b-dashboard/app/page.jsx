"use client";

import { useEffect, useState, useRef } from "react";

export default function Dashboard() {
  const [opportunities, setOpportunities] = useState([]);
  const [wsStatus, setWsStatus] = useState("DISCONNECTED");
  const wsRef = useRef(null);

  useEffect(() => {
    // 1. Verificación JWT existente (opcional: redirigir a /login si no hay token)
    const token = typeof window !== "undefined" ? localStorage.getItem("cardex_token") : null;
    if (!token) {
      // En producción: router.push('/login');
    }

    // 2. Carga Histórica Institucional desde PostgreSQL
    const fetchHistoricalData = async () => {
      const res = await fetch("/api/assets");
      if (res.ok) {
        const historicalAssets = await res.json();
        setOpportunities(historicalAssets);
      }
    };
    fetchHistoricalData();

    // 3. Inicialización del WebSocket para streaming en tiempo real
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
          <tr style={{ borderBottom: "1px solid #333", color: "#888" }}>
            <th style={{ padding: "10px" }}>VIN</th>
            <th style={{ padding: "10px" }}>NET LANDED COST</th>
            <th style={{ padding: "10px" }}>LEGAL STATUS</th>
            <th style={{ padding: "10px" }}>QUOTE ID (SHA-256)</th>
          </tr>
        </thead>
        <tbody>
          {opportunities.map((opp, idx) => (
            <tr
              key={opp.quote_id || idx}
              style={{
                borderBottom: "1px solid #222",
                backgroundColor:
                  idx === 0 ? "rgba(0, 255, 204, 0.05)" : "transparent",
                transition: "background-color 0.5s",
              }}
            >
              <td style={{ padding: "10px", fontWeight: "bold" }}>{opp.vin}</td>
              <td style={{ padding: "10px", color: "#00ffcc" }}>
                {opp.nlc ? `${opp.nlc} EUR` : "CALCULATING..."}
              </td>
              <td
                style={{
                  padding: "10px",
                  color:
                    opp.legal_status === "VAT_DEDUCTIBLE" ? "#00ffcc" : "#ffaa00",
                }}
              >
                {opp.legal_status || "ANALYZING..."}
              </td>
              <td
                style={{
                  padding: "10px",
                  fontSize: "12px",
                  color: "#666",
                }}
              >
                {opp.quote_id}
              </td>
            </tr>
          ))}
          {opportunities.length === 0 && (
            <tr>
              <td
                colSpan="4"
                style={{
                  padding: "20px",
                  textAlign: "center",
                  color: "#666",
                }}
              >
                ESPERANDO TRANSMISIÓN HFT...
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </main>
  );
}
