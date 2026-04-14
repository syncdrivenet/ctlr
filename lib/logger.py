"""Simple MQTT logger for ctlr"""
import subprocess
import json
from datetime import datetime, timezone

MQTT_BROKER = "localhost"
NODE = "melb-01-ctlr"
TOPIC_BASE = f"logging/{NODE}/"

def log(component: str, message: str, level: str = "INFO"):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    payload = json.dumps({
        "ts": ts,
        "node": NODE,
        "component": component,
        "level": level,
        "message": message
    })
    try:
        subprocess.run(
            ["mosquitto_pub", "-h", MQTT_BROKER, "-t", f"{TOPIC_BASE}{component}", "-m", payload],
            timeout=2, capture_output=True
        )
    except:
        pass
