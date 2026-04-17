# Controller (ctlr)

Central orchestrator for multi-camera recording system. Coordinates cameras, receives sync data, processes recordings, and manages storage.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  Controller (melb-01-ctlr)                                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐             │
│  │  REST API   │    │ Orchestrator│    │ Post-Process│             │
│  │  (FastAPI)  │◄───│             │───►│   Script    │             │
│  └──────┬──────┘    └─────────────┘    └──────┬──────┘             │
│         │                                      │                    │
│         ▼                                      ▼                    │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐            │
│  │   SQLite    │    │   Mount     │    │  /mnt/sync  │            │
│  │   Sessions  │    │   Watcher   │    │  (output)   │            │
│  └─────────────┘    └─────────────┘    └─────────────┘            │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
         ▲                                        ▲
         │ HTTP                                   │ rsync
         │                                        │
    ┌────┴────┐                            ┌──────┴──────┐
    │   iOS   │                            │   Cameras   │
    │   App   │                            │ (cam-01/02) │
    └─────────┘                            └─────────────┘
```

## Data Flow

### Recording Flow
```
1. iOS App ─── POST /api/record/start ───► ctlr
2. ctlr generates UUID + start_at timestamp
3. ctlr ─── POST /record/start ───► cam-01, cam-02, cam-03 (parallel)
4. Cameras wait until start_at, then record synchronized
5. iOS App ─── POST /api/record/stop ───► ctlr
6. ctlr ─── POST /record/stop ───► all cameras
7. Cameras finalize and rsync remaining segments
```

### Sync & Post-Process Flow
```
During Recording:
  cam-01 ──rsync──► /mnt/logging/melb-01-cam-01/{uuid}/seg_*.mp4
  cam-02 ──rsync──► /mnt/logging/melb-01-cam-02/{uuid}/seg_*.mp4
  cam-03 ──rsync──► /mnt/logging/melb-01-cam-03/{uuid}/seg_*.mp4

