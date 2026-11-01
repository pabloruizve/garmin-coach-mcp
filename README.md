# Garmin Coach MCP

Servidor MCP que conecta Garmin Connect con Claude y ChatGPT — 137 herramientas, datos en tiempo real · by AlejandrLucena

---

## Puesta en marcha (Docker / Easypanel)

El servidor es una app Python que se despliega con el `Dockerfile` del repo. Sirve igual en Easypanel, en cualquier VPS con Docker o en local.

### Lo que necesitas antes de empezar
- Tu cuenta de **Garmin Connect** (la del reloj) y acceso a su código MFA si lo tienes activo.
- Un **fork** de este repo en tu cuenta de GitHub: <https://github.com/Alejandrlucena/garmin-coach-mcp> → **Fork**.
- Un servidor con Docker (en Easypanel, un VPS tuyo).
- Una **IA con soporte de conectores MCP**: Claude, ChatGPT u otra compatible.

### Paso 1 · Crea la app desde tu fork

1. En Easypanel, crea una **App** nueva con origen **GitHub** y elige tu fork.
2. Método de build: **Dockerfile** (el del repo).
3. Puerto interno: **8000**.
4. Añade un **volumen** montado en **`/data`**. Es imprescindible: ahí se guardan los tokens de Garmin, la contraseña del panel y los ajustes. Sin volumen se pierden en cada reinicio.
5. Asigna un **dominio** a la app (con HTTPS) y despliega.

### Paso 2 · Configura todo desde el panel

Abre tu dominio. Verás un **panel** con una lista de pasos:

1. **Conectar Garmin** → email + contraseña + el código MFA que te llega al correo.
2. **Protección con contraseña** → eliges una contraseña para que solo tú puedas abrir el panel.

Cada paso se pone en **verde ✅** cuando está hecho. El panel se refresca solo cada pocos segundos.

### Paso 3 · Conéctalo a tu IA (Claude, ChatGPT, etc.)

Funciona con cualquier IA que acepte conectores MCP.

1. En el panel, pulsa **Copiar URL del conector** (es `https://tu-dominio/mcp`).
2. En tu IA, ve a la sección de conectores/MCP y añade un conector personalizado:
   - **Claude**: Settings → **Connectors** → **Add custom connector**.
   - **ChatGPT**: Settings → **Connectors** (MCP) → añadir servidor.
   - **Otras**: busca "MCP" o "conector personalizado" y pega la URL.
3. Pega la URL → guarda.
4. Listo. Ya puedes pedirle tus métricas de Garmin.

### Actualizar el servidor

Cuando se mergee un cambio en tu fork, vuelve a **desplegar** la app en Easypanel. Las herramientas nuevas aparecen en tu IA después de refrescar la lista de herramientas del conector.

---

### ¿Necesitas re-loguearte en el futuro?

Cuando Garmin caduque tu sesión (raro, ~1 año) o cambies de contraseña en Garmin:
- Abre tu panel (te pedirá tu contraseña), pulsa **Re-loguear Garmin** y repite el Paso 2.1. Desde el móvil, en 1 minuto.

---

## Cómo se ve

### El recorrido completo

```
①  Fork en GitHub  +  App en Easypanel (Dockerfile, puerto 8000, volumen /data)
        │
②  Abrir la URL  ───────────►   aparece el Panel de estado
        │
③  [Conectar Garmin]            email · contraseña · código MFA
        │
④  [Protección]                 elegir contraseña (con ojito 👁)
        │
⑤  Copiar URL /mcp  ────────►   pegar en Claude / ChatGPT
        │
      ✅  Listo
```

### El panel (`/`)

```
Garmin Coach MCP · Panel de estado
══════════════════════════════════

Estado del setup
  ✅  Servidor desplegado          Activo y respondiendo
  ✅  Garmin conectado             Tokens válidos, caché al día
  ✅  ⚠️  Protección con contraseña  Activada / [Activar]
  ✅  IA conectada / durmiendo / lista  Según uso

Acciones
  [ Re-loguear Garmin ]
  [ Copiar URL del conector ]
  [ Bloquear sesión ]
```

