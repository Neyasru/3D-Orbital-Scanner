import os
import time
import asyncio

IS_PI = os.path.exists("/proc/device-tree/model")

if IS_PI:
    from picamera2 import Picamera2
    import io

class Camera:
    def __init__(self):
        self._streaming = False
        if IS_PI:
            self._cam = Picamera2()
            self._cam.configure(self._cam.create_still_configuration(
                main={"size": (3280, 2464)}
            ))
            self._cam.start()

    def capture(self, path: str):
        if IS_PI:
            self._cam.capture_file(path)
        else:
            self._mock_capture(path)

    def _mock_capture(self, path: str):
        import struct, zlib
        # Genera un JPEG mínimo válido de 100x100 gris con timestamp
        w, h = 100, 100
        raw = bytes([128] * (w * h * 3))
        with open(path, "wb") as f:
            # PNG mínimo como placeholder (más fácil que JPEG sin deps)
            def chunk(name, data):
                c = zlib.crc32(name + data) & 0xffffffff
                return struct.pack(">I", len(data)) + name + data + struct.pack(">I", c)
            ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
            rows = b"".join(b"\x00" + bytes([128]*w*3) for _ in range(h))
            idat = zlib.compress(rows)
            f.write(b"\x89PNG\r\n\x1a\n")
            f.write(chunk(b"IHDR", ihdr))
            f.write(chunk(b"IDAT", idat))
            f.write(chunk(b"IEND", b""))

    def start_stream(self):
        self._streaming = True
        if IS_PI:
            self._cam.configure(self._cam.create_video_configuration(
                main={"size": (1280, 720)}
            ))

    def stop_stream(self):
        self._streaming = False

    def mjpeg_generator(self):
        if IS_PI:
            yield from self._pi_stream()
        else:
            yield from self._mock_stream()

    def _mock_stream(self):
        import struct, zlib
        while self._streaming:
            # Frame gris simple
            w, h = 320, 240
            def chunk(name, data):
                c = zlib.crc32(name + data) & 0xffffffff
                return struct.pack(">I", len(data)) + name + data + struct.pack(">I", c)
            ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
            rows = b"".join(b"\x00" + bytes([100]*w*3) for _ in range(h))
            idat = zlib.compress(rows)
            frame = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")
            yield (b"--frame\r\nContent-Type: image/png\r\n\r\n" + frame + b"\r\n")
            time.sleep(0.1)

    def _pi_stream(self):
        import io
        while self._streaming:
            buf = io.BytesIO()
            self._cam.capture_file(buf, format="jpeg")
            frame = buf.getvalue()
            yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n")
            time.sleep(0.05)