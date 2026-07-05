import asyncio
import os
import datetime
from camera import Camera

class Scanner:
    def __init__(self, camera: Camera):
        self._camera = camera
        self._state = "idle"
        self._current_angle = 0
        self._total_angles = 0
        self._photos_taken = 0
        self._size_bytes = 0
        self._task = None
        self._session_dir = None

    async def start(self, total_angles: int):
        if self._state == "scanning":
            return
        self._total_angles = total_angles
        self._current_angle = 0
        self._photos_taken = 0
        self._size_bytes = 0
        self._state = "scanning"
        name = datetime.datetime.now().strftime("scan_%Y_%m_%d_%H%M%S")
        self._session_dir = os.path.join("scans", name)
        os.makedirs(self._session_dir, exist_ok=True)
        self._task = asyncio.create_task(self._run())

    async def stop(self):
        self._state = "idle"
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _run(self):
        step_deg = 360 / self._total_angles
        for i in range(self._total_angles):
            if self._state != "scanning":
                break
            self._current_angle = i + 1
            # --- Mover motor aquí en el futuro ---
            # motor.move_to(i * step_deg)
            await asyncio.sleep(0.1)  # placeholder del movimiento
            # Capturar foto
            path = os.path.join(self._session_dir, f"angle_{i:04d}.jpg")
            await asyncio.get_event_loop().run_in_executor(
                None, self._camera.capture, path
            )
            if os.path.exists(path):
                self._size_bytes += os.path.getsize(path)
                self._photos_taken += 1
            await asyncio.sleep(0.05)
        self._state = "idle"

    def status(self) -> dict:
        return {
            "state": self._state,
            "current_angle": self._current_angle,
            "total_angles": self._total_angles,
            "photos_taken": self._photos_taken,
            "size_mb": round(self._size_bytes / 1024 / 1024, 1),
        }