### Pantalla de acceso (cuando hay contraseña)

```
Panel protegido
───────────────
Introduce tu contraseña para acceder.

  Contraseña:  [ ••••••••••          👁 ]

  [ Entrar ]

  ▸ ¿No recuerdas la contraseña?
```

### Asistente de Garmin (3 pasos)

```
 Paso 1 ─ Email + contraseña      ●○○
 Paso 2 ─ Código MFA del Gmail    ○●○
 Paso 3 ─ Confirmación            ○○●
```

---

## El panel y los asistentes web

Todo se hace desde el navegador, sin terminal. El servidor sirve un panel en `/` con asistentes guiados:

- **`/` (panel de estado)**: muestra cada paso del setup (servidor, Garmin, protección, IA) en verde ✅ o pendiente ⚠️, con su botón de acción.
- **Conectar Garmin**: reemplaza a `login_once.py`. Email + contraseña + MFA, todo web, en 3 pasos. Los tokens se guardan en el volumen (`/data/garmin`).
- **Protección con contraseña**: eliges tu propia contraseña (o generas una al azar). El servidor la guarda en un archivo del volumen que lee en vivo → los cambios de contraseña son **instantáneos, sin reiniciar el servidor** y sobreviven a reinicios mientras el volumen exista.

### Detalles del acceso por contraseña

- **Campo con ojito 👁**: la contraseña va oculta por defecto; pulsa el ojo para mostrarla u ocultarla.
- **Sesión deslizante**: tras entrar, el navegador te recuerda 365 días y renueva el plazo en cada visita (como Instagram/X/TikTok). No te pide la contraseña una y otra vez.
- **Bloquear sesión**: botón en el panel que borra la cookie; la próxima visita vuelve a pedir contraseña (útil en equipos compartidos).
- **Cambiar contraseña**: botón **Cambiar** en la fila de Protección. Aplica al instante.
- **¿Olvidaste la contraseña?**: si la pierdes, está en el fichero `admin_token` de la carpeta de tokens (`/data/garmin/admin_token`) o, si ese fichero no existe, en la variable `ADMIN_TOKEN` de tu app.

---

## Flujo técnico

```
Garmin Connect → garminconnect (Python) → server.py (Docker) → Claude / Web / Móvil
```

---

## Endpoints HTTP

| Ruta | Descripción |
|------|-------------|
| `GET /` | Panel de estado y configuración (pide contraseña si está protegido) |
| `GET /lock` | Cierra la sesión del panel (borra la cookie) |
| `GET /login` | Wizard web para conectar / re-loguear en Garmin |
| `POST /login/submit` · `GET /login/wait` · `GET/POST /login/mfa` · `GET /login/result` | Pasos internos del wizard (envío de credenciales, espera, código MFA, resultado) |
| `GET/POST /setup/proteccion` | Asistente para poner / cambiar la contraseña del panel |
| `GET /health` | Estado del servidor y del caché |
| `GET /dashboard/rows` · `GET /dashboard/deploy-status` | Fragmentos que el panel refresca solo: filas de estado y estado del despliegue |
| `GET /activities?limit=30` | Lista de actividades recientes (JSON) con CORS |
| `GET /download/{activity_id}` | Descarga el .zip/.fit de una actividad con CORS |
| `GET /config` · `POST /config` | Configuración web persistida (solo clave `driveUrl`) |
| `POST /config/share` · `GET /config/share/{share_id}` | Crea / lee una configuración compartida (se guarda en disco con un ID aleatorio) |
| `GET /adj` · `DELETE /adj` | Lista todos los ajustes guardados (con uso de disco) / los borra todos |
| `GET /adj/{activity_id}` | Obtiene los ajustes guardados de distancia/ritmo/vel para una actividad |
| `POST /adj/{activity_id}` | Guarda ajustes de distancia/ritmo/vel para una actividad (persiste en el volumen) |
| `DELETE /adj/{activity_id}` | Borra los ajustes de una actividad |
| `GET /hrmax/candidates?start_date=...` | Carreras del rango con `maxHR` alto y pico sostenido calculado desde el FIT (candidatas a FCmáx; pensado para un job semanal de n8n) |
| `POST /mcp` | Endpoint MCP principal para Claude |
| `GET /debug/activities` · `GET /debug/audit` | Debug: actividades / métricas del caché |
| `GET /debug/sleep-freshness` · `GET /debug/sleep-selection` | Debug: frescura y selección del dato de sueño en el snapshot |

