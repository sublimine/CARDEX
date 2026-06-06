# CARDEX — Panel de Control

Un panel que abres y ves de un vistazo el **estado** y el **PROGRESO** reales del
proyecto. Todos los números salen en vivo de la base de datos del sistema; nada
está inventado. Lo que no se puede verificar aparece como **«sin datos»**.

---

## Abrir el panel

Doble clic en:

```
dashboard\cardex_control.html
```

Se abre en el navegador. Si tienes el auto-refresco activado (ver abajo), la
página se regenera sola cada 15 minutos y el navegador la recarga sola.

> ¿Quieres verlo **ahora mismo** con los datos del segundo exacto?
> ```powershell
> powershell -ExecutionPolicy Bypass -File dashboard\open_dashboard.ps1
> ```
> Regenera el panel desde la base de datos y lo abre.

---

## Auto-refresco cada 15 minutos (en el host)

El refresco corre **en este ordenador** mediante el Programador de Tareas de
Windows. No usa el scheduler de Cowork (que corre aislado y no llega a la base
de datos local).

**Arrancar** (registra la tarea y genera el panel por primera vez):

```powershell
powershell -ExecutionPolicy Bypass -File dashboard\register_refresh.ps1
```

**Parar** (elimina la tarea; el último panel generado se queda en disco):

```powershell
powershell -ExecutionPolicy Bypass -File dashboard\unregister_refresh.ps1
```

**Comprobar el estado de la tarea**:

```powershell
Get-ScheduledTask     -TaskName 'CARDEX Dashboard Refresh'
Get-ScheduledTaskInfo -TaskName 'CARDEX Dashboard Refresh'   # último resultado y próximo disparo
```

La tarea ejecuta `python generate.py` cada 15 min, con tope de 5 min por
ejecución y sin solapamiento. Corre como tu usuario (necesita acceso a Docker).

---

## Qué muestra (de arriba abajo)

| Sección | Pregunta del dueño |
|---|---|
| **Titular + semáforo** | ¿Está sano el sistema en una frase? |
| **KPIs** | Punteros L1, coches ricos L2, dealers, portales que producen, contenedores vivos |
| **Salud del pipeline** | El recorrido de un coche, etapa a etapa, con verde/ámbar/rojo |
| **Listings por país** | El balance entre los 6 mercados (la concentración real salta a la vista) |
| **Cobertura por portal** | Cuánto extrae cada portal y dónde está el tope |
| **Gigantes en cero** | Los líderes del mercado bloqueados por el muro económico (sin proxies) |
| **Discovery de dealers** | Candidatos por país y fuente, % con web, % crawleado |
| **Colas y salud del crawler** | Profundidad de colas, identidades, proxies, circuitos, DLQ |
| **Registro de progreso** | Qué se ha completado y qué sigue (hitos del blueprint, estado en vivo) |
| **Contenedores Docker** | Qué está arriba y qué está caído |

### Cómo leer los semáforos
- 🟢 **verde** = sano / completado
- 🟡 **ámbar** = atención / parcial
- 🔴 **rojo** = caído / crítico / inerte
- ⚪ **gris** = sin datos o pendiente (futuro)

---

## De dónde salen los datos (todo en vivo, solo lectura)

| Fuente | Cómo se lee | Qué aporta |
|---|---|---|
| PostgreSQL (`cardex-pg`) | `docker exec … psql` | `vehicle_index`, `vehicle_events`, `vehicles`, `discovery_candidates`, `entities` |
| Redis (`cardex-redis`) | `docker exec … redis-cli` | profundidad de las colas/streams (el puente L1→L2) |
| SQLite (`scrapers/engine.db`) | lectura directa (modo solo-lectura) | `work_queue`, identidades, proxies, circuitos, DLQ |
| Docker | `docker ps` | contenedores arriba/abajo y su salud |

No se guardan secretos en el código: la contraseña de Redis y las credenciales
de PostgreSQL se descubren del propio contenedor en marcha (o de variables de
entorno `CARDEX_REDIS_PASSWORD` / `CARDEX_PG_USER` / `CARDEX_PG_DB`).

---

## ¿Por qué un panel HTML propio y no Grafana?

Grafana y Prometheus **están vivos**, pero hoy Prometheus solo se scrapea a sí
mismo: no hay exporters de PostgreSQL ni de Redis, así que **Grafana no ve ni un
dato de negocio**. Además, el `work_queue` y la salud del crawler viven en un
SQLite **en el host**, que Grafana (dentro de Docker) no puede leer.

Este panel resuelve eso leyendo las cuatro fuentes directamente desde el host, y
está pensado para mostrar **PROGRESO de proyecto** (auditoría, blueprint, P0,
hitos) — no solo métricas de runtime — con titulares claros para un dueño no
técnico. Grafana/Prometheus siguen disponibles como capa de ops para
diagnóstico profundo; son complementarios, no rivales.

---

## Estructura

```
dashboard/
├── generate.py            # entrypoint: recolecta → renderiza → escribe el HTML (atómico)
├── collectors.py          # lectura del estado real (PG, Redis, SQLite, Docker), cada fuente aislada
├── render.py              # renderizado HTML autocontenido (sin dependencias externas)
├── reference.py           # hechos citados del audit (gigantes, topes, hitos)
├── cardex_control.html    # SALIDA generada — el panel que abres (se regenera solo)
├── register_refresh.ps1   # arrancar auto-refresco (Programador de Tareas, cada 15 min)
├── unregister_refresh.ps1 # parar auto-refresco
├── open_dashboard.ps1     # regenerar ahora y abrir en el navegador
└── README.md
```

Solo Python 3 estándar — sin `pip install`. El HTML no carga nada de internet
(CSS embebido), así que funciona offline y por doble clic.
