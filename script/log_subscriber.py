import sqlite3
import paho.mqtt.client as mqtt
import json
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import time
import sys
from datetime import datetime, timezone
import re
import threading

# -----------------------------
# Configuration
# -----------------------------
DB_PATH = "/mnt/logging/logs/logs.db"
LOKI_URL = "http://100.71.5.101:3100/loki/api/v1/push"
FLUSH_INTERVAL = 5
MAX_ROWS = 100_000
WATCHDOG_TIMEOUT = 120  # Exit if no MQTT messages for 2 minutes

db_lock = threading.Lock()
last_activity = time.time()

# -----------------------------
# Helper functions
# -----------------------------
def rfc3339_utc():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")

def sanitize_label(s):
    return re.sub(r"[^a-zA-Z0-9_]", "_", s)

def ts_to_nanoseconds(ts_str):
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        return str(int(dt.timestamp() * 1_000_000_000))
    except:
        return str(int(time.time() * 1_000_000_000))

def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    return conn

# -----------------------------
# Setup SQLite
# -----------------------------
conn = get_db()
c = conn.cursor()
c.execute("""
CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT,
    node TEXT,
    component TEXT,
    level TEXT,
    message TEXT,
    status TEXT DEFAULT pending
)
""")
conn.commit()
c.close()

# -----------------------------
# Setup requests session with retries
# -----------------------------
session = requests.Session()
retries = Retry(total=3, backoff_factor=2, status_forcelist=[500,502,503,504])
adapter = HTTPAdapter(max_retries=retries)
session.mount("http://", adapter)
session.mount("https://", adapter)

# -----------------------------
# MQTT callback
# -----------------------------
def on_message(client, userdata, msg):
    global last_activity
    last_activity = time.time()
    try:
        payload = json.loads(msg.payload.decode())
        ts = payload.get("ts", rfc3339_utc())
        node = sanitize_label(payload.get("node", "unknown"))
        component = sanitize_label(payload.get("component", "general"))
        level = sanitize_label(payload.get("level", "INFO"))
        message = payload.get("message", "")

        with db_lock:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO logs (ts, node, component, level, message) VALUES (?, ?, ?, ?, ?)",
                (ts, node, component, level, message)
            )
            conn.commit()
            cur.close()
        print(f"[{ts}] {node}/{component} ({level}): {message}")
    except Exception as e:
        print(f"Error parsing MQTT message: {e}")

# -----------------------------
# Send pending logs to Loki
# -----------------------------
def send_pending_logs_to_loki():
    with db_lock:
        cur = conn.cursor()
        cur.execute("SELECT id, ts, node, component, level, message FROM logs WHERE status='pending' ORDER BY id ASC")
        rows = cur.fetchall()
        cur.close()

    if not rows:
        return

    streams = {}
    for r in rows:
        label_key = (r[2], r[3], r[4])
        if label_key not in streams:
            streams[label_key] = []
        ts_ns = ts_to_nanoseconds(r[1])
        streams[label_key].append([ts_ns, r[5]])

    payload = {
        "streams": [
            {
                "stream": {"node": node, "component": component, "level": level},
                "values": values
            }
            for (node, component, level), values in streams.items()
        ]
    }

    try:
        resp = session.post(LOKI_URL, json=payload, timeout=5)
        resp.raise_for_status()
        ids = ",".join(str(r[0]) for r in rows)
        with db_lock:
            cur = conn.cursor()
            cur.execute(f"UPDATE logs SET status='sent' WHERE id IN ({ids})")
            conn.commit()
            cur.close()
        print(f"Sent {len(rows)} logs to Loki")
    except Exception as e:
        print(f"Error sending logs to Loki: {e}")

    # cleanup
    with db_lock:
        cur = conn.cursor()
        cur.execute(f"DELETE FROM logs WHERE id NOT IN (SELECT id FROM logs ORDER BY id DESC LIMIT {MAX_ROWS})")
        conn.commit()
        cur.close()

# -----------------------------
# MQTT client
# -----------------------------
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_message = on_message
client.connect("localhost", 1883, 60)
client.subscribe("logging/#")
client.loop_start()

# -----------------------------
# Main loop
# -----------------------------
while True:
    if time.time() - last_activity > WATCHDOG_TIMEOUT:
        print(f"Watchdog: No MQTT messages in {WATCHDOG_TIMEOUT}s, exiting")
        sys.exit(1)
    send_pending_logs_to_loki()
    time.sleep(FLUSH_INTERVAL)
