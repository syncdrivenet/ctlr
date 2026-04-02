# Control Node

Orchestrates synchronized recording across Raspberry Pi camera nodes.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Control Node                         │
│                   pi@melb-01-ctlr                       │
│                                                         │
│  ┌─────────────┐    ┌──────────────┐    ┌──────────┐   │
│  │   main.py   │───►│ orchestrator │───►│    db    │   │
│  │   (CLI)     │    │              │    │ (SQLite) │   │
│  └─────────────┘    └──────┬───────┘    └──────────┘   │
│                            │                            │
└────────────────────────────┼────────────────────────────┘
                             │ HTTP
              ┌──────────────┼──────────────┐
              │              │              │
              ▼              ▼              ▼
        ┌──────────┐   ┌──────────┐   ┌──────────┐
        │  cam-01  │   │  cam-02  │   │  cam-N   │
        │  :8080   │   │  :8080   │   │  :8080   │
        └──────────┘   └──────────┘   └──────────┘
```

## Quick Start

```bash
cd ~/ctlr
source .venv/bin/activate

# Edit config
vi config.py

# Run commands
python main.py preflight    # Check all nodes
python main.py start        # Start synchronized recording
python main.py status       # Check recording status
python main.py stop         # Stop recording
```

## Files

| File | Description |
|------|-------------|
| `main.py` | CLI entry point |
| `orchestrator.py` | Recording orchestration logic |
| `nodes/client.py` | HTTP client for camera nodes |
| `config.py` | Node list and settings |
| `db.py` | SQLite session logging |
| `ctlr.db` | Session database |

## Configuration

Edit `config.py`:

```python
NODES = [
    "melb-01-cam-01:8080",
    "melb-01-cam-02:8080",
]
DB_PATH = "ctlr.db"
START_DELAY_MS = 3000  # 3 seconds sync delay
TIMEOUT = 5.0          # HTTP timeout
```

## Commands

### preflight

Check if all camera nodes are ready.

```bash
python main.py preflight
```

Output:
```
[PREFLIGHT] melb-01-cam-01:8080: OK
[PREFLIGHT] melb-01-cam-02:8080: OK
```

Exit code: `0` if all ready, `1` if any failed.

### start

Run preflight, then start synchronized recording on all nodes.

```bash
python main.py start
```

Output:
```
[PREFLIGHT] melb-01-cam-01:8080: OK
[PREFLIGHT] melb-01-cam-02:8080: OK
[START] melb-01-cam-01:8080: OK
[START] melb-01-cam-02:8080: OK
```

What happens:
1. Preflight all nodes
2. Generate session UUID
3. Calculate `start_at = now + START_DELAY_MS`
4. Send start command to all nodes with same `start_at`
5. Log session to database

### status

Check current state of all nodes.

```bash
python main.py status
```

Output:
```
melb-01-cam-01:8080: recording seg=2
melb-01-cam-02:8080: recording seg=2
```

### stop

Stop recording on all nodes.

```bash
python main.py stop
```

Output:
```
[STOP] melb-01-cam-01:8080: OK
[STOP] melb-01-cam-02:8080: OK
```

## API Flow

```
Controller                              Camera Nodes
    │                                        │
    │  1. GET /preflight                     │
    ├───────────────────────────────────────►│
    │◄───────────────────────────────────────┤
    │     {ready: true}                      │
    │                                        │
    │  2. POST /record/start                 │
    │     {uuid, start_at: now+3000}         │
    ├───────────────────────────────────────►│
    │◄───────────────────────────────────────┤
    │     {success: true}                    │
    │                                        │
    │         ... nodes wait until start_at ...
    │         ... recording in progress ...  │
    │                                        │
    │  3. GET /status (optional)             │
    ├───────────────────────────────────────►│
    │◄───────────────────────────────────────┤
    │     {state: "recording", segment: 2}   │
    │                                        │
    │  4. POST /record/stop                  │
    ├───────────────────────────────────────►│
    │◄───────────────────────────────────────┤
    │     {success: true}                    │
```

## Database

Sessions are logged to `ctlr.db` (SQLite):

```sql
CREATE TABLE sessions (
    uuid TEXT PRIMARY KEY,
    started_at INTEGER,  -- Unix timestamp ms
    stopped_at INTEGER   -- Unix timestamp ms
);
```

Query sessions:
```bash
sqlite3 ctlr.db "SELECT * FROM sessions ORDER BY started_at DESC LIMIT 10;"
```

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Node unreachable | Command fails, prints error |
| Preflight fails | Start aborted |
| Start while recording | Returns `"already recording"` |
| Stop while not recording | Returns `"not recording"` |

## Requirements

- Python 3.11+
- Network access to camera nodes

```bash
pip install httpx
```

## Camera Node API Reference

### GET /preflight
```json
{
  "success": true,
  "node_id": "melb-01-cam-01",
  "ts": 1712045000123,
  "data": {
    "ready": true,
    "checks": {
      "camera": { "ok": true, "msg": "/dev/video0 present" },
      "ntp": { "ok": true, "msg": "NTP synced" },
      "storage": { "ok": true, "msg": "12.4GB free" },
      "state": { "ok": true, "msg": "idle" }
    }
  },
  "error": null
}
```

### POST /record/start
Request:
```json
{"uuid": "session-abc-123", "start_at": 1712045005000}
```

Response:
```json
{
  "success": true,
  "node_id": "melb-01-cam-01",
  "ts": 1712045000456,
  "data": { "uuid": "session-abc-123", "start_at": 1712045005000 },
  "error": null
}
```

### GET /status
```json
{
  "success": true,
  "node_id": "melb-01-cam-01",
  "ts": 1712045010000,
  "data": {
    "state": "recording",
    "segment": 2,
    "error": null,
    "system": { "cpu": 45.2, "ram": 62.1, "disk_free_gb": 12.4 }
  },
  "error": null
}
```

### POST /record/stop
```json
{
  "success": true,
  "node_id": "melb-01-cam-01",
  "ts": 1712045060000,
  "data": null,
  "error": null
}
```
