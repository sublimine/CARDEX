#![cfg_attr(
    all(not(debug_assertions), target_os = "windows"),
    windows_subsystem = "windows"
)]

use std::time::Instant;
use tauri::{Manager, WebviewUrl, WebviewWindowBuilder};

#[tauri::command]
async fn safe_upload_fifo(url: String, filepath: String) -> Result<u128, String> {
    // Passive TCP Backpressure: Sube foto y mide Socket RTT.
    // El frontend estrangulará la cola si supera 500ms.
    let file_bytes = std::fs::read(&filepath).map_err(|e| e.to_string())?;
    let start = Instant::now();

    let client = reqwest::Client::new();
    let res = client
        .post(&url)
        .body(file_bytes)
        .send()
        .await
        .map_err(|e| e.to_string())?;

    if res.status().is_success() {
        Ok(start.elapsed().as_millis())
    } else {
        Err("Error en subida".into())
    }
}

#[tauri::command]
async fn execute_shadow_osint(app: tauri::AppHandle, url: String) -> Result<String, String> {
    // ZERO-CHROMIUM: Instancia motor nativo Edge WebView2 oculto (visible: false)
    let url_parsed = url::Url::parse(&url).map_err(|e| e.to_string())?;
    let ghost = WebviewWindowBuilder::new(&app, "ghost", WebviewUrl::External(url_parsed))
        .visible(false)
        .decorations(false)
        .build()
        .map_err(|e| e.to_string())?;

    // Extracción silenciosa amparada en EU Data Act
    ghost
        .eval(
            r#"setTimeout(() => {
            let m = document.body?.innerHTML?.match(/data-initial-state="([^"]+)"/);
            if (m) window.__TAURI__.core.invoke('osint_cb', { data: m[1] });
        }, 4000);"#,
        )
        .map_err(|e| e.to_string())?;

    Ok("Extracción Delegada Inicializada".into())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .invoke_handler(tauri::generate_handler![safe_upload_fifo, execute_shadow_osint])
        .run(tauri::generate_context!())
        .expect("Error al inicializar el motor Tauri CRM");
}
