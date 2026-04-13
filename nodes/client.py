import httpx
from config import TIMEOUT


class CameraNode:
    def __init__(self, host: str):
        self.host = host
        self.url = f"http://{host}"

    def _get(self, path: str) -> dict:
        try:
            r = httpx.get(f"{self.url}{path}", timeout=TIMEOUT)
            r.raise_for_status()
            return r.json()
        except httpx.ConnectError:
            return {"ok": False, "error": "connection_refused"}
        except httpx.TimeoutException:
            return {"ok": False, "error": "timeout"}
        except httpx.HTTPStatusError as e:
            return {
                "ok": False,
                "error": "http_error",
                "status_code": e.response.status_code,
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _post(self, path: str, json=None) -> dict:
        try:
            r = httpx.post(
                f"{self.url}{path}",
                json=json,
                timeout=TIMEOUT
            )
            r.raise_for_status()
            return r.json()
        except httpx.ConnectError:
            return {"ok": False, "error": "connection_refused"}
        except httpx.TimeoutException:
            return {"ok": False, "error": "timeout"}
        except httpx.HTTPStatusError as e:
            return {
                "ok": False,
                "error": "http_error",
                "status_code": e.response.status_code,
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ---- API methods ----

    def preflight(self) -> dict:
        return self._get("/preflight")

    def status(self) -> dict:
        return self._get("/status")

    def start(self, uuid: str, start_at: int) -> dict:
        return self._post("/record/start", json={
            "uuid": uuid,
            "start_at": start_at
        })

    def stop(self) -> dict:
        return self._post("/record/stop")
