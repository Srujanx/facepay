"""
GET /gtfs/route-status — cached GTFS route display data for the terminal.
Fetches DRT static feed from GTFS_FEED_URL, parses routes/trips/stop_times in memory (zipfile).
Cache 30s; if feed unreachable return stale up to 5 min; older than 5 min return empty.
"""
import csv
import io
import os
import time
import zipfile
from datetime import datetime
from typing import Any, Optional

import requests
from fastapi import APIRouter, Query

router = APIRouter()

GTFS_FEED_URL = os.getenv("GTFS_FEED_URL", "")
TERMINAL_STOP_ID = os.getenv("TERMINAL_STOP_ID", "")
CACHE_TTL_SEC = 30
CACHE_STALE_MAX_SEC = 5 * 60  # 5 minutes

# In-memory cache: { route_id: { "data": {...}, "cached_at": float } }
_gtfs_cache: dict[str, dict[str, Any]] = {}


def _parse_csv(content: bytes) -> list[dict[str, str]]:
    """Parse GTFS CSV (with header) from bytes. Returns list of row dicts."""
    text = content.decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    return list(reader)


def _fetch_and_parse_gtfs(route_id: str, stop_id: str) -> Optional[dict[str, Any]]:
    """
    Fetch zip from GTFS_FEED_URL, parse routes.txt, trips.txt, stop_times.txt in memory.
    Returns dict with route_number, headsign, delay_seconds, next_departure, alerts, current_trip_id.
    Returns None on fetch or parse error.
    """
    if not GTFS_FEED_URL:
        return None
    try:
        resp = requests.get(GTFS_FEED_URL, timeout=15)
        resp.raise_for_status()
    except Exception:
        return None

    try:
        zip_buf = io.BytesIO(resp.content)
        with zipfile.ZipFile(zip_buf, "r") as zf:
            # routes.txt
            if "routes.txt" not in zf.namelist():
                return None
            routes = _parse_csv(zf.read("routes.txt"))
            route_row = None
            for r in routes:
                if r.get("route_short_name") == route_id or r.get("route_id") == route_id:
                    route_row = r
                    break
            if not route_row:
                return None
            internal_route_id = route_row.get("route_id", route_id)
            route_number = route_row.get("route_short_name", route_id)

            # trips.txt
            if "trips.txt" not in zf.namelist():
                return {"route_number": route_number, "headsign": "", "delay_seconds": 0, "next_departure": "", "alerts": [], "current_trip_id": ""}
            trips = _parse_csv(zf.read("trips.txt"))
            route_trips = [t for t in trips if t.get("route_id") == internal_route_id]
            if not route_trips:
                return {"route_number": route_number, "headsign": "", "delay_seconds": 0, "next_departure": "", "alerts": [], "current_trip_id": ""}
            trip_ids = [t.get("trip_id") for t in route_trips if t.get("trip_id")]
            headsign = route_trips[0].get("trip_headsign", "") if route_trips else ""

            # stop_times.txt — next departure at stop_id for these trips
            next_departure = ""
            current_trip_id = ""
            current_trip_id = trip_ids[0] if trip_ids else ""
            next_departure = ""
            if trip_ids and stop_id and "stop_times.txt" in zf.namelist():
                stop_times = _parse_csv(zf.read("stop_times.txt"))
                relevant = [st for st in stop_times if st.get("trip_id") in trip_ids and st.get("stop_id") == stop_id]
                if relevant:
                    now_dt = datetime.now()
                    now_minutes = now_dt.hour * 60 + now_dt.minute
                    best = None
                    best_minutes = None
                    for st in relevant:
                        dep = st.get("departure_time", "")
                        if not dep:
                            continue
                        parts = dep.split(":")
                        if len(parts) >= 2:
                            try:
                                h, m = int(parts[0]), int(parts[1])
                                if h >= 24:
                                    h -= 24
                                dep_minutes = h * 60 + m
                                if dep_minutes >= now_minutes and (best_minutes is None or dep_minutes < best_minutes):
                                    best = st
                                    best_minutes = dep_minutes
                            except ValueError:
                                continue
                    if best:
                        current_trip_id = best.get("trip_id", "")
                        dep = best.get("departure_time", "")
                        if dep and ":" in dep:
                            next_departure = dep[:5] if len(dep) >= 5 else dep

            return {
                "route_number": route_number,
                "headsign": headsign,
                "delay_seconds": 0,
                "next_departure": next_departure,
                "alerts": [],
                "current_trip_id": current_trip_id,
            }
    except Exception:
        return None


@router.get("/route-status")
def route_status(
    route_id: str = Query(..., description="Route number e.g. 110"),
):
    """
    Return cached GTFS route display data. Cache 30s; stale up to 5 min on fetch failure; empty if cache > 5 min.
    """
    stop_id = TERMINAL_STOP_ID
    now = time.time()
    cached = _gtfs_cache.get(route_id)

    # Fresh cache
    if cached and (now - cached["cached_at"]) < CACHE_TTL_SEC:
        return cached["data"]

    # Try fetch
    data = _fetch_and_parse_gtfs(route_id, stop_id)
    if data is not None:
        _gtfs_cache[route_id] = {"data": data, "cached_at": now}
        return data

    # Fetch failed — serve stale if within 5 min
    if cached and (now - cached["cached_at"]) < CACHE_STALE_MAX_SEC:
        return cached["data"]

    # No cache or too old — return empty so frontend hides panel
    return {
        "route_number": "",
        "headsign": "",
        "delay_seconds": 0,
        "next_departure": "",
        "alerts": [],
        "current_trip_id": "",
    }
