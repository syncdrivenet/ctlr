"""
ctlr REST API - Camera orchestration + sync endpoints
"""
import os
import time
import uuid as uuid_lib
import shutil
import psutil
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import threading

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
    
    @property
    def duration(self):
        if self.start_time and self.recording:
            return int(time.time() - self.start_time)
        return 0

state = AppState()

# ---------- System Stats ----------
def get_system_stats():
    """Get CPU, memory, temp, disk stats"""
    cpu = psutil.cpu_percent(interval=0.1)
    mem = psutil.virtual_memory().percent
    
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

# ---------- Lifespan ----------
@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init()
    t = threading.Thread(target=health_logger_loop, daemon=True)
    t.start()
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
    """Get system status with camera sync info"""
    cameras = []
    all_ready = True
    current_uuid = state.current_uuid
    
    for node in state.nodes:
        r = node.status()
        node_name = node.host.split(":")[0]
        
        if r.get("success"):
            d = r.get("data", {})
            sys = d.get("system", {})
            sync = d.get("sync", {})
            cam_state = d.get("state", "unknown")
            cam_segment = d.get("segment")
            
            # Count segments on ctlr for this camera
            segments_on_ctlr = count_segments(node_name, current_uuid)
            
            cameras.append({
                "name": node_name,
                "connected": True,
                "state": cam_state,
                "segment": cam_segment,
                "cpu": sys.get("cpu"),
                "ram": sys.get("ram"),
                "disk_free_gb": sys.get("disk_free_gb"),
                "temp": sys.get("temp"),
                # Sync status from camera
                "sync_status": sync.get("status", "idle"),
                "sync_segments_synced": sync.get("segments_synced", 0),
                "sync_segments_queued": sync.get("segments_queued", 0),
                "sync_last": sync.get("last_sync"),
                "sync_error": sync.get("error"),
                # Segments counted on ctlr
                "segments_on_ctlr": segments_on_ctlr,
            })
            
            if cam_state != "idle" and not state.recording:
                all_ready = False
        else:
            cameras.append({
                "name": node_name,
                "connected": False,
                "state": "offline",
                "error": r.get("error")
            })
            all_ready = False
    
    stats = get_system_stats()
    
    return {
        "ready": all_ready and not state.recording,
        "recording": state.recording,
        "uuid": current_uuid,
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
        }
    }

@app.get("/api/sync/status")
def get_sync_status():
    """Get detailed sync status for preflight checks."""
    current_uuid = state.current_uuid
    cameras = []
    all_synced = True
    any_syncing = False
    
    for node in state.nodes:
        r = node.status()
        node_name = node.host.split(":")[0]
        
        if r.get("success"):
            d = r.get("data", {})
            sync = d.get("sync", {})
            cam_segment = d.get("segment") or 0
            
            segments_on_ctlr = count_segments(node_name, current_uuid)
            segments_synced = sync.get("segments_synced", 0)
            sync_status = sync.get("status", "idle")
            
            # Check if camera has pending segments
            # segment is 0-indexed, so if segment=5, we have 6 segments (0-5)
            # But segment starts at 0 when recording starts
            total_segments = cam_segment + 1 if state.recording else cam_segment
            pending = max(0, total_segments - segments_on_ctlr)
            
            if pending > 0 or sync_status == "syncing":
                all_synced = False
            if sync_status == "syncing":
                any_syncing = True
            
            cameras.append({
                "name": node_name,
                "connected": True,
                "sync_status": sync_status,
                "segments_local": total_segments,
                "segments_on_ctlr": segments_on_ctlr,
                "segments_pending": pending,
                "last_sync": sync.get("last_sync"),
                "error": sync.get("error"),
            })
        else:
            cameras.append({
                "name": node_name,
                "connected": False,
                "error": r.get("error")
            })
            all_synced = False
    
    return {
        "recording": state.recording,
        "uuid": current_uuid,
        "all_synced": all_synced,
        "any_syncing": any_syncing,
        "cameras": cameras
    }

@app.post("/api/record/start")
def start_recording():
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
    
    session_uuid = str(uuid_lib.uuid4())
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
    
    # Check sync status before allowing phone sync
    sync_status = get_sync_status()
    if sync_status["recording"]:
        raise HTTPException(status_code=409, detail="Recording in progress")
    if sync_status["any_syncing"]:
        raise HTTPException(status_code=409, detail="Camera sync in progress")
    if not sync_status["all_synced"]:
        pending_cams = [c["name"] for c in sync_status["cameras"] if c.get("segments_pending", 0) > 0]
        raise HTTPException(
            status_code=409,
            detail=f"Cameras have pending segments: {', '.join(pending_cams)}"
        )
    
    session_dir = LOGGING_DIR / "phone" / uuid
    session_dir.mkdir(parents=True, exist_ok=True)
    
    saved_files = []
    for file in files:
        file_path = session_dir / file.filename
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
        "logging": {"path": "/mnt/logging", "device": "/dev/sdb1", "fstype": "ext4", "opts": "defaults"},
        "sync": {"path": "/mnt/sync", "device": "/dev/sdb2", "fstype": "exfat", "opts": "defaults,uid=1000,gid=1000"},
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
    
    return {
        "success": all(r.get("success") for r in results.values()),
        "mounts": results
    }