Todos los endpoints incluyen CORS completo (`allow_origins=["*"]`).

---

## Instalación local (solo para desarrollo)

Solo necesitas esto si vas a modificar el código. Para uso normal, sigue la «Puesta en marcha» de arriba.

```bash
git clone https://github.com/Alejandrlucena/garmin-coach-mcp.git
cd garmin-coach-mcp
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python login_once.py          # autentica y genera tokens locales
python server.py              # → http://localhost:8000
```

---

## Variables de entorno

> Con el volumen montado en `/data` no necesitas poner ninguna a mano: el panel guarda los tokens de Garmin y la contraseña en archivos del volumen. Esta tabla es de referencia.

### Alternativa a los archivos del volumen
| Variable | Descripción |
|----------|-------------|
| `GARMIN_TOKENS_JSON` | Tokens de Garmin (JSON o base64), como alternativa al fichero que crea el wizard de "Conectar Garmin". |
| `ADMIN_TOKEN` | Contraseña del panel, como alternativa al fichero que escribe el asistente "Protección con contraseña". Mientras no exista ninguna, el panel está abierto (sin contraseña); una vez existe, el panel la pide. |

### Opcionales
| Variable | Por defecto | Descripción |
|----------|-------------|-------------|
| `PORT` | `8000` | Puerto del servidor |
| `GARMIN_EMAIL` | _(vacío)_ | Email de Garmin; solo se usa si no hay tokens guardados |
| `GARMIN_TOKEN_DIR` | `~/.garminconnect` | Carpeta de tokens en local |
| `RESET_GARMIN_TOKENS` | `0` | Si `1` y hay `GARMIN_TOKENS_JSON`, sobrescribe el fichero de tokens local con esa variable al arrancar |
| `GARMIN_DISABLE_PORTED_WRITES` | _(vacío)_ | Si `1`, las tools que escriben en tu cuenta (ver «Herramientas que escriben») se registran pero devuelven error |
| `RECOVERY_MAX_FRESH_MINUTES` | `360` | Minutos tras los que el dato de recuperación del reloj se considera caducado |
| `RECOVERY_CROSS_DAY_STALE_MINUTES` | `180` | Igual, pero si el dato es de un día anterior |
| `GARMIN_TIMEZONE` | `Europe/Madrid` | Zona horaria local |
| `GARMIN_LANGUAGE` | `es` | Idioma de traducciones |
| `CACHE_MINUTES` | `30` | Minutos entre refresco de caché |
| `ACTIVITY_LIMIT` | `8` | Límite de actividades en caché |

---

## Configuración web persistente (`/config`)

El endpoint `/config` almacena la URL del Google Apps Script de Drive en el volumen (`/data/web_config.json`). Esto permite que el visualizador web sincronice su configuración automáticamente en todos los dispositivos: basta con introducir la URL del servidor una sola vez y la URL de Drive se carga sola.

- `GET /config` — devuelve `{"driveUrl": "..."}` o `{}`
- `POST /config` — acepta `{"driveUrl": "..."}` y lo persiste en disco

Solo se permite la clave `driveUrl`. No se almacena ningún dato de usuario ni credencial.

---

## Ajustes de actividad persistentes (`/adj/`)

