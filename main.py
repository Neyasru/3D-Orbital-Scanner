from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from contextlib import asynccontextmanager
import asyncio
import os

from camera import Camera
from scanner import Scanner

camera = Camera()
scanner = Scanner(camera)

@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs("scans", exist_ok=True)
    yield
    await scanner.stop()
    camera.stop_stream()

app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def index():
    return FileResponse("static/index.html")

# --- Scan ---

@app.post("/scan/start")
async def scan_start(body: dict):
    total_angles = body.get("total_angles", 72)
    await scanner.start(total_angles)
    return {"ok": True}

@app.post("/scan/stop")
async def scan_stop():
    await scanner.stop()
    return {"ok": True}

@app.get("/scan/status")
async def scan_status():
    return scanner.status()

# --- Stream ---

@app.post("/stream/start")
async def stream_start():
    camera.start_stream()
    return {"ok": True}

@app.post("/stream/stop")
async def stream_stop():
    camera.stop_stream()
    return {"ok": True}

@app.get("/stream/feed")
async def stream_feed():
    return StreamingResponse(
        camera.mjpeg_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )

# --- Sessions ---

@app.get("/sessions")
async def list_sessions():
    sessions = []
    scans_dir = "scans"
    if not os.path.exists(scans_dir):
        return sessions
    for name in sorted(os.listdir(scans_dir), reverse=True):
        path = os.path.join(scans_dir, name)
        if not os.path.isdir(path):
            continue
        photos = len([f for f in os.listdir(path) if f.endswith(".jpg")])
        size_mb = round(sum(
            os.path.getsize(os.path.join(path, f))
            for f in os.listdir(path)
        ) / 1024 / 1024)
        mtime = os.path.getmtime(path)
        import datetime
        date = datetime.datetime.fromtimestamp(mtime).strftime("%d/%m/%Y %H:%M")
        sessions.append({"name": name, "photos": photos, "size_mb": size_mb, "date": date})
    return sessions

@app.get("/sessions/{name}/download")
async def download_session(name: str):
    import shutil, tempfile
    path = os.path.join("scans", name)
    tmp = tempfile.mktemp(suffix=".zip")
    shutil.make_archive(tmp.replace(".zip", ""), "zip", path)
    return FileResponse(tmp, filename=f"{name}.zip", media_type="application/zip")

@app.delete("/sessions/{name}")
async def delete_session(name: str):
    import shutil
    path = os.path.join("scans", name)
    if not os.path.exists(path):
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Sesión no encontrada")
    shutil.rmtree(path)
    return {"ok": True}

@app.get("/sessions/download-all")
async def download_all():
    import shutil, tempfile
    tmp = tempfile.mktemp(suffix=".zip")
    shutil.make_archive(tmp.replace(".zip", ""), "zip", "scans")
    return FileResponse(tmp, filename="all_scans.zip", media_type="application/zip")