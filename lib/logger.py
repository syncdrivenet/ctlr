"""MQTT logger for ctlr - matches cam node format."""
import subprocess
import json
from datetime import datetime, timezone

MQTT_BROKER = "localhost"
NODE = "melb-01-ctlr"


def _publish(topic: str, payload: dict):
    """Publish JSON payload to MQTT topic."""
    try:
        subprocess.run(
            ["mosquitto_pub", "-h", MQTT_BROKER, "-t", topic, "-m", json.dumps(payload)],
            timeout=2, capture_output=True
        )
    except:
        pass


def log(component: str, message: str, level: str = "INFO"):
    """Send app log to logging/{node} topic."""
    payload = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "node": NODE,
        "level": level,
        "component": component,
        "message": message
    }
    _publish(f"logging/{NODE}", payload)


def metric(cpu: float, mem: float, temp: float, disk: float):
    """Send health metrics to logging/{node} topic with level=METRICS."""
    payload = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "node": NODE,
        "level": "METRICS",
        "component": "health",
        "cpu": cpu,
        "mem": mem,
        "temp": temp,
        "disk": disk
    }
    _publish(f"logging/{NODE}", payload)