El endpoint `/adj/{activity_id}` permite al visualizador web [garmin-laps](https://github.com/Alejandrlucena/garmin-laps) persistir ajustes de distancia, ritmo y velocidad para cada actividad. Los datos se guardan en el volumen (`/data/adj/{activity_id}.json`).

- `GET /adj/{activity_id}` — devuelve `{"dist":"12.5","pace":"4:12"}` o `{}` si no hay ajustes
- `POST /adj/{activity_id}` — acepta un JSON con los campos ajustados (`dist`, `pace`, `speed`, etc.) y lo persiste en disco

Esto permite que los ajustes sobrevivan a recargas de página y se sincronicen entre dispositivos conectados al mismo servidor.

---

## Uso con el visualizador web

El visualizador [garmin-laps](https://github.com/Alejandrlucena/garmin-laps) tiene un botón **🔌 Conector** que carga la actividad con un clic y renderiza la tabla directamente. Cada usuario configura la URL de su propio servidor en **⚙ Configurar**.

- Despliega este repo, copia la URL de tu app y pégala en **⚙**
- O arranca el servidor en local (`http://localhost:8000`) — sirve el `index.html` directamente, sin problemas de CORS
- Soporta running, ciclismo y motorsport (moto, coche, kart) — el visualizador adapta las columnas según el tipo de actividad
- Filtros de tipo en el panel: 🗂️ Todo · 🏃 Running · 🚴 Ciclismo · 🏍️ Motorsport 🏎️ (busca entre las últimas 500 actividades)
- Solo muestra actividades con datos de splits (oculta fuerza, yoga, etc.)

---

## Herramientas MCP (137)

### Snapshot y caché
`get_day_snapshot` · `get_cached_snapshot` · `get_raw_sources` · `refresh_snapshot` · `get_window_rollup`

### Actividades
`get_recent_activities` · `get_recent_activities_full` · `get_recent_activities_catalog` · `get_recent_activities_all_data` · `get_activities_paged` · `get_activities_in_range` · `get_last_activity` · `get_activity_full` · `get_activity_all_data` · `get_activity_sport_profile` · `get_activity_visible_profile` · `get_activity_splits` · `get_activity_split_summaries` · `get_activity_time_series` · `get_activity_hr_in_timezones` · `get_activity_evaluation` · `get_activity_exercise_sets` · `get_activity_gear` · `get_activity_weather` · `get_activity_types` · `get_recent_activity_sport_profiles` · `get_activity_fit_download` · `download_activity` · `upload_activity` · `get_activity_fit_messages` · `get_activity_hr_peak` · `get_activity_typed_splits` · `get_activity_self_assessment` · `set_activity_name` · `set_activity_description` · `set_activity_type` · `set_perceived_effort` · `set_activity_feel` · `add_gear_to_activity` · `remove_gear_from_activity`

### Métricas diarias
`get_stats` · `get_stats_and_body` · `get_daily_wellness` · `get_user_summary` · `get_steps_data` · `get_daily_steps` · `get_floors` · `get_all_day_stress` · `get_stress_data` · `get_heart_rates` · `get_rhr_day` · `get_body_battery` · `get_respiration_data` · `get_spo2_data` · `get_hydration_data` · `get_blood_pressure` · `get_body_composition` · `get_stats_range`

### Sueño y recuperación
`get_sleep_data` · `get_hrv_data` · `get_training_readiness` · `get_wellness_range` · `get_sleep_summary_range` · `get_hrv_trend` · `get_morning_training_readiness` · `get_recovery_time_remaining` · `get_respiration_trend`

### Entrenamiento y rendimiento
`get_training_status` · `get_max_metrics` · `get_endurance_score` · `get_hill_score` · `get_race_predictions` · `get_personal_records` · `get_progress_summary` · `get_primary_device_info` · `get_fitness_age` · `get_training_effect` · `get_lactate_threshold` · `get_heart_rate_zones` · `get_vo2max_trend` · `get_training_load_trend` · `get_training_load_balance` · `get_running_tolerance_trend` · `get_weekly_intensity_minutes`

### Dispositivos y equipamiento
`get_devices` · `get_device_settings` · `get_device_last_used` · `get_device_alarms` · `get_gear` · `get_gear_defaults` · `get_gear_stats` · `set_gear_default`

### Peso y salud
`get_weigh_ins` · `get_daily_weigh_ins` · `add_weigh_in` · `delete_weigh_in` · `delete_weigh_ins`

### Retos y badges
`get_goals` · `get_earned_badges` · `get_available_badge_challenges` · `get_badge_challenges` · `get_adhoc_challenges` · `get_inprogress_virtual_challenges` · `get_non_completed_badge_challenges`

### Workouts y planes
`get_workout_library` · `get_workout_detail` · `get_todays_workout` · `get_scheduled_workouts` · `schedule_workout` · `unschedule_workout` · `get_training_plans` · `get_training_plan_detail` · `get_workout_compact` · `get_garmin_coach_workouts` · `get_calendar_range` · `get_calendar_events` · `preview_running_workout` · `create_running_workout` · `update_running_workout` · `delete_workout` · `delete_workouts` · `schedule_workouts` · `unschedule_workouts` · `reschedule_workout`

### Nutrición
`get_nutrition_log`

### Perfil de usuario
`get_user_profile_info`

### Análisis compacto (datos ya calculados, sin cargar la actividad entera)
- `get_time_in_zones`: tiempo en tus 3 zonas de FC (por defecto 140/165) en un rango, con comparación contra la distribución objetivo.
- `get_weekly_summary`: km, minutos, carga, sesiones duras, descansos y planificado vs. ejecutado por semana (lunes–domingo).
- `get_cardiac_drift`: deriva cardiaca (ritmo/FC) de una sesión, 1.ª mitad frente a 2.ª.
- `get_comparable_runs`: evolución de ritmo y FC en carreras comparables (misma franja de distancia).
- `get_recovery_hr`: FC de recuperación (caída de ppm a los 2 min) de hasta 10 actividades por ID. Con `include_end_hr` añade `last_lap_avg_hr`, `end_hr_reliable` (última vuelta ≤ 30 s) y `hr_at_2min` (FC final − caída; `null` si no es fiable).
- `get_recovery_hr_trend`: lo mismo para un rango de fechas, de más antigua a más reciente, con la media (máx. 60 actividades).

### Herramientas que escriben en tu cuenta de Garmin
`set_activity_name` · `set_activity_description` · `set_activity_type` · `set_perceived_effort` · `set_activity_feel` · `add_gear_to_activity` · `remove_gear_from_activity` · `schedule_workout` · `unschedule_workout` · `schedule_workouts` · `unschedule_workouts` · `reschedule_workout` · `create_running_workout` · `update_running_workout` · `delete_workout` · `delete_workouts` · `upload_activity` · `add_weigh_in` · `delete_weigh_in` · `delete_weigh_ins` · `set_gear_default`

Con `GARMIN_DISABLE_PORTED_WRITES=1` se desactivan `set_activity_*`, `set_perceived_effort`, `set_activity_feel`, `add_gear_to_activity`, `remove_gear_from_activity`, `schedule_workouts`, `unschedule_workouts`, `delete_workouts` y `reschedule_workout`. Las demás de esta lista no están cubiertas por ese interruptor.

### Hybrid Coach (Claude-native)
`get_hybrid_user_briefing` · `get_hybrid_coach_snapshot` · `get_hybrid_coach_decision` · `get_hybrid_recent_overview` · `get_hybrid_nutrition_briefing`

---

## Tests

```bash
pip install -r requirements.txt pytest
python -m pytest tests -q      # sin red: usan una API de Garmin simulada
```

## Archivos

| Archivo | Descripción |
|---------|-------------|
| `server.py` | Servidor principal — tools MCP + endpoints HTTP |
| `tests/` | Tests con `pytest` y una API simulada (herramientas de análisis, portadas y FC de recuperación) |
| `login_once.py` | Script para autenticar y generar tokens locales |
| `requirements.txt` | Dependencias Python |
| `Dockerfile` | Imagen para desplegar (Easypanel, Docker, VPS) |
| `.env.example` | Variables de entorno de ejemplo |

