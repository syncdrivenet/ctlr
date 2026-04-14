# Controller (ctlr)

Central orchestrator for multi-camera recording system. Coordinates cameras, receives sync data, and processes recordings.

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
│  ┌─────────────┐                        ┌─────────────┐            │
│  │   SQLite    │                        │  /mnt/sync  │            │
│  │   Sessions  │                        │  (output)   │            │
│  └─────────────┘                        └─────────────┘            │
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
3. ctlr ─── POST /record/start ───► cam-01, cam-02 (parallel)
4. Cameras wait until start_at, then record synchronized
5. iOS App ─── POST /api/record/stop ───► ctlr
6. ctlr ─── POST /record/stop ───► cam-01, cam-02
7. Cameras finalize and rsync remaining segments
```

### Sync & Post-Process Flow
```
During Recording:
  cam-01 ──rsync──► /mnt/logging/cam-01/{uuid}/seg_*.mp4
  cam-02 ──rsync──► /mnt/logging/cam-02/{uuid}/seg_*.mp4

After Recording (iOS triggers):
  iOS ──POST /api/sync/phone──► /mnt/logging/phone/{uuid}/*.csv
                                    │
                                    ▼
                          postprocess.py --uuid {uuid}
                                    │
                                    ▼
                          /mnt/sync/{uuid}/
                            ├── cam-01.mp4 (concatenated)
                            ├── cam-02.mp4 (concatenated)
                            ├── phone/
                            │   ├── accelerometer.csv
                            │   ├── gyroscope.csv
                            │   └── ...
                            └── manifest.json
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/status` | GET | System status, cameras, sync info |
| `/api/sync/status` | GET | Detailed sync status for preflight |
| `/api/record/start` | POST | Start synchronized recording |
| `/api/record/stop` | POST | Stop recording |
| `/api/sync/phone` | POST | Upload phone sensor data |
| `/api/sessions` | GET | List recorded sessions |
| `/health` | GET | Health check |

### GET /api/status Response

```json
{
  "ready": true,
  "recording": false,
  "uuid": null,
  "duration": 0,
  "cameras": [
    {
      "name": "cam-01",
      "connected": true,
      "state": "idle",
      "segment": null,
      "cpu": 25.5,
      "ram": 45.2,
      "disk_free_gb": 28.5,
      "temp": 52.3,
      "sync_status": "idle",
      "sync_segments_synced": 10,
      "sync_segments_queued": 0,
      "segments_on_ctlr": 10
    }
  ],
  "storage": {
    "used_gb": 150.5,
    "total_gb": 500.0,
    "percent": 30.1
  },
  "system": {
    "cpu_percent": 15.0,
    "mem_percent": 35.0,
    "temp_c": 45.0
  }
}
```

### GET /api/sync/status Response

Used by iOS for preflight checks before uploading phone data:

```json
{
  "recording": false,
  "uuid": "abc12345-...",
  "all_synced": true,
  "any_syncing": false,
  "cameras": [
    {
      "name": "cam-01",
      "connected": true,
      "sync_status": "idle",
      "segments_local": 10,
      "segments_on_ctlr": 10,
      "segments_pending": 0
    }
  ]
}
```

### POST /api/sync/phone

Preflight checks:
1. Recording must be stopped
2. No cameras actively syncing
3. All camera segments must be synced

On success:
1. Saves phone CSVs to `/mnt/logging/phone/{uuid}/`
2. Triggers `postprocess.py` in background
3. Returns immediately

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
    └── postprocess.py   # Video concatenation + data organization
```

## Storage Layout

```
/mnt/logging/                    # Raw incoming data
├── cam-01/
│   └── {uuid}/
│       ├── seg_0000.mp4
│       ├── seg_0001.mp4
│       └── ...
├── cam-02/
│   └── {uuid}/
│       └── ...
└── phone/
    └── {uuid}/
        ├── accelerometer.csv
        ├── gyroscope.csv
        └── metadata.json

/mnt/sync/                       # Processed output
└── {uuid}/
    ├── cam-01.mp4              # Concatenated video
    ├── cam-02.mp4
    ├── phone/
    │   ├── accelerometer.csv
    │   └── ...
    └── manifest.json
```

## Configuration (config.py)

```python
NODES = [
    "melb-01-cam-01:8000",
    "melb-01-cam-02:8000",
]

START_DELAY_MS = 3000  # Delay for synchronized start
```

## Services

```bash
# Start API
sudo systemctl start ctlr

# View logs
journalctl -u ctlr -f

# Restart
sudo systemctl restart ctlr
```

## Post-Processing

The `postprocess.py` script:
1. Scans `/mnt/logging/` for session UUID
2. Concatenates video segments using ffmpeg
3. Copies phone sensor data
4. Creates `manifest.json` with session metadata
5. Outputs to `/mnt/sync/{uuid}/`

```bash
# Manual run
/home/pi/ctlr/script/postprocess.py --uuid abc12345-...

# Dry run (preview only)
/home/pi/ctlr/script/postprocess.py --uuid abc12345-... --dry-run
```
