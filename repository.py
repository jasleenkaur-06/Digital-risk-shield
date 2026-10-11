"""Storage layer. Two interchangeable classes with the same methods:

* SupabaseRepository : real, persistent storage (Supabase PostgreSQL).
* MemoryRepository   : DEMO MODE only. Data lives in RAM and is lost on restart.

Credentials come from environment variables and are only ever used on the server.
"""
import os
import uuid
from datetime import datetime, timezone


class DatabaseError(Exception):
    """Raised when the database cannot be reached or rejects a request."""


def _now():
    return datetime.now(timezone.utc).isoformat()


def _stats(rows):
    """Dashboard counters from a list of scan rows (each has scan_type and risk_level)."""
    return {"total_scans": len(rows),
            "high_risk": sum(r["risk_level"] in ("High", "Critical") for r in rows),
            "social_scans": sum(r["scan_type"] == "social" for r in rows),
            "app_scans": sum(r["scan_type"] == "app" for r in rows)}


def _profile(brand, assets):
    """Turn a brand row + its asset rows into one dict the rest of the app uses."""
    mine = [a for a in assets if a["brand_id"] == brand["id"]]
    return {"id": brand["id"], "name": brand["name"], "official_website": brand.get("official_website") or "",
            "socials": [a["official_identifier"] for a in mine if a["asset_type"] == "social"],
            "apps": [{"name": a["official_identifier"], "publisher": a.get("official_publisher") or ""}
                     for a in mine if a["asset_type"] == "app"]}


def _asset_rows(brand_id, socials, apps):
    rows = [{"brand_id": brand_id, "asset_type": "social", "official_identifier": s.strip().lstrip("@")}
            for s in socials if s.strip()]
    rows += [{"brand_id": brand_id, "asset_type": "app", "official_identifier": a["name"].strip(),
              "official_publisher": (a.get("publisher") or "").strip() or None}
             for a in apps if a.get("name", "").strip()]
    return rows


class MemoryRepository:
    mode = "demo"

    def __init__(self):
        self.brands, self.assets, self.scans = [], [], []

    def list_profiles(self):
        return [_profile(b, self.assets) for b in self.brands]

    def save_profile(self, name, website, socials, apps, brand_id=None):
        brand = next((b for b in self.brands if b["id"] == brand_id), None)
        if brand:
            brand.update(name=name, official_website=website)
            self.assets = [a for a in self.assets if a["brand_id"] != brand["id"]]
        else:
            brand = {"id": str(uuid.uuid4()), "name": name, "official_website": website, "created_at": _now()}
            self.brands.append(brand)
        self.assets += [{"id": str(uuid.uuid4()), "created_at": _now(), **r}
                        for r in _asset_rows(brand["id"], socials, apps)]
        return _profile(brand, self.assets)

    def add_scan(self, brand_id, scan_type, identifier, platform, score, level, reasons):
        row = {"id": str(uuid.uuid4()), "brand_id": brand_id, "scan_type": scan_type,
               "submitted_identifier": identifier, "platform": platform, "risk_score": score,
               "risk_level": level, "reasons": reasons, "created_at": _now(),
               "brand_name": next(b["name"] for b in self.brands if b["id"] == brand_id)}
        self.scans.append(row)
        return row

    def recent_scans(self, limit=10):
        return list(reversed(self.scans))[:limit]

    def stats(self):
        return _stats(self.scans)


class SupabaseRepository:
    mode = "supabase"

    def __init__(self, client):
        self.db = client

    def _run(self, query):
        try:
            return query.execute().data or []
        except Exception as exc:  # network, auth or SQL problems all end up here
            raise DatabaseError(f"Database request failed: {exc}") from exc

    def list_profiles(self):
        brands = self._run(self.db.table("brands").select("*").order("created_at"))
        assets = self._run(self.db.table("official_assets").select("*"))
        return [_profile(b, assets) for b in brands]

    def save_profile(self, name, website, socials, apps, brand_id=None):
        if brand_id:
            self._run(self.db.table("brands").update({"name": name, "official_website": website}).eq("id", brand_id))
            self._run(self.db.table("official_assets").delete().eq("brand_id", brand_id))
        else:
            brand_id = self._run(self.db.table("brands").insert({"name": name, "official_website": website}))[0]["id"]
        rows = _asset_rows(brand_id, socials, apps)
        if rows:
            self._run(self.db.table("official_assets").insert(rows))
        return next(p for p in self.list_profiles() if p["id"] == brand_id)

    def add_scan(self, brand_id, scan_type, identifier, platform, score, level, reasons):
        row = {"brand_id": brand_id, "scan_type": scan_type, "submitted_identifier": identifier,
               "platform": platform, "risk_score": score, "risk_level": level, "reasons": reasons}
        return self._run(self.db.table("scan_results").insert(row))[0]

    def recent_scans(self, limit=10):
        rows = self._run(self.db.table("scan_results").select("*, brands(name)")
                         .order("created_at", desc=True).limit(limit))
        for r in rows:
            r["brand_name"] = (r.pop("brands", None) or {}).get("name", "")
        return rows

    def stats(self):
        # Prototype shortcut: counts the 5000 newest scans. Use SQL COUNT(*) queries for big data.
        rows = self._run(self.db.table("scan_results").select("scan_type,risk_level").limit(5000))
        return _stats(rows)


def create_repository():
    """Return (repository, status_message). Falls back to demo mode with a visible explanation."""
    url, key = os.getenv("SUPABASE_URL", "").strip(), os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    if not url or not key:
        return MemoryRepository(), ("Demo mode: Supabase is not configured, so nothing is saved permanently. "
                                    "Set SUPABASE_URL and SUPABASE_SERVICE_KEY (see README) to enable the database.")
    try:
        from supabase import create_client
        repo = SupabaseRepository(create_client(url, key))
        repo.list_profiles()  # connection + tables check
        return repo, "Connected to Supabase. Data is saved permanently."
    except Exception as exc:
        return MemoryRepository(), (f"Demo mode: could not use Supabase ({str(exc)[:160]}). Nothing is saved "
                                    "permanently. Check your keys and that schema.sql has been run.")
