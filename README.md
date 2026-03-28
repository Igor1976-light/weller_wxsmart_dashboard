# WXsmart Workspace

Dieses Projekt dient zur Erfassung und grafischen Darstellung der von einer **Weller WX SMART Power Unit** gesendeten MQTT-Daten.
Der aktuelle Stand umfasst einen bestehenden CLI-Monitor sowie ein Browser-Dashboard, das die empfangenen Live-Daten grafisch aufbereitet.

## Zweck

- Live-Monitoring der von der Weller WX SMART Power Unit gesendeten MQTT-Daten
- grafische Anzeige im Browser für Temperatur, Power, Counter, Status und weitere Stationsdaten
- technische Analyse und Fehlersuche bei MQTT-Kommunikation und Stationstelemetrie

## Unterstützte Plattformen

Die Software ist grundsätzlich für diese Plattformen geeignet:

- **macOS**
- **Linux**
- **Windows**

Voraussetzung ist jeweils eine Python-Umgebung sowie ein erreichbarer MQTT-Broker.
Das Browser-Dashboard selbst ist plattformunabhängig und läuft im Webbrowser.

## Voraussetzungen

Für den Betrieb werden zusätzlich benötigt:

- **Python 3.11+** (empfohlen: virtuelle Umgebung)
- **MQTT-Broker** mit passender Konfiguration
  - z. B. **Mosquitto**
  - bei Nutzung der WX SMART typischerweise mit **WebSocket-Unterstützung** auf dem konfigurierten Port
- **Python-Pakete** aus `requirements.txt`
- optional ein moderner Browser für das Live-Dashboard

Typischer Aufbau:

- Weller WX SMART Power Unit sendet MQTT-Daten
- MQTT-Broker nimmt die Daten entgegen
- dieses Projekt liest die Daten ein und stellt sie im Browser dar

## Projektaufbau

Dieses Repository enthält aktuell zwei Ebenen:

- `wxsmart.py`: bestehender CLI-Monitor (laufender Produktions-/Testpfad)
- `app/`: neuer Startpunkt für das kommende Browser-Dashboard (FastAPI + MQTT Ingest)

## Struktur

- `app/main.py` – FastAPI App + Startup/Shutdown
- `app/config.py` – Umgebungsvariablen
- `app/state.py` – In-Memory Zustand (`Tool1`, `Tool2`, `station`)
- `app/mqtt_service.py` – MQTT Subscriber und Topic-Ingest
- `app/api.py` – REST-Endpunkte (`/api/health`, `/api/state`, `/api/tools`, `/api/station`)
- `app/static/index.html` – erstes Live-Dashboard im Browser
- `scripts/run_dashboard.sh` – lokaler Starthelfer
- `todo.md` – Roadmap für das vollständige Live-Dashboard

## Schnellstart (Dashboard-API)

1. Abhängigkeiten installieren:

```zsh
cd /pfad/zu/wxsmart
source .venv/bin/activate
pip install -r requirements.txt
```

Optional: Umgebungsvariablen vorbereiten:

```zsh
cp .env.example .env
```

Danach Werte in `.env` anpassen (z. B. `MQTT_HOST`, `MQTT_TOPIC`).

2. API starten:

```zsh
cd /pfad/zu/wxsmart
source .venv/bin/activate
MQTT_HOST=<broker-ip-oder-hostname> MQTT_PORT=9001 uvicorn app.main:app --host 127.0.0.1 --port 8000
```

3. Testen:

- `http://127.0.0.1:8000/api/health`
- `http://127.0.0.1:8000/api/state`
- `http://127.0.0.1:8000/` (Live-Dashboard)

## Wichtige ENV-Variablen

- `MQTT_HOST` (Default: `localhost`)
- `MQTT_PORT` (Default: `9001`)
- `MQTT_TOPIC` (Default: `WXSMART/#`, optional spezifischer Filter: `WXSMART/<seriennummer>/#`)
- `MQTT_TRANSPORT` (Default: `websockets`)
- `APP_HOST` (Default: `127.0.0.1`)
- `APP_PORT` (Default: `8000`)

## Hinweis

`wxsmart.py` ist der CLI-Monitor für den direkten MQTT-Betrieb. Die `app/`-Struktur enthält die API- und Dashboard-Komponenten für den Browserbetrieb.

### Live-Update ohne Reload

- Das Dashboard nutzt `ws://127.0.0.1:8000/ws/live` (bzw. `wss://` unter HTTPS).
- Beim Verbinden wird automatisch ein Snapshot angezeigt; danach kommen Änderungen live nach.
- Bei Verbindungsabbruch versucht die Seite automatisch einen Reconnect.
