from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from contextlib import asynccontextmanager
import asyncio
import os
import datetime
import shutil
import tempfile
import glob

from camera import Camera
from scanner import Scanner

camera = Camera()
scanner = Scanner(camera)

CALIBRATION_DIR = "calibration_photos"

@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs("scans", exist_ok=True)
    os.makedirs(CALIBRATION_DIR, exist_ok=True)
    yield
    await scanner.stop()
    camera.stop_stream()

app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")

# --- Pages ---
 
@app.get("/")
async def index():
    return FileResponse("static/index.html")
 
@app.get("/calibration")
async def calibration_page():
    return FileResponse("static/calibration.html")

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

# --- Calibration ---
 
@app.post("/calibration/capture")
async def calibration_capture():
    filename = datetime.datetime.now().strftime("calib_%Y%m%d_%H%M%S.jpg")
    path = os.path.join(CALIBRATION_DIR, filename)
    await asyncio.get_event_loop().run_in_executor(None, camera.capture, path)
    return {"ok": True, "filename": filename}
 
@app.get("/calibration/photos")
async def calibration_list():
    if not os.path.exists(CALIBRATION_DIR):
        return []
    return sorted([f for f in os.listdir(CALIBRATION_DIR) if f.endswith(".jpg")])
 
@app.get("/calibration/photos/{filename}/thumb")
async def calibration_thumb(filename: str):
    path = os.path.join(CALIBRATION_DIR, filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Foto no encontrada")
    # Genera thumbnail con OpenCV
    import cv2
    img = cv2.imread(path)
    img = cv2.resize(img, (200, 150))
    tmp = tempfile.mktemp(suffix=".jpg")
    cv2.imwrite(tmp, img)
    return FileResponse(tmp, media_type="image/jpeg")
 
@app.get("/calibration/photos/{filename}/thumb")
async def calibration_thumb(filename: str):
    path = os.path.join(CALIBRATION_DIR, filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Foto no encontrada")
    import cv2
    from fastapi.responses import Response
    img = cv2.imread(path)
    img = cv2.resize(img, (200, 150))
    _, buf = cv2.imencode(".jpg", img)
    return Response(content=buf.tobytes(), media_type="image/jpeg")


@app.post("/calibration/run")
async def calibration_run():
    import cv2
    import numpy as np
    import json
 
    BOARD_W, BOARD_H = 7, 7
    objp = np.zeros((BOARD_W * BOARD_H, 3), np.float32)
    objp[:, :2] = np.mgrid[0:BOARD_W, 0:BOARD_H].T.reshape(-1, 2)
 
    objpoints, imgpoints = [], []
    images = glob.glob(os.path.join(CALIBRATION_DIR, "*.jpg"))
 
    if len(images) < 5:
        raise HTTPException(status_code=400, detail="Mínimo 5 fotos necesarias")
 
    gray_shape = None
    for fname in images:
        img = cv2.imread(fname)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        gray_shape = gray.shape
        ret, corners = cv2.findChessboardCorners(gray, (BOARD_W, BOARD_H), None)
        if ret:
            objpoints.append(objp)
            corners2 = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1),
                (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001))
            imgpoints.append(corners2)
 
    if len(objpoints) < 5:
        raise HTTPException(status_code=400, detail="Pocas fotos con tablero detectado")
 
    ret, mtx, dist, _, _ = cv2.calibrateCamera(
        objpoints, imgpoints, gray_shape[::-1], None, None
    )
 
    calibration = {
        "camera_matrix": mtx.tolist(),
        "dist_coeffs": dist.tolist(),
        "reprojection_error": ret
    }
    with open("calibration.json", "w") as f:
        json.dump(calibration, f, indent=2)
 
    return {"ok": True, "reprojection_error": ret, "photos_used": len(objpoints)}