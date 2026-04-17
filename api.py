"""
ctlr REST API - Camera orchestration + sync endpoints
"""
import os
import time
import json
import uuid as uuid_lib
import shutil
import subprocess
import psutil
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from config import NODES, START_DELAY_MS
from nodes.client import CameraNode
from lib.logger import log, metric
import db

# ---------- Config ----------
LOGGING_DIR = Path("/mnt/logging")
SYNC_DIR = Path("/mnt/sync")

# ---------- State ----------
class AppState:
    def __init__(self):
        self.nodes = [CameraNode(h) for h in NODES]
        self.recording = False
        self.current_uuid = None
        self.start_time = None
        self.cached_cameras = []
    
    @property
    def duration(self):
        if self.start_time and self.recording:
            return int(time.time() - self.start_time)
        return 0

state = AppState()

# ---------- Sync State (reported by cameras) ----------
sync_state = {}

# ---------- System Stats ----------
def get_system_stats():
    """Get CPU, memory, temp, disk stats"""
    try:
        cpu = psutil.cpu_percent(interval=0.1)
    except:
        cpu = 0
    try:
        mem = psutil.virtual_memory().percent
    except:
        mem = 0
    
    temp = None
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            temp = round(int(f.read().strip()) / 1000, 1)
    except:
        pass
    
    try:
        disk = shutil.disk_usage(LOGGING_DIR)
        disk_used_gb = round(disk.used / (1024**3), 1)
        disk_total_gb = round(disk.total / (1024**3), 1)
        disk_percent = round((disk.used / disk.total) * 100, 1)
    except:
        disk_used_gb = 0
        disk_total_gb = 0
        disk_percent = 0
    
    return {
        "cpu_percent": cpu,
        "mem_percent": mem,
        "temp_c": temp,
        "disk_used_gb": disk_used_gb,
        "disk_total_gb": disk_total_gb,
        "disk_percent": disk_percent
    }

def get_can_status():
    """Read CAN status from listener status file."""
    try:
        with open("/tmp/can_status.json") as f:
            data = json.load(f)
            return {
                "connected": data.get("connected", False),
                "file_size_bytes": data.get("file_size_bytes", 0),
                "frame_count": data.get("frame_count", 0),
            }
    except:
        return {"connected": False, "file_size_bytes": 0, "frame_count": 0}


def count_segments(node_id: str, uuid: Optional[str]) -> int:
    """Count synced segments for a camera/uuid on ctlr."""
    if not uuid:
        return 0
    seg_dir = LOGGING_DIR / node_id / uuid
    if not seg_dir.exists():
        return 0
    return len(list(seg_dir.glob("seg_*.mp4")))

# ---------- MQTT Publisher ----------
def publish_status():
    """Publish current status to MQTT"""
    import subprocess
    import json
    
    status = {
        "recording": state.recording,
        "uuid": state.current_uuid,
        "duration": state.duration
    }
    payload = json.dumps(status)
    try:
        subprocess.run(
            ["mosquitto_pub", "-h", "localhost", "-t", "status/recording", "-m", payload],
            timeout=2, capture_output=True
        )
    except:
        pass

def health_logger_loop():
    """Background thread to log health every 30s"""
    while True:
        stats = get_system_stats()
        metric(stats["cpu_percent"], stats["mem_percent"], stats["temp_c"] or 0, stats["disk_percent"])
        publish_status()
        time.sleep(30)

def camera_poller_loop():
    """Background thread to poll cameras every 2s and cache results"""
    def query_camera(node):
        node_name = node.host.split(":")[0]
        current_uuid = state.current_uuid
        r = node.status()
        if r.get("success"):
            d = r.get("data", {})
            sys_info = d.get("system", {})
            sync = d.get("sync", {})
            return {
                "name": node_name,
                "connected": True,
                "state": d.get("state", "unknown"),
                "segment": d.get("segment"),
                "cpu": sys_info.get("cpu"),
                "ram": sys_info.get("ram"),
                "disk_free_gb": sys_info.get("disk_free_gb"),
                "temp": sys_info.get("temp"),
                "sync_status": sync.get("status", "idle"),
                "sync_segments_synced": sync.get("segments_synced", 0),
                "sync_segments_queued": sync.get("segments_queued", 0),
                "sync_last": sync.get("last_sync"),
                "sync_error": sync.get("error"),
                "segments_on_ctlr": count_segments(node_name, current_uuid),
            }
        else:
            return {
                "name": node_name,
                "connected": False,
                "state": "offline",
                "error": r.get("error")
            }

    while True:
        cameras = []
        with ThreadPoolExecutor(max_workers=len(state.nodes)) as executor:
            futures = {executor.submit(query_camera, node): node for node in state.nodes}
            for future in as_completed(futures):
                try:
                    cameras.append(future.result())
                except Exception as e:
                    node = futures[future]
                    cameras.append({"name": node.host.split(":")[0], "connected": False, "state": "error", "error": str(e)})
        cameras.sort(key=lambda c: c["name"])
        state.cached_cameras = cameras
        time.sleep(2)

