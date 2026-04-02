// CARDEX Intelligence — Popup Script

const dot = document.getElementById('status-dot');
const statusText = document.getElementById('status-text');
const toggleEnabled = document.getElementById('toggle-enabled');
const btnSettings = document.getElementById('btn-settings');

// Load settings
chrome.runtime.sendMessage({ type: 'GET_SETTINGS' }, (settings) => {
  toggleEnabled.checked = settings.enabled !== false;

  // Test API connectivity
  const apiUrl = (settings.apiUrl || 'http://localhost:8080').replace(/\/$/, '');
  fetch(`${apiUrl}/healthz`, { signal: AbortSignal.timeout(3000) })
    .then(r => {
      if (r.ok) {
        dot.className = 'status-dot';
        statusText.textContent = `Conectado a ${apiUrl}`;
      } else {
        throw new Error(`HTTP ${r.status}`);
      }
    })
    .catch(() => {
      dot.className = 'status-dot inactive';
      statusText.textContent = 'API no disponible — configurar URL';
    });
});

// Toggle enable/disable
toggleEnabled.addEventListener('change', () => {
  chrome.runtime.sendMessage({
    type: 'SAVE_SETTINGS',
    payload: { enabled: toggleEnabled.checked },
  });
});

// Open settings
btnSettings.addEventListener('click', () => {
  chrome.runtime.openOptionsPage();
});
