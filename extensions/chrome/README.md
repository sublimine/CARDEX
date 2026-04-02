# CARDEX Intelligence — Extensión de Navegador

Overlay de inteligencia de mercado en tiempo real sobre los principales portales de coches de Europa.

## Qué hace

Cuando navegas por un listing en cualquier portal soportado, la extensión muestra automáticamente:

- **Posición de precio** — Si el coche está barato, en precio justo o caro vs el mercado
- **Mediana de mercado** — Precio P25, mediana y P75 para ese make/model/año/país
- **Demanda (Market Days' Supply)** — Cuántos días de stock hay disponibles. Menos días = más demanda
- **Tiempo de venta estimado** — Cuántos días tardará este coche en venderse al precio actual
- **Alertas de arbitraje** — Si el mismo coche está disponible >15% más barato en otro país

## Portales soportados

| País | Portales |
|---|---|
| 🇪🇸 España | AutoScout24, Coches.net, Milanuncios, Autocasion, Wallapop |
| 🇩🇪 Alemania | AutoScout24, mobile.de |
| 🇫🇷 Francia | AutoScout24, LeBonCoin, La Centrale |
| 🇳🇱 Países Bajos | AutoScout24, Marktplaats, Gaspedaal |
| 🇧🇪 Bélgica | AutoScout24, Tweedehands |
| 🇨🇭 Suiza | AutoScout24, Comparis |

## Instalación (modo desarrollador)

1. Clona el repositorio CARDEX y asegúrate de que el servidor API está corriendo (`make dev`)
2. En Chrome, navega a `chrome://extensions/`
3. Activa **"Modo desarrollador"** (toggle superior derecha)
4. Haz click en **"Cargar extensión sin empaquetar"**
5. Selecciona la carpeta `extensions/chrome/`
6. La extensión aparece en la barra de extensiones
7. Click en el icono ⬡ → **Configurar** → introduce la URL de tu servidor CARDEX

## Configuración

Por defecto apunta a `http://localhost:8080` (servidor local con `make dev`).

Para usar con un servidor en producción: cambia la URL en la configuración de la extensión.

## Endpoint utilizado

```
GET /api/v1/ext/market-check?make=BMW&model=320d&year=2021&price_eur=28000&mileage_km=45000&country=ES
```

Endpoint público sin autenticación (rate limited: 20 req/min por IP).

## Privacidad

- La extensión NO recoge datos personales
- Solo envía: make, model, año, precio, km y país al servidor CARDEX
- No hay tracking, analytics ni terceros
- Todo se procesa en tu servidor CARDEX (local o autohosteado)