# ---------- Lifespan ----------
@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init()
    threading.Thread(target=health_logger_loop, daemon=True).start()
    threading.Thread(target=camera_poller_loop, daemon=True).start()
    log("api", "ctlr API started")
    yield
    log("api", "ctlr API stopped")

# ---------- App ----------
app = FastAPI(title="ctlr API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- Endpoints ----------

@app.get("/api/status")
def get_status():
    """Get system status - returns cached camera data for instant response"""
    cameras = state.cached_cameras

    all_ready = all(
        c.get("connected") and c.get("state") == "idle"
        for c in cameras
    ) if cameras else False

    stats = get_system_stats()

    return {
        "ready": all_ready and not state.recording,
        "recording": state.recording,
        "uuid": state.current_uuid,
        "duration": state.duration,
        "cameras": cameras,
        "storage": {
            "used_gb": stats["disk_used_gb"],
            "total_gb": stats["disk_total_gb"],
            "percent": stats["disk_percent"]
        },
        "system": {
            "cpu_percent": stats["cpu_percent"],
            "mem_percent": stats["mem_percent"],
            "temp_c": stats["temp_c"]
        },
        "can": get_can_status()
    }



@app.post("/api/sync/report")
def sync_report(data: dict):
    """Receive sync status from camera rsync."""
    sync_state[data["camera"]] = {
        "status": data["status"],
        "files": data.get("files", 0),
        "remaining": data["remaining"],
        "ts": datetime.now().isoformat()
    }
    return {"ok": True}


@app.get("/api/sync/status")
def get_sync_status():
    """Get sync status - from camera reports. iOS compatible."""
    from config import NODES
    
    all_synced = (
        len(sync_state) == len(NODES) and
        all(c["remaining"] == 0 for c in sync_state.values())
    )
    any_syncing = any(c["status"] == "syncing" for c in sync_state.values())
    
    # Build cameras array for iOS compatibility
    cameras = []
    for name, data in sync_state.items():
        cameras.append({
            "name": name,
            "connected": True,
            "sync_status": data["status"],
            "segments_pending": data["remaining"],
            "last_sync": data.get("ts"),
        })
    cameras.sort(key=lambda c: c["name"])
    
    return {
        "recording": state.recording,
        "uuid": state.current_uuid,
        "all_synced": all_synced,
        "any_syncing": any_syncing,
        "cameras": cameras
    }



@app.post("/api/record/start")
def start_recording(uuid: str = None):
    """Start synchronized recording on all cameras"""
    if state.recording:
        raise HTTPException(status_code=409, detail="Already recording")
    
    for node in state.nodes:
        r = node.preflight()
        if not r.get("success") or not r.get("data", {}).get("ready"):
            raise HTTPException(
                status_code=503,
                detail=f"Camera {node.host} not ready"
            )
    
    session_uuid = uuid if uuid else str(uuid_lib.uuid4())
    start_at = int(time.time() * 1000) + START_DELAY_MS
    
    log("recording", f"Starting session {session_uuid}")
    
    for node in state.nodes:
        r = node.start(session_uuid, start_at)
        if not r.get("success"):
            log("recording", f"Failed to start {node.host}", "ERROR")
            for n in state.nodes:
                n.stop()
            raise HTTPException(
                status_code=500,
                detail=f"Failed to start {node.host}: {r.get('error')}"
            )
    
    state.recording = True
    state.current_uuid = session_uuid
    state.start_time = time.time()
    
    db.insert_session(session_uuid, start_at)
    publish_status()
    log("recording", f"Session {session_uuid} started on all cameras")
    
    return {
        "success": True,
        "uuid": session_uuid,
        "start_at": start_at
    }

@app.post("/api/record/stop")
def stop_recording():
    """Stop recording on all cameras"""
    if not state.recording:
        raise HTTPException(status_code=409, detail="Not recording")
    
    session_uuid = state.current_uuid
    duration = state.duration
    stopped_at = int(time.time() * 1000)
    
    log("recording", f"Stopping session {session_uuid}")
    
    errors = []
    for node in state.nodes:
        r = node.stop()
        if not r.get("success"):
            errors.append(f"{node.host}: {r.get('error')}")
            log("recording", f"Error stopping {node.host}: {r.get('error')}", "ERROR")
    
    state.recording = False
    state.current_uuid = None
    state.start_time = None
    
    db.update_session_stop(session_uuid, stopped_at)
    publish_status()
    
    log("recording", f"Session {session_uuid} stopped, duration={duration}s")
    
    return {
        "success": len(errors) == 0,
        "uuid": session_uuid,
        "duration": duration,
        "errors": errors if errors else None
    }

@app.post("/api/sync/phone")
async def sync_phone_data(
    uuid: str = Form(...),
    files: List[UploadFile] = File(...)
):
    """Receive phone sensor data and trigger post-processing"""
    if not uuid:
        raise HTTPException(status_code=400, detail="UUID required")
    
    # Check if recording in progress
    if state.recording:
        raise HTTPException(status_code=409, detail="Recording in progress")
    
    # Check actual files on disk for this UUID (not camera self-report)
    from config import NODES
    camera_names = [n.split(":")[0] for n in NODES]
    segment_counts = {}
    for cam in camera_names:
        count = count_segments(cam, uuid)
        segment_counts[cam] = count
    
    # All cameras should have same segment count (synchronized recording)
    counts = list(segment_counts.values())
    if not counts or max(counts) == 0:
        raise HTTPException(status_code=409, detail="No camera segments found for this session")
    
    # Check if any camera has fewer segments than others (still syncing)
    max_count = max(counts)
    missing = [cam for cam, count in segment_counts.items() if count < max_count]
    if missing:
        raise HTTPException(
            status_code=409,
            detail=f"Cameras still syncing: {", ".join(missing)} ({min(counts)}/{max_count} segments)"
        )
    
    session_dir = LOGGING_DIR / "phone" / uuid
    session_dir.mkdir(parents=True, exist_ok=True)
    
    saved_files = []
    for file in files:
        file_path = session_dir / file.filename
        file_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            content = await file.read()
            with open(file_path, "wb") as f:
                f.write(content)
            saved_files.append(file.filename)
        except Exception as e:
            log("sync", f"Failed to save {file.filename}: {e}", "ERROR")
    
    log("sync", f"Phone sync: {uuid[:8]}... - {len(saved_files)} files")
    
    # Trigger post-processing
    import subprocess
    subprocess.Popen(
        ["/home/pi/ctlr/script/postprocess.py", "--uuid", uuid],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    log("sync", f"Post-processing triggered for {uuid[:8]}...")
    
    return {
        "success": True,
        "uuid": uuid,
        "files_saved": len(saved_files),
        "files": saved_files,
        "processing": True
    }

@app.get("/api/sessions")
def list_sessions():
    """List recorded sessions"""
    sessions = db.get_sessions()
    return {"sessions": sessions}


# ---------- Remote Logging ----------

@app.post("/api/log")
def receive_log(payload: dict):
    """Receive log from iOS app, publish to MQTT."""
    from datetime import datetime, timezone
    
    # Add timestamp if missing
    if "ts" not in payload:
        payload["ts"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    
    # Ensure required fields
    node = payload.get("node", "unknown")
    payload.setdefault("component", "app")
    payload.setdefault("level", "INFO")
    payload.setdefault("message", "")
    
    # Publish to MQTT (same as Pi nodes)
    subprocess.run(
        ["mosquitto_pub", "-h", "localhost", "-t", f"logging/{node}", "-m", json.dumps(payload)],
        timeout=2, capture_output=True
    )
    
    return {"ok": True}

@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)


# ---------- Storage Management ----------

def check_mount(path: str) -> dict:
    """Check mount status for a path."""
    result = {
        "path": path,
        "mounted": False,
        "accessible": False,
        "free_gb": 0,
        "total_gb": 0,
    }
    
    # Check if mounted
    try:
        with open("/proc/mounts") as f:
            for line in f:
                if f" {path} " in line:
                    result["mounted"] = True
                    break
    except:
        pass
    
    if not result["mounted"]:
        return result
    
    # Check accessibility and space
    try:
        disk = shutil.disk_usage(path)
        result["accessible"] = True
        result["free_gb"] = round(disk.free / (1024**3), 2)
        result["total_gb"] = round(disk.total / (1024**3), 2)
    except:
        pass
    
    return result


@app.get("/api/storage/status")
def get_storage_status():
    """Get storage mount status for iOS app."""
    import subprocess
    
    logging_status = check_mount("/mnt/logging")
    sync_status = check_mount("/mnt/sync")
    
    return {
        "logging": logging_status,
        "sync": sync_status,
        "healthy": logging_status["accessible"] and sync_status["accessible"]
    }


@app.post("/api/storage/remount")
def remount_storage(mount: str = "all"):
    """Remount storage (logging, sync, or all)."""
    import subprocess
    
    mounts = {
        "logging": {"path": "/mnt/logging", "device": "/dev/sda1", "fstype": "ext4", "opts": "defaults"},
        "sync": {"path": "/mnt/sync", "device": "/dev/sda2", "fstype": "exfat", "opts": "defaults,uid=1000,gid=1000"},
    }
    
    targets = [mount] if mount != "all" else ["logging", "sync"]
    results = {}
    
    for name in targets:
        if name not in mounts:
            results[name] = {"success": False, "error": "Unknown mount"}
            continue
        
        cfg = mounts[name]
        path = cfg["path"]
        
        log("storage", f"Remounting {name}...", "INFO")
        
        # Unmount first
        subprocess.run(["sudo", "umount", "-l", path], capture_output=True)
        time.sleep(1)
        
        # Mount
        result = subprocess.run(
            ["sudo", "mount", "-t", cfg["fstype"], "-o", cfg["opts"], cfg["device"], path],
            capture_output=True, text=True
        )
        
        if result.returncode == 0:
            status = check_mount(path)
            results[name] = {"success": True, "status": status}
            log("storage", f"Remount {name} successful", "INFO")
        else:
            results[name] = {"success": False, "error": result.stderr.strip()}
            log("storage", f"Remount {name} failed: {result.stderr.strip()}", "ERROR")
    
    # Restart services after remount
    if all(r.get("success") for r in results.values()):
        subprocess.run(["sudo", "systemctl", "start", "mnt-logging.automount"], capture_output=True)
        subprocess.run(["sudo", "systemctl", "start", "mnt-sync.automount"], capture_output=True)
        subprocess.run(["sudo", "systemctl", "start", "can-listener"], timeout=10, capture_output=True)
        subprocess.run(["sudo", "systemctl", "start", "mount-watcher"], capture_output=True)
        subprocess.run(["sudo", "systemctl", "start", "log-subscriber"], capture_output=True)
    
    return {
        "success": all(r.get("success") for r in results.values()),
        "mounts": results
    }


@app.post("/api/storage/unmount")
def unmount_storage(mount: str = "sync"):
    """Safely unmount storage for removal."""
    import subprocess
    
    mounts = {
        "logging": "/mnt/logging",
        "sync": "/mnt/sync",
    }
    
    if mount not in mounts:
        raise HTTPException(status_code=400, detail=f"Unknown mount: {mount}")
    
    path = mounts[mount]
    
    # Stop CAN listener if unmounting logging drive
    if mount == "logging":
        log("storage", "Stopping CAN listener...", "INFO")
        subprocess.run(["sudo", "systemctl", "stop", "can-listener"], timeout=10, capture_output=True)
    
    log("storage", f"Unmounting {mount}...", "INFO")
    
    # Sync filesystem
    subprocess.run(["sync"], timeout=30)
    
    # Unmount
    result = subprocess.run(
        ["sudo", "umount", path],
        capture_output=True, text=True
    )
    
    if result.returncode == 0:
        log("storage", f"Unmounted {mount} successfully", "INFO")
        return {"success": True, "mount": mount, "message": "Safe to remove"}
    else:
        # Try lazy unmount
        result = subprocess.run(
            ["sudo", "umount", "-l", path],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            log("storage", f"Lazy unmounted {mount}", "WARN")
            return {"success": True, "mount": mount, "message": "Lazy unmount - wait before removing"}
        else:
            log("storage", f"Failed to unmount {mount}: {result.stderr}", "ERROR")
            raise HTTPException(status_code=500, detail=f"Unmount failed: {result.stderr.strip()}")


# ---------- Storage Eject (Safe) ----------

FRIENDLY_MESSAGES = {
    "postprocess": "Video processing in progress",
    "ffmpeg": "Video conversion in progress",
    "rsync": "File sync in progress",
    "listener": "CAN listener is writing",
    "log_subscriber": "Log service is writing",
    "python": "Background task running",
}


def get_blocking_reason(path: str) -> str | None:
    """Check what is blocking unmount and return friendly message."""
    import subprocess
    result = subprocess.run(["lsof", "+D", path], capture_output=True, text=True, timeout=10)
    
    if not result.stdout.strip():
        return None
    
    for process, message in FRIENDLY_MESSAGES.items():
        if process in result.stdout.lower():
            return message
    
    return "Drive is busy"


@app.post("/api/storage/eject")
def eject_storage():
    """Safely eject drive - stops services, unmounts both partitions."""
    import subprocess
    
    log("storage", "Ejecting drive...", "INFO")
    
    # 1. Stop automount first (prevents auto-remount)
    subprocess.run(["sudo", "systemctl", "stop", "mnt-sync.automount"], timeout=10)
    subprocess.run(["sudo", "systemctl", "stop", "mnt-logging.automount"], timeout=10)
    
    # 2. Stop services that use disk
    subprocess.run(["sudo", "systemctl", "stop", "can-listener"], timeout=10)
    subprocess.run(["sudo", "systemctl", "stop", "mount-watcher"], timeout=10)
    subprocess.run(["sudo", "systemctl", "stop", "log-subscriber"], timeout=10)
    
    time.sleep(1)
    
    # 3. Sync pending writes
    subprocess.run(["sync"], timeout=30)
    
    # 4. Unmount both partitions
    results = {}
    for name, path in [("logging", "/mnt/logging"), ("sync", "/mnt/sync")]:
        r = subprocess.run(["sudo", "umount", path], capture_output=True, text=True)
        if r.returncode == 0 or "not mounted" in r.stderr:
            results[name] = {"success": True}
        else:
            reason = get_blocking_reason(path) or r.stderr.strip()
            results[name] = {"success": False, "reason": reason}
    
    all_success = all(r["success"] for r in results.values())
    
    if all_success:
        log("storage", "Drive ejected safely", "INFO")
        return {"success": True, "message": "Safe to remove drive"}
    else:
        # Rollback - restart services
        subprocess.run(["sudo", "systemctl", "start", "mnt-logging.automount"], timeout=10)
        subprocess.run(["sudo", "systemctl", "start", "mnt-sync.automount"], timeout=10)
        subprocess.run(["sudo", "systemctl", "start", "can-listener"], timeout=10)
        subprocess.run(["sudo", "systemctl", "start", "mount-watcher"], timeout=10)
        subprocess.run(["sudo", "systemctl", "start", "log-subscriber"], timeout=10)
        
        failed = [f"{k}: {v['reason']}" for k, v in results.items() if not v["success"]]
        log("storage", f"Eject failed: {failed}", "WARN")
        return {"success": False, "message": failed[0] if failed else "Eject failed", "details": results}


@app.post("/api/storage/mount")
def mount_storage():
    """Re-enable storage after drive inserted."""
    import subprocess
    
    log("storage", "Mounting drive...", "INFO")
    
    # 1. Start automount
    subprocess.run(["sudo", "systemctl", "start", "mnt-logging.automount"], timeout=10)
    subprocess.run(["sudo", "systemctl", "start", "mnt-sync.automount"], timeout=10)
    
    time.sleep(1)
    
    # 2. Touch paths to trigger mount
    try:
        os.listdir("/mnt/logging")
        os.listdir("/mnt/sync")
    except:
        pass
    
    # 3. Start services
    subprocess.run(["sudo", "systemctl", "start", "can-listener"], timeout=10)
    subprocess.run(["sudo", "systemctl", "start", "mount-watcher"], timeout=10)
    subprocess.run(["sudo", "systemctl", "start", "log-subscriber"], timeout=10)
    
    # 4. Check status
    logging_ok = check_mount("/mnt/logging")["accessible"]
    sync_ok = check_mount("/mnt/sync")["accessible"]
    
    if logging_ok and sync_ok:
        log("storage", "Drive mounted successfully", "INFO")
        return {"success": True, "message": "Drive ready"}
    else:
        log("storage", "Mount incomplete", "WARN")
        return {"success": False, "message": "Mount incomplete", "logging": logging_ok, "sync": sync_ok}
