import logging
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.config import PORT
from backend.database import connect_supabase

from backend.auth import router as auth_router
from backend.workspace import router as workspace_router
from backend.session import router as session_router
from backend.iot import router as iot_router
from backend.registration import router as registration_router
from backend.admin import router as admin_router
from backend.stats import router as stats_router

PUBLIC_DIR = Path(__file__).resolve().parent / "public"

log = logging.getLogger("ruang-kita")


@asynccontextmanager
async def lifespan(app: FastAPI):
    connect_supabase()
    yield


app = FastAPI(title="Ruang Kita API", version="1.0.0", lifespan=lifespan)


# Semua error dikembalikan sebagai {"error": "..."} karena itulah
# format yang dibaca frontend (sama seperti server.js versi Node).
@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: StarletteHTTPException):
    return JSONResponse(status_code=exc.status_code, content={"error": str(exc.detail)})


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=400, content={"error": "Data yang dikirim tidak valid"})


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception):
    log.exception("Error tidak tertangani di %s", request.url.path)
    return JSONResponse(status_code=500, content={"error": "Terjadi kesalahan server"})


# Menghubungkan seluruh endpoint
app.include_router(auth_router)
app.include_router(workspace_router)
app.include_router(session_router)
app.include_router(iot_router)
app.include_router(registration_router)
app.include_router(admin_router)
app.include_router(stats_router)


@app.get("/", include_in_schema=False)
def home():
    return FileResponse(PUBLIC_DIR / "index.html")


@app.get("/admin.html", include_in_schema=False)
def admin_page():
    return FileResponse(PUBLIC_DIR / "admin.html")


# File statis lain (harus paling akhir agar tidak menimpa route /api)
app.mount("/", StaticFiles(directory=PUBLIC_DIR), name="public")


if __name__ == "__main__":
    # Memungkinkan menjalankan dengan:  python main.py
    uvicorn.run("main:app", host="0.0.0.0", port=PORT)
