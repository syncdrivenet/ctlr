import time
import uuid as uuid_lib
from config import NODES, START_DELAY_MS
from nodes.client import CameraNode
from session_manager import setup_session
import db

class Orchestrator:
    def __init__(self):
        self.nodes = [CameraNode(h) for h in NODES]
        self.current_uuid = None

    def preflight(self) -> bool:
        all_ok = True

        for node in self.nodes:
            r = node.preflight()

            # handle totally broken responses safely
            if not isinstance(r, dict):
                print(f"[PREFLIGHT] {node.host}: FAIL (invalid response)")
                all_ok = False
                continue

            # handle network/API failure format
            if r.get("ok") is False:
                print(f"[PREFLIGHT] {node.host}: FAIL ({r.get('error')})")
                all_ok = False
                continue

            # old-style success format (if your API still uses it)
            ready = r.get("success") and r.get("data", {}).get("ready")

            print(f"[PREFLIGHT] {node.host}: {'OK' if ready else 'FAIL'}")

            if not ready:
                all_ok = False

        return all_ok

    def start(self) -> bool:
        self.current_uuid = str(uuid_lib.uuid4())
        start_at = int(time.time() * 1000) + START_DELAY_MS

        for node in self.nodes:
            r = node.start(self.current_uuid, start_at)
            ok = r.get("success")
            print(f"[START] {node.host}: {'OK' if ok else r.get('error')}")
            if not ok:
                return False

        db.insert_session(self.current_uuid, start_at)
        return True

    def stop(self) -> bool:
        stopped_at = int(time.time() * 1000)

        for node in self.nodes:
            r = node.stop()
            ok = r.get("success")
            print(f"[STOP] {node.host}: {'OK' if ok else r.get('error')}")
            if not ok:
                return False

        if self.current_uuid:
            db.update_session_stop(self.current_uuid, stopped_at)
            self.current_uuid = None
        return True

    def status(self):
        for node in self.nodes:
            r = node.status()
            if r.get("success"):
                d = r.get("data", {})
                print(f"{node.host}: {d.get('state')} seg={d.get('segment')}")
            else:
                print(f"{node.host}: ERROR {r.get('error')}")
