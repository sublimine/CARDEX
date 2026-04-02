// CARDEX Intelligence — Settings Script

const apiUrlInput = document.getElementById('api-url');
const btnSave = document.getElementById('btn-save');
const toast = document.getElementById('toast');

// Load existing settings
chrome.runtime.sendMessage({ type: 'GET_SETTINGS' }, (settings) => {
  apiUrlInput.value = settings.apiUrl || 'http://localhost:8080';
});

// Save settings
btnSave.addEventListener('click', () => {
  const apiUrl = apiUrlInput.value.trim().replace(/\/$/, '');

  if (!apiUrl) {
    apiUrlInput.focus();
    return;
  }

  btnSave.disabled = true;
  btnSave.textContent = 'Guardando…';

  chrome.runtime.sendMessage({
    type: 'SAVE_SETTINGS',
    payload: { apiUrl },
  }, () => {
    btnSave.disabled = false;
    btnSave.textContent = 'Guardar configuración';
    toast.classList.add('visible');
    setTimeout(() => toast.classList.remove('visible'), 2500);
  });
});
