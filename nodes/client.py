import httpx
from config import TIMEOUT

class CameraNode:
    def __init__(self, host: str):
        self.host = host
        self.url = f"http://{host}"

    def preflight(self) -> dict:
        r = httpx.get(f"{self.url}/preflight", timeout=TIMEOUT)
        return r.json()

    def status(self) -> dict:
        r = httpx.get(f"{self.url}/status", timeout=TIMEOUT)
        return r.json()

    def start(self, uuid: str, start_at: int) -> dict:
        r = httpx.post(f"{self.url}/record/start", json={"uuid": uuid, "start_at": start_at}, timeout=TIMEOUT)
        return r.json()

    def stop(self) -> dict:
        r = httpx.post(f"{self.url}/record/stop", timeout=TIMEOUT)
        return r.json()
