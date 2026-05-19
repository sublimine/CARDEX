"""
Stealth JS constants — para Chromium fallback en pw_base.py.

Camoufox (Firefox) no necesita estos patches — los aplica a nivel C++.
Este módulo centraliza las constantes JS para el fallback Chromium de pw_base.py.
Importado desde pw_base.py en lugar de inline para mantener el código limpio.

Señales cubiertas (10):
  1.  navigator.webdriver — delete + defineProperty
  2.  navigator.plugins — PluginArray con 3 plugins PDF reales
  3.  chrome.runtime — objeto completo con connect/sendMessage/id
  4.  permissions.query — notifications devuelve estado real
  5.  WebGL vendor/renderer — Intel Inc. / Intel Iris
  6.  iframe.contentWindow.webdriver — cross-frame detection
  7.  hardwareConcurrency / deviceMemory — 8/8
  8.  window.outerWidth/outerHeight — innerWidth+17 / innerHeight+74
  9.  Battery API — level=0.95, charging=true
  10. navigator.connection — undefined (oculta NetworkInfo)
"""

# Extraído de pw_base.py — single source of truth para el JS de stealth
CHROMIUM_STEALTH_JS: str = """
(function() {
  Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
  try { delete navigator.__proto__.webdriver; } catch(_) {}

  function fakePlugin(name) {
    const p = Object.create(Plugin.prototype);
    Object.defineProperties(p, {
      name:        {value: name,                  enumerable: true},
      filename:    {value: 'internal-pdf-viewer', enumerable: true},
      description: {value: 'Portable Document Format', enumerable: true},
      length:      {value: 0,                     enumerable: true},
    });
    return p;
  }
  Object.defineProperty(navigator, 'plugins', {
    get: () => {
      const arr = [fakePlugin('PDF Viewer'), fakePlugin('Chrome PDF Viewer'), fakePlugin('Chromium PDF Viewer')];
      arr.__proto__ = PluginArray.prototype;
      return arr;
    },
  });

  Object.defineProperty(navigator, 'languages',           {get: () => ['de-DE','de','en-US','en']});
  Object.defineProperty(navigator, 'platform',            {get: () => 'Win32'});
  Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});
  Object.defineProperty(navigator, 'deviceMemory',        {get: () => 8});

  window.chrome = {
    runtime: {connect:()=>{}, sendMessage:()=>{}, onMessage:{addListener:()=>{}}, id: undefined},
    loadTimes: ()=>({}), csi: ()=>({}), app: {},
  };

  const _origQuery = window.navigator.permissions.query.bind(navigator.permissions);
  window.navigator.permissions.query = (p) =>
    p.name === 'notifications'
      ? Promise.resolve({state: Notification.permission, onchange: null})
      : _origQuery(p);

  const _getParam = WebGLRenderingContext.prototype.getParameter;
  WebGLRenderingContext.prototype.getParameter = function(p) {
    if (p === 37445) return 'Intel Inc.';
    if (p === 37446) return 'Intel Iris OpenGL Engine';
    return _getParam.call(this, p);
  };

  const _origCW = Object.getOwnPropertyDescriptor(HTMLIFrameElement.prototype, 'contentWindow');
  Object.defineProperty(HTMLIFrameElement.prototype, 'contentWindow', {
    get: function() {
      const win = _origCW.get.call(this);
      if (win && win.navigator.webdriver) Object.defineProperty(win.navigator, 'webdriver', {get: () => undefined});
      return win;
    },
  });

  Object.defineProperty(window, 'outerWidth',  {get: () => window.innerWidth  + 17});
  Object.defineProperty(window, 'outerHeight', {get: () => window.innerHeight + 74});

  if (navigator.getBattery) {
    const _orig = navigator.getBattery.bind(navigator);
    navigator.getBattery = () => _orig().then(b => {
      Object.defineProperty(b, 'level',    {get: () => 0.95});
      Object.defineProperty(b, 'charging', {get: () => true});
      return b;
    }).catch(() => Promise.resolve({level:0.95, charging:true, chargingTime:0, dischargingTime:Infinity}));
  }

  try { Object.defineProperty(navigator, 'connection', {get: () => undefined}); } catch(_) {}
})();
"""
