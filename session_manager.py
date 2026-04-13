# session_manager.py
import os
from pathlib import Path
from config import BASE_SESSION_PATH  # e.g., /home/pi/recordings

def setup_session(session_uuid: str) -> Path:
    node_paths = {}
    for node_host in nodes:
        node_folder = session_path / node_host
        node_folder.mkdir(parents=True, exist_ok=True)
        node_paths[node_host] = node_folder
    return node_paths
