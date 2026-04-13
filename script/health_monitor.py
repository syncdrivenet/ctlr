#!/usr/bin/env python3
import paho.mqtt.client as mqtt
import json
import socket
import os
from datetime import datetime, timezone

def get_hostname():
    return socket.gethostname().replace("-", "_")

def get_cpu_usage():
    with open("/proc/stat") as f:
        line = f.readline()
    parts = line.split()
    idle = int(parts[4])
    total = sum(int(p) for p in parts[1:])
    # Read again after small delay for delta
    import time
    time.sleep(0.1)
    with open("/proc/stat") as f:
        line = f.readline()
    parts = line.split()
    idle2 = int(parts[4])
    total2 = sum(int(p) for p in parts[1:])
    idle_delta = idle2 - idle
    total_delta = total2 - total
    return round(100 * (1 - idle_delta / total_delta), 1) if total_delta else 0

def get_temperature():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            return round(int(f.read().strip()) / 1000, 1)
    except:
        return None

def get_memory_usage():
    with open("/proc/meminfo") as f:
        lines = f.readlines()
    mem = {}
    for line in lines:
        parts = line.split()
        mem[parts[0].rstrip(":")] = int(parts[1])
    total = mem["MemTotal"]
    available = mem.get("MemAvailable", mem["MemFree"])
    used_pct = round(100 * (1 - available / total), 1)
    return used_pct

def get_disk_usage():
    st = os.statvfs("/")
    total = st.f_blocks * st.f_frsize
    free = st.f_bavail * st.f_frsize
    used_pct = round(100 * (1 - free / total), 1)
    return used_pct

def get_load_average():
    with open("/proc/loadavg") as f:
        return float(f.read().split()[0])

def get_level(metric, value):
    thresholds = {
        "cpu": (70, 90),
        "temp": (65, 75),
        "memory": (80, 95),
        "disk": (80, 95),
        "load": (2.0, 4.0),
    }
    warn, error = thresholds.get(metric, (80, 95))
    if value >= error:
        return "ERROR"
    elif value >= warn:
        return "WARN"
    return "INFO"

def main():
    node = get_hostname()
    ts = datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
    
    metrics = {
        "cpu": get_cpu_usage(),
        "temp": get_temperature(),
        "memory": get_memory_usage(),
        "disk": get_disk_usage(),
        "load": get_load_average(),
    }
    
    # Determine overall level (worst case)
    levels = [get_level(k, v) for k, v in metrics.items() if v is not None]
    if "ERROR" in levels:
        level = "ERROR"
    elif "WARN" in levels:
        level = "WARN"
    else:
        level = "INFO"
    
    # Build message
    parts = []
    for k, v in metrics.items():
        if v is not None:
            unit = "°C" if k == "temp" else "%" if k != "load" else ""
            parts.append(f"{k}={v}{unit}")
    message = " | ".join(parts)
    
    payload = {
        "ts": ts,
        "node": node,
        "component": "health",
        "level": level,
        "message": message
    }
    
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.connect("localhost", 1883, 60)
    client.publish("logging/health", json.dumps(payload))
    client.disconnect()
    
    print(f"[{level}] {node}: {message}")

if __name__ == "__main__":
    main()
