# Control Node

Orchestrates recording across Pi Zero camera nodes.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

```bash
python main.py preflight   # Check all nodes ready
python main.py start       # Preflight + start recording
python main.py stop        # Stop recording
python main.py status      # Get node states
```

## Config

Edit `config.py`:

```python
NODES = [
    "melb-01-cam-01.local:8080",
    "melb-01-cam-02.local:8080",
]
```

## API Flow

```
PREFLIGHT -> START -> (recording) -> STOP
```

Sessions are logged to `ctlr.db` (SQLite).
