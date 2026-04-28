// CARDEX Edge — frontend logic
// All gRPC calls go through Tauri commands (window.__TAURI__.core.invoke).

const { invoke } = window.__TAURI__.core;

// ─── State ────────────────────────────────────────────────────────────────────
let heartbeatTimer = null;
const history = [];

// ─── Screen helpers ───────────────────────────────────────────────────────────
function showScreen(id) {
  document.querySelectorAll('.screen').forEach(s => {
    s.classList.toggle('active', s.id === id);
    s.classList.toggle('hidden', s.id !== id);
  });
}

function showTab(name) {
  document.querySelectorAll('.tab').forEach(t =>
    t.classList.toggle('active', t.id === `tab-${name}`)
  );
  document.querySelectorAll('.nav-btn').forEach(b =>
    b.classList.toggle('active', b.dataset.tab === name)
  );
}

function showResult(el, ok, msg) {
  el.textContent = msg;
  el.className = `result ${ok ? 'ok' : 'err'}`;
  el.classList.remove('hidden');
}

// ─── Login ────────────────────────────────────────────────────────────────────
document.getElementById('form-login').addEventListener('submit', async e => {
  e.preventDefault();
  const errEl = document.getElementById('login-error');
  errEl.classList.add('hidden');

  const dealerId   = document.getElementById('inp-dealer-id').value.trim();
  const apiKey     = document.getElementById('inp-api-key').value.trim();
  const serverAddr = document.getElementById('inp-server-addr').value.trim();

  try {
    await invoke('login', { dealerId, apiKey, serverAddr });
    showScreen('screen-main');
    startHeartbeat();
  } catch (err) {
    errEl.textContent = String(err);
    errEl.classList.remove('hidden');
  }
});

document.getElementById('btn-logout').addEventListener('click', () => {
  stopHeartbeat();
  showScreen('screen-login');
});

// ─── Navigation ───────────────────────────────────────────────────────────────
document.querySelectorAll('.nav-btn').forEach(btn => {
  btn.addEventListener('click', () => showTab(btn.dataset.tab));
});

// ─── Heartbeat ────────────────────────────────────────────────────────────────
const dot   = document.querySelector('.dot');
const label = document.getElementById('heartbeat-label');

function startHeartbeat() {
  pingHeartbeat();
  heartbeatTimer = setInterval(pingHeartbeat, 30_000);
}

function stopHeartbeat() {
  clearInterval(heartbeatTimer);
  dot.className = 'dot';
  label.textContent = 'Disconnected';
}

async function pingHeartbeat() {
  try {
    const ts = await invoke('heartbeat');
    const t  = new Date(ts * 1000).toLocaleTimeString();
    dot.className  = 'dot ok';
    label.textContent = `Connected · ${t}`;
  } catch {
    dot.className  = 'dot err';
    label.textContent = 'Server unreachable';
  }
}

// ─── Push single vehicle ──────────────────────────────────────────────────────
document.getElementById('form-vehicle').addEventListener('submit', async e => {
  e.preventDefault();
  const resultEl = document.getElementById('push-result');
  resultEl.classList.add('hidden');

  const listing = {
    vin:          document.getElementById('v-vin').value.trim().toUpperCase(),
    make:         document.getElementById('v-make').value.trim(),
    model:        document.getElementById('v-model').value.trim(),
    year:         parseInt(document.getElementById('v-year').value, 10),
    price_cents:  parseInt(document.getElementById('v-price-cents').value || '0', 10),
    currency:     document.getElementById('v-currency').value.trim().toUpperCase() || 'EUR',
    mileage_km:   parseInt(document.getElementById('v-mileage').value || '0', 10),
    fuel_type:    document.getElementById('v-fuel').value,
    transmission: document.getElementById('v-transmission').value,
    color:        document.getElementById('v-color').value.trim(),
    source_url:   document.getElementById('v-source-url').value.trim(),
    image_urls:   [],
    description:  document.getElementById('v-description').value.trim(),
  };

  try {
    const summary = await invoke('push_vehicle', { listing });
    addHistory(summary);
    showResult(resultEl, true,
      `✓ Accepted: ${summary.accepted}   Rejected: ${summary.rejected}`
    );
    if (summary.rejected > 0) {
      resultEl.className = 'result err';
      resultEl.textContent += '\n' + summary.errors.join('\n');
    }
  } catch (err) {
    showResult(resultEl, false, String(err));
  }
});

// ─── Bulk CSV import ──────────────────────────────────────────────────────────
const dropZone   = document.getElementById('drop-zone');
const fileInput  = document.getElementById('file-input');
const csvPreview = document.getElementById('csv-preview');

document.getElementById('btn-browse').addEventListener('click', () => fileInput.click());

fileInput.addEventListener('change', () => {
  const file = fileInput.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = ev => { csvPreview.value = ev.target.result; };
  reader.readAsText(file);
});

dropZone.addEventListener('dragover', e => {
  e.preventDefault();
  dropZone.classList.add('over');
});
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('over'));
dropZone.addEventListener('drop', e => {
  e.preventDefault();
  dropZone.classList.remove('over');
  const file = e.dataTransfer.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = ev => { csvPreview.value = ev.target.result; };
  reader.readAsText(file);
});

document.getElementById('btn-push-csv').addEventListener('click', async () => {
  const resultEl = document.getElementById('bulk-result');
  resultEl.classList.add('hidden');

  const csvText = csvPreview.value.trim();
  if (!csvText) {
    showResult(resultEl, false, 'Paste or drop a CSV file first.');
    return;
  }

  try {
    const summary = await invoke('push_csv', { csvText });
    addHistory(summary);
    showResult(resultEl, summary.rejected === 0,
      `Accepted: ${summary.accepted}   Rejected: ${summary.rejected}` +
      (summary.errors.length ? '\n' + summary.errors.join('\n') : '')
    );
  } catch (err) {
    showResult(resultEl, false, String(err));
  }
});

// ─── History ──────────────────────────────────────────────────────────────────
function addHistory(summary) {
  history.unshift({ time: new Date().toLocaleTimeString(), ...summary });
  renderHistory();
}

function renderHistory() {
  const tbody = document.getElementById('history-tbody');
  tbody.innerHTML = history.map(h =>
    `<tr>
      <td>${h.time}</td>
      <td style="color:var(--ok)">${h.accepted}</td>
      <td style="color:${h.rejected > 0 ? 'var(--error)' : 'var(--text-dim)'}">${h.rejected}</td>
    </tr>`
  ).join('');
}
