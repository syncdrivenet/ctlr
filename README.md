# Controller Node

Central hub for camera network - receives logs via MQTT, forwards to Loki.

## Services

| Service | Description |
|---------|-------------|
| `mosquitto` | MQTT broker - receives logs from camera nodes |
| `log-subscriber` | Subscribes to MQTT, forwards to Loki |

## Commands

```bash
# Service management
sudo systemctl status mosquitto log-subscriber
sudo systemctl restart log-subscriber

# View logs
journalctl -u log-subscriber -f

# Monitor MQTT traffic
mosquitto_sub -t "logging/#"           # all logs
mosquitto_sub -t "logging/+/health"    # health only
mosquitto_sub -t "logging/+/rsync"     # rsync only
```

## Architecture

```
Camera nodes ──MQTT──► mosquitto ──► log_subscriber.py ──HTTP──► Loki (VPS)
                         :1883              │
                                     SQLite buffer
                                   /mnt/logging/logs/logs.db
```

## Config

Edit `/home/pi/ctlr/script/log_subscriber.py`:
- `LOKI_URL` - Loki push endpoint
- `DB_PATH` - SQLite buffer location
- `FLUSH_INTERVAL` - seconds between Loki pushes
