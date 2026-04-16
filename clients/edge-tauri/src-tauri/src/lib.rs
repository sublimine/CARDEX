// CARDEX Edge Tauri — Rust backend
//
// Commands exposed to the webview (invoked via window.__TAURI__.core.invoke):
//
//   login(dealer_id, api_key, server_addr) → Result<(), String>
//   push_vehicle(listing: VehicleListing)  → Result<PushSummary, String>
//   push_csv(csv_text: String)             → Result<PushSummary, String>
//   heartbeat()                            → Result<i64, String>
//   get_connection_status()                → ConnectionStatus

use std::sync::Mutex;
use tauri::{Manager, State};

mod grpc_client;

use grpc_client::{CardexEdgeClient, VehicleListing, PushSummary};

// ─── App state ───────────────────────────────────────────────────────────────

struct AppState {
    client: Mutex<Option<CardexEdgeClient>>,
}

// ─── Tauri commands ──────────────────────────────────────────────────────────

/// Authenticate with the CARDEX Edge Push server.
/// Stores the authenticated client in app state for subsequent calls.
#[tauri::command]
async fn login(
    dealer_id: String,
    api_key: String,
    server_addr: String,
    state: State<'_, AppState>,
) -> Result<(), String> {
    let client = CardexEdgeClient::connect(dealer_id, api_key, server_addr)
        .await
        .map_err(|e| format!("Connection failed: {e}"))?;

    *state.client.lock().unwrap() = Some(client);
    Ok(())
}

/// Push a single vehicle listing to CARDEX.
#[tauri::command]
async fn push_vehicle(
    listing: VehicleListing,
    state: State<'_, AppState>,
) -> Result<PushSummary, String> {
    let guard = state.client.lock().unwrap();
    let client = guard
        .as_ref()
        .ok_or("Not connected — call login first")?
        .clone();
    drop(guard);

    client
        .push_listings(vec![listing])
        .await
        .map_err(|e| format!("Push failed: {e}"))
}

/// Parse a CSV string and push all rows to CARDEX in one batch.
///
/// CSV format (header required):
///   vin,make,model,year,price_cents,currency,mileage_km,fuel_type,transmission,color,source_url
#[tauri::command]
async fn push_csv(
    csv_text: String,
    state: State<'_, AppState>,
) -> Result<PushSummary, String> {
    let listings = parse_csv(&csv_text)?;
    if listings.is_empty() {
        return Ok(PushSummary { accepted: 0, rejected: 0, errors: vec![] });
    }

    let guard = state.client.lock().unwrap();
    let client = guard
        .as_ref()
        .ok_or("Not connected — call login first")?
        .clone();
    drop(guard);

    client
        .push_listings(listings)
        .await
        .map_err(|e| format!("Bulk push failed: {e}"))
}

/// Ping the server and return its Unix timestamp.
#[tauri::command]
async fn heartbeat(state: State<'_, AppState>) -> Result<i64, String> {
    let guard = state.client.lock().unwrap();
    let client = guard
        .as_ref()
        .ok_or("Not connected — call login first")?
        .clone();
    drop(guard);

    client
        .heartbeat()
        .await
        .map_err(|e| format!("Heartbeat failed: {e}"))
}

/// Returns whether the app has an active gRPC connection.
#[tauri::command]
fn get_connection_status(state: State<'_, AppState>) -> bool {
    state.client.lock().unwrap().is_some()
}

// ─── CSV parser ──────────────────────────────────────────────────────────────

fn parse_csv(text: &str) -> Result<Vec<VehicleListing>, String> {
    let mut rdr = csv::ReaderBuilder::new()
        .has_headers(true)
        .trim(csv::Trim::All)
        .from_reader(text.as_bytes());

    let mut out = Vec::new();
    for (i, result) in rdr.deserialize::<VehicleListing>().enumerate() {
        match result {
            Ok(listing) => out.push(listing),
            Err(e) => return Err(format!("CSV row {}: {e}", i + 2)),
        }
    }
    Ok(out)
}

// ─── App entry point ─────────────────────────────────────────────────────────

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_store::Builder::default().build())
        .manage(AppState {
            client: Mutex::new(None),
        })
        .invoke_handler(tauri::generate_handler![
            login,
            push_vehicle,
            push_csv,
            heartbeat,
            get_connection_status,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
