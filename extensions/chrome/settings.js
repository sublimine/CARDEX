// CARDEX Intelligence — Settings Script

const apiUrlInput = document.getElementById('api-url');
const btnSave = document.getElementById('btn-save');
const toast = document.getElementById('toast');
const urlError = document.getElementById('url-error');

// Load existing settings
chrome.runtime.sendMessage({ type: 'GET_SETTINGS' }, (settings) => {
  apiUrlInput.value = settings.apiUrl || 'http://localhost:8080';
});

// Validate URL: allows localhost/127.0.0.1 over HTTP, requires HTTPS for all other hosts
function validateApiUrl(raw) {
  if (!raw) return { ok: false, message: 'La URL no puede estar vacía.' };

  let parsed;
  try {
    parsed = new URL(raw);
  } catch {
    return { ok: false, message: 'URL no válida. Ejemplo: https://api.cardex.eu' };
  }

  const isLocal = parsed.hostname === 'localhost' || parsed.hostname === '127.0.0.1';

  if (!isLocal && parsed.protocol !== 'https:') {
    return { ok: false, message: 'Se requiere HTTPS para hosts remotos por razones de seguridad.' };
  }

  if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
    return { ok: false, message: 'Solo se permiten protocolos http y https.' };
  }

  return { ok: true };
}

// Show/clear validation error
function setError(msg) {
  if (!urlError) return;
  if (msg) {
    urlError.textContent = msg;
    urlError.style.display = 'block';
    apiUrlInput.style.borderColor = '#ef4444';
  } else {
    urlError.textContent = '';
    urlError.style.display = 'none';
    apiUrlInput.style.borderColor = '';
  }
}

// Save settings
btnSave.addEventListener('click', () => {
  const apiUrl = apiUrlInput.value.trim().replace(/\/$/, '');
  const validation = validateApiUrl(apiUrl);

  if (!validation.ok) {
    setError(validation.message);
    apiUrlInput.focus();
    return;
  }

  setError(null);
  btnSave.disabled = true;
  btnSave.textContent = 'Guardando…';

  const timeout = setTimeout(() => {
    btnSave.disabled = false;
    btnSave.textContent = 'Guardar configuración';
    setError('Error al guardar. Recarga la extensión e inténtalo de nuevo.');
  }, 5000);

  chrome.runtime.sendMessage({
    type: 'SAVE_SETTINGS',
    payload: { apiUrl },
  }, () => {
    clearTimeout(timeout);
    btnSave.disabled = false;
    btnSave.textContent = 'Guardar configuración';
    if (toast) {
      toast.classList.add('visible');
      setTimeout(() => toast.classList.remove('visible'), 2500);
    }
  });
});

// Clear error on input change
apiUrlInput.addEventListener('input', () => setError(null));
