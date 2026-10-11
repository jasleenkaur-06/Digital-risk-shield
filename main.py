"""FastAPI app: thin HTTP layer. Run from the backend/ folder: uvicorn app.main:app --reload"""
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

try:  # optional: load backend/.env for local development
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except ImportError:
    pass

from . import services
from .repository import DatabaseError, create_repository

app = FastAPI(title="Digital Risk Shield")
repo, status_message = create_repository()


class AppAsset(BaseModel):
    name: str = ""
    publisher: str = ""


class BrandIn(BaseModel):
    name: str
    official_website: str = ""
    socials: List[str] = []
    apps: List[AppAsset] = []


class SocialScanIn(BaseModel):
    brand_name: str
    submitted: str
    platform: str
    description: str = ""


class AppScanIn(BaseModel):
    brand_name: str
    submitted: str
    publisher: str = ""
    description: str = ""


def guarded(fn, *args):
    """Run a service call and turn known errors into clear HTTP responses."""
    try:
        return fn(repo, *args)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except DatabaseError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.get("/api/status")
def status():
    return {"mode": repo.mode, "message": status_message, "platforms": services.PLATFORMS,
            "demo_brand": services.DEMO_BRAND["name"]}


@app.get("/api/dashboard")
def dashboard():
    return guarded(services.dashboard)


@app.get("/api/brand")
def get_brand():
    return {"brand": guarded(services.get_profile)}


@app.put("/api/brand")
def put_brand(body: BrandIn):
    apps = [a.dict() for a in body.apps]
    return {"brand": guarded(services.save_profile, body.name, body.official_website, body.socials, apps)}


@app.post("/api/brand/demo")
def demo_brand():
    return {"brand": guarded(services.load_demo_brand)}


@app.post("/api/scan/social")
def scan_social(body: SocialScanIn):
    return guarded(services.scan_social, body.brand_name, body.submitted, body.platform, body.description)


@app.post("/api/scan/app")
def scan_app(body: AppScanIn):
    return guarded(services.scan_app, body.brand_name, body.submitted, body.publisher, body.description)


# Serve the frontend last so /api routes win.
app.mount("/", StaticFiles(directory=Path(__file__).resolve().parents[2] / "frontend", html=True), name="frontend")
