from __future__ import annotations

import csv
import io
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import FileResponse, StreamingResponse

from .state import StateStore

if TYPE_CHECKING:
    from .influx_writer import InfluxWriter

# Zielverzeichnis: ~/Documents/WXSMART/
RECORD_DIR = Path.home() / "Documents" / "WXSMART"

# Aktive Aufzeichnungen pro Tool: { "Tool1": {"writer": ..., "fh": ..., "path": ..., "lock": ...} }
_active_recordings: dict[str, dict] = {}
_rec_lock = threading.Lock()

CSV_COLUMNS = ["time", "tool", "tip_id", "tip_serial", "tool_serial",
               "power_w", "temperature_c", "counter_time_s", "operating_hours_total"]


def _snapshot_to_row(tool_key: str, snap: dict) -> list:
    """Extrahiert eine CSV-Zeile aus dem aktuellen AppState-Snapshot."""
    tool = (snap.get("tools") or {}).get(tool_key, {})
    tip_key = tool_key.replace("Tool", "Tip")
    tip = (snap.get("tips") or {}).get(tip_key, {})
    return [
        datetime.now(tz=timezone.utc).isoformat(),
        tool_key,
        tip.get("id") or "",
        tip.get("serial_number") or "",
        tool.get("serial_number") or "",
        tool.get("power_w") if tool.get("power_w") is not None else "",
        tool.get("temperature_c") if tool.get("temperature_c") is not None else "",
        tool.get("counter_time") or "",
        tool.get("operating_hours_total") or "",
    ]


def create_api_router(state_store: StateStore, influx_writer: "InfluxWriter | None" = None) -> APIRouter:
    router = APIRouter()

    @router.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @router.get("/api/state")
    def get_state() -> dict:
        return state_store.snapshot()

    @router.get("/api/tools")
    def get_tools() -> dict:
        return state_store.snapshot().get("tools", {})

    @router.get("/api/station")
    def get_station() -> dict:
        return state_store.snapshot().get("station", {})

    @router.get("/api/export/csv")
    def export_csv(
        start: str = Query(
            default=None,
            description="Start-Zeitpunkt (ISO8601, z.B. 2026-03-29T10:00:00Z). Standard: letzte Stunde.",
        ),
        stop: str = Query(
            default=None,
            description="End-Zeitpunkt (ISO8601). Standard: jetzt.",
        ),
        tool: str = Query(
            default="both",
            description="Welches Tool: Tool1 | Tool2 | both",
        ),
    ) -> StreamingResponse:
        """Exportiert Lötdaten als CSV-Datei aus InfluxDB."""
        if influx_writer is None or not influx_writer.enabled:
            raise HTTPException(
                status_code=503,
                detail="InfluxDB nicht konfiguriert. INFLUX_URL in .env setzen.",
            )

        # Zeitbereich bestimmen
        now = datetime.now(tz=timezone.utc)
        try:
            t_stop = datetime.fromisoformat(stop.replace("Z", "+00:00")) if stop else now
            t_start = datetime.fromisoformat(start.replace("Z", "+00:00")) if start else t_stop - timedelta(hours=1)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"Ungültiges Zeitformat: {exc}") from exc

        # Tool-Filter
        tool_filter = ""
        if tool in ("Tool1", "Tool2"):
            tool_filter = f'|> filter(fn: (r) => r["tool"] == "{tool}")'

        flux_query = f"""
            from(bucket: "{influx_writer.settings.influx_bucket}")
              |> range(start: {t_start.strftime("%Y-%m-%dT%H:%M:%SZ")}, stop: {t_stop.strftime("%Y-%m-%dT%H:%M:%SZ")})
              |> filter(fn: (r) => r["_measurement"] == "soldering_session")
              {tool_filter}
              |> pivot(rowKey: ["_time", "tool", "tip_id", "tip_serial", "tool_serial"],
                       columnKey: ["_field"],
                       valueColumn: "_value")
              |> sort(columns: ["_time"])
        """

        try:
            query_api = influx_writer._client.query_api()  # noqa: SLF001
            tables = query_api.query(flux_query, org=influx_writer.settings.influx_org)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"InfluxDB Query-Fehler: {exc}") from exc

        # Daten in CSV umwandeln
        output = io.StringIO()
        writer = csv.writer(output)

        columns = ["time", "tool", "tip_id", "tip_serial", "tool_serial",
                   "power_w", "temperature_c", "counter_time_s", "operating_hours_total"]
        writer.writerow(columns)

        for table in tables:
            for record in table.records:
                writer.writerow([
                    record.get_time().isoformat() if record.get_time() else "",
                    record.values.get("tool", ""),
                    record.values.get("tip_id", ""),
                    record.values.get("tip_serial", ""),
                    record.values.get("tool_serial", ""),
                    record.values.get("power_w", ""),
                    record.values.get("temperature_c", ""),
                    record.values.get("counter_time_s", ""),
                    record.values.get("operating_hours_total", ""),
                ])

        filename = f"wxsmart_{t_start.strftime('%Y%m%d_%H%M')}_{t_stop.strftime('%Y%m%d_%H%M')}.csv"
        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    # ------------------------------------------------------------------
    # Lokaler Recorder  (speichert CSV direkt in ~/Documents/WXSMART/)
    # ------------------------------------------------------------------

    @router.post("/api/record/start")
    def record_start(
        tool: str = Query(default="Tool1", description="Tool1 | Tool2"),
    ) -> dict:
        """Startet eine Aufzeichnung für das angegebene Tool."""
        if tool not in ("Tool1", "Tool2"):
            raise HTTPException(status_code=422, detail="tool muss Tool1 oder Tool2 sein")

        with _rec_lock:
            if tool in _active_recordings:
                raise HTTPException(status_code=409, detail=f"{tool} läuft bereits")

            RECORD_DIR.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = RECORD_DIR / f"wxsmart_{tool}_{ts}.csv"
            fh = open(filename, "w", newline="", encoding="utf-8")  # noqa: WPS515
            writer = csv.writer(fh)
            writer.writerow(CSV_COLUMNS)

            _active_recordings[tool] = {
                "writer": writer,
                "fh": fh,
                "path": filename,
                "lock": threading.Lock(),
            }

        return {"status": "recording", "tool": tool, "filename": str(filename)}

    @router.post("/api/record/stop")
    def record_stop(
        tool: str = Query(default="Tool1", description="Tool1 | Tool2"),
    ) -> dict:
        """Stoppt die laufende Aufzeichnung und schließt die CSV-Datei."""
        with _rec_lock:
            rec = _active_recordings.pop(tool, None)

        if rec is None:
            raise HTTPException(status_code=404, detail=f"Keine aktive Aufzeichnung für {tool}")

        with rec["lock"]:
            rec["fh"].flush()
            rec["fh"].close()

        return {"status": "stopped", "tool": tool, "filename": str(rec["path"])}

    @router.get("/api/record/download")
    def record_download(
        file: str = Query(description="Absoluter Dateipfad der gespeicherten CSV"),
    ) -> FileResponse:
        """Liefert eine gespeicherte CSV-Datei zum Download."""
        path = Path(file)
        # Sicherheits-Check: nur Dateien innerhalb von ~/Documents/WXSMART/
        try:
            path.resolve().relative_to(RECORD_DIR.resolve())
        except ValueError:
            raise HTTPException(status_code=403, detail="Zugriff verweigert")
        if not path.exists():
            raise HTTPException(status_code=404, detail="Datei nicht gefunden")
        return FileResponse(
            path=path,
            media_type="text/csv",
            filename=path.name,
        )

    return router
