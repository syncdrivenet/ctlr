#!/usr/bin/env python3
"""Mount watcher service - monitors and auto-remounts storage."""

import os
import time
import subprocess
import json
from datetime import datetime, timezone
from pathlib import Path

# Configuration
MOUNTS = {
    "logging": {"path": "/mnt/logging", "device": "/dev/sdb1", "fstype": "ext4"},
    "sync": {"path": "/mnt/sync", "device": "/dev/sdb2", "fstype": "exfat"},
}
CHECK_INTERVAL = 30  # seconds
MQTT_BROKER = "localhost"
NODE = "melb-01-ctlr"


def mqtt_publish(topic: str, payload: dict):
    """Publish to MQTT."""
    try:
        subprocess.run(
            ["mosquitto_pub", "-h", MQTT_BROKER, "-t", topic, "-m", json.dumps(payload)],
            timeout=5, capture_output=True
        )
    except Exception as e:
        print(f"[MQTT ERROR] {e}")


def log(message: str, level: str = "INFO"):
    """Send log message."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    payload = {"ts": ts, "node": NODE, "component": "storage", "level": level, "message": message}
    mqtt_publish(f"logging/{NODE}", payload)
    print(f"[{level}] storage: {message}")


def check_mount(name: str, config: dict) -> dict:
    """Check if mount is accessible and get stats."""
    path = config["path"]
    result = {
        "name": name,
        "path": path,
        "mounted": False,
        "accessible": False,
        "free_gb": 0,
        "total_gb": 0,
        "write_ok": False,
        "latency_ms": 0,
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
    
    # Check if accessible (can stat)
    try:
        st = os.statvfs(path)
        result["accessible"] = True
        result["free_gb"] = round((st.f_bavail * st.f_frsize) / (1024**3), 2)
        result["total_gb"] = round((st.f_blocks * st.f_frsize) / (1024**3), 2)
    except OSError:
        return result
    
    # Test write latency
    test_file = Path(path) / ".write_test"
    try:
        start = time.perf_counter()
        test_file.write_text("test")
        test_file.unlink()
        result["write_ok"] = True
        result["latency_ms"] = round((time.perf_counter() - start) * 1000, 1)
    except:
        pass
    
    return result


def remount(name: str, config: dict) -> bool:
    """Attempt to remount a filesystem."""
    path = config["path"]
    device = config["device"]
    fstype = config["fstype"]
    
    log(f"Attempting remount: {name} ({path})", "WARN")
    
    # Try unmount first
    subprocess.run(["sudo", "umount", "-l", path], capture_output=True)
    time.sleep(1)
    
    # Mount
    opts = "defaults"
    if fstype == "exfat":
        opts = "defaults,uid=1000,gid=1000"
    
    result = subprocess.run(
        ["sudo", "mount", "-t", fstype, "-o", opts, device, path],
        capture_output=True, text=True
    )
    
    if result.returncode == 0:
        log(f"Remount successful: {name}", "INFO")
        return True
    else:
        log(f"Remount failed: {name} - {result.stderr.strip()}", "ERROR")
        return False


def publish_metrics(statuses: list):
    """Publish storage metrics."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    payload = {"ts": ts, "node": NODE, "level": "METRICS", "component": "storage"}
    
    parts = []
    for status in statuses:
        name = status["name"]
        payload[f"{name}_mounted"] = status["mounted"]
        payload[f"{name}_accessible"] = status["accessible"]
        payload[f"{name}_free_gb"] = status["free_gb"]
        payload[f"{name}_write_ok"] = status["write_ok"]
        payload[f"{name}_latency_ms"] = status["latency_ms"]
        ok = "OK" if status["mounted"] and status["accessible"] else "FAIL"
        parts.append(f"{name}={ok} {status['free_gb']}GB")
    
    payload["message"] = " | ".join(parts)
    mqtt_publish(f"logging/{NODE}", payload)


def main():
    log("Mount watcher started", "INFO")
    
    while True:
        statuses = []
        
        for name, config in MOUNTS.items():
            status = check_mount(name, config)
            statuses.append(status)
            
            # Auto-remount if mounted but not accessible
            if status["mounted"] and not status["accessible"]:
                log(f"Mount stale: {name} - attempting recovery", "WARN")
                if remount(name, config):
                    status = check_mount(name, config)
                    statuses[-1] = status
            
            # Alert if not mounted
            elif not status["mounted"]:
                log(f"Mount missing: {name} ({config[path]})", "ERROR")
        
        publish_metrics(statuses)
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