After Recording (iOS triggers):
  iOS ──POST /api/sync/phone──► /mnt/logging/phone/{uuid}/*.csv
                                    │
                                    ▼
                          postprocess.py --uuid {uuid}
                                    │
                                    ▼
                          /mnt/sync/{uuid}/
                            ├── melb-01-cam-01.mp4 (concatenated)
                            ├── melb-01-cam-02.mp4 (concatenated)
                            ├── melb-01-cam-03.mp4 (concatenated)
                            ├── phone/
                            │   ├── accelerometer.csv
                            │   └── ...
                            └── manifest.json
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/status` | GET | System status, cameras, sync info |
| `/api/sync/status` | GET | Sync status (from camera reports) |
| `/api/sync/report` | POST | Receive sync status from cameras |
| `/api/record/start` | POST | Start synchronized recording |
| `/api/record/stop` | POST | Stop recording |
| `/api/sync/phone` | POST | Upload phone sensor data |
| `/api/storage/status` | GET | Storage mount health |
| `/api/storage/remount` | POST | Remount storage (for iOS) |
| `/api/storage/unmount` | POST | Unmount storage partition |
| `/api/storage/eject` | POST | Safe eject (stops services, unmounts) |
| `/api/storage/mount` | POST | Mount and restart services |
| `/api/sessions` | GET | List recorded sessions |
| `/api/log` | POST | Receive logs from iOS app (→ MQTT) |
| `/health` | GET | Health check |

### GET /api/storage/status

Check SSD mount health (used by iOS app):

```json
{
  "logging": {
    "path": "/mnt/logging",
    "mounted": true,
    "accessible": true,
    "free_gb": 548.12,
    "total_gb": 589.51
  },
  "sync": {
    "path": "/mnt/sync",
    "mounted": true,
    "accessible": true,
    "free_gb": 331.32,
    "total_gb": 331.5
  },
  "healthy": true
}
```

### POST /api/storage/remount

Remount storage if stale/disconnected:

```bash
# Remount all
curl -X POST http://ctlr:8000/api/storage/remount

# Remount specific
curl -X POST http://ctlr:8000/api/storage/remount?mount=logging
curl -X POST http://ctlr:8000/api/storage/remount?mount=sync
```

## MQTT Logging

All logs are published to logging/{node} topics with structured JSON:

| Component | Level | Description |
|-----------|-------|-------------|
| health | METRICS | System health: cpu, temp, mem, disk (every 5s) |
| storage | METRICS | Storage mount status: mounted, free_gb (every 30s) |
| storage | INFO/ERROR | Mount watcher events |

## File Structure

```
/home/pi/ctlr/
├── api.py               # FastAPI REST API
├── main.py              # Entry point
├── config.py            # Node configuration
├── orchestrator.py      # Multi-camera coordination
├── db.py                # SQLite session storage
│
├── nodes/
│   └── client.py        # Camera HTTP client
│
├── lib/
│   └── logger.py        # MQTT logging
│
└── script/
    ├── postprocess.py   # Video concatenation + data organization
    └── mount_watcher.py # Storage monitor + auto-remount
```

## Storage Layout

```
/mnt/logging/                      # Raw incoming data (ext4)
├── melb-01-cam-01/
│   └── {uuid}/
│       ├── seg_0000.mp4
│       ├── seg_0001.mp4
│       └── ...
├── melb-01-cam-02/
│   └── {uuid}/
├── melb-01-cam-03/
│   └── {uuid}/
└── phone/
    └── {uuid}/
        ├── accelerometer.csv
        └── ...

/mnt/sync/                         # Processed output (exFAT - portable)
└── {uuid}/
    ├── melb-01-cam-01.mp4        # Concatenated video
    ├── melb-01-cam-02.mp4
    ├── melb-01-cam-03.mp4
    ├── phone/
    │   └── ...
    └── manifest.json
```

## Configuration (config.py)

```python
NODES = [
    "melb-01-cam-01:8080",
    "melb-01-cam-02:8080",
    "melb-01-cam-03:8080",
]

START_DELAY_MS = 3000  # Delay for synchronized start
```

## Services

```bash
# API service
sudo systemctl start ctlr-api
sudo systemctl status ctlr-api
journalctl -u ctlr-api -f

# Mount watcher (auto-remounts stale drives)
sudo systemctl start mount-watcher
sudo systemctl status mount-watcher
journalctl -u mount-watcher -f

# Restart all
sudo systemctl restart ctlr-api mount-watcher
```

## Mount Watcher

The `mount_watcher.py` service:
- Checks `/mnt/logging` and `/mnt/sync` every 30s
- Detects stale/inaccessible mounts
- Auto-remounts if mount goes stale
- Publishes storage metrics to MQTT
- Logs mount failures for alerting

## Post-Processing

The `postprocess.py` script:
1. Scans `/mnt/logging/` for session UUID
2. Concatenates video segments using ffmpeg (lossless)
3. Copies phone sensor data
4. Creates `manifest.json` with session metadata
5. Outputs to `/mnt/sync/{uuid}/`

```bash
# Manual run
/home/pi/ctlr/script/postprocess.py --uuid abc12345-...

# Dry run (preview only)
/home/pi/ctlr/script/postprocess.py --uuid abc12345-... --dry-run
```

## Adding a New Camera

1. Set up camera node (see cam README)
2. Add node to `config.py`:
   ```python
   NODES = [
       ...
       "melb-01-cam-03:8080",
   ]
   ```
3. Add camera SSH pubkey to `~/.ssh/authorized_keys`
4. Restart ctlr-api: `sudo systemctl restart ctlr-api`

### POST /api/storage/eject

Safely eject drive - stops services, syncs, unmounts both partitions:

```bash
curl -X POST http://ctlr:8000/api/storage/eject
```

Success response:
```json
{"success": true, "message": "Safe to remove drive"}
```

If blocked:
```json
{"success": false, "message": "Video processing in progress"}
```

Services stopped: can-listener, mount-watcher, log-subscriber

### POST /api/storage/mount

Re-mount drive and restart services:

```bash
curl -X POST http://ctlr:8000/api/storage/mount
```

### CAN Bus Status

`/api/status` includes CAN bus info (reads from `/tmp/can_status.json`):

```json
{
  "can": {
    "connected": true,
    "file_size_bytes": 100012653,
    "frame_count": 121497
  }
}
```

### manifest.json Format

```json
{
  "uuid": "abc12345-...",
  "folder": "2026-04-14_abc123",
  "started_at": 1776313714000,
  "stopped_at": 1776314000000,
  "processed_at": "2026-04-14T10:40:00.123456",
  "sources": {
    "melb-01-cam-01": {
      "file": "melb-01-cam-01.mp4",
      "segments": 5,
      "size_mb": 125.3
    },
    "phone": {
      "files": ["accelerometer.csv", "gyroscope.csv", "gps.csv"]
    }
  }
}
```

- `started_at` / `stopped_at`: Unix timestamps (ms) from sessions database
- `processed_at`: When postprocess ran (ISO format)
