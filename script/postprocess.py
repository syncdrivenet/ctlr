#!/usr/bin/env python3
"""
Post-process recorded sessions with detailed logging.
"""

import os
import sys
import json
import shutil
import subprocess
from pathlib import Path
from datetime import datetime

# Add parent dir for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.logger import log

# Paths
LOGGING_DIR = Path("/mnt/logging")
SYNC_DIR = Path("/mnt/sync")
CAMERAS = ["melb-01-cam-01", "melb-01-cam-02", "melb-01-cam-03"]

def find_all_uuids():
    """Find all unique session UUIDs across cameras and phone"""
    uuids = set()
    
    for cam in CAMERAS:
        cam_dir = LOGGING_DIR / cam
        if cam_dir.exists():
            for d in cam_dir.iterdir():
                if d.is_dir() and len(d.name) == 36:
                    uuids.add(d.name)
    
    phone_dir = LOGGING_DIR / "phone"
    if phone_dir.exists():
        for d in phone_dir.iterdir():
            if d.is_dir():
                uuids.add(d.name)
    
    return sorted(uuids)

def get_session_sources(uuid):
    """Get all data sources for a session"""
    sources = {}
    earliest_time = None
    
    for cam in CAMERAS:
        cam_path = LOGGING_DIR / cam / uuid
        if cam_path.exists():
            segments = sorted(cam_path.glob("seg_*.mp4"))
            if segments:
                sources[cam] = {
                    "path": cam_path,
                    "segments": segments,
                    "count": len(segments)
                }
                first_seg_time = segments[0].stat().st_mtime
                if earliest_time is None or first_seg_time < earliest_time:
                    earliest_time = first_seg_time
    
    phone_path = LOGGING_DIR / "phone" / uuid
    if phone_path.exists():
        csvs = list(phone_path.glob("*.csv"))
        if csvs:
            sources["phone"] = {
                "path": phone_path,
                "files": csvs,
                "count": len(csvs)
            }
    
    return sources, earliest_time

def get_folder_name(uuid, earliest_time):
    """Generate folder name: YYYY-MM-DD_shortid"""
    if earliest_time:
        date_str = datetime.fromtimestamp(earliest_time).strftime("%Y-%m-%d")
    else:
        date_str = datetime.now().strftime("%Y-%m-%d")
    return f"{date_str}_{uuid[:6]}"

def concatenate_videos(segments, output_path):
    """Concatenate video segments using ffmpeg"""
    if not segments:
        return False, "No segments"
    
    concat_file = output_path.parent / "concat.txt"
    try:
        with open(concat_file, "w") as f:
            for seg in segments:
                f.write(f"file {seg}\n")
        
        cmd = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(concat_file),
            "-c", "copy",
            str(output_path)
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        concat_file.unlink()
        
        if result.returncode == 0:
            return True, None
        else:
            return False, result.stderr[:200]
    except Exception as e:
        return False, str(e)

def process_session(uuid, dry_run=False):
    """Process a single session"""
    log("postprocess", f"Starting: {uuid[:8]}...", "INFO")
    
    sources, earliest_time = get_session_sources(uuid)
    if not sources:
        log("postprocess", f"No data found for {uuid[:8]}", "WARN")
        return False
    
    folder_name = get_folder_name(uuid, earliest_time)
    
    for name, info in sources.items():
        log("postprocess", f"Found {name}: {info.get(count, 0)} files", "INFO")
    
    if dry_run:
        log("postprocess", f"Dry run - would output to {folder_name}", "INFO")
        return True
    
    output_dir = SYNC_DIR / folder_name
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        log("postprocess", f"Created output dir: {folder_name}", "INFO")
    except Exception as e:
        log("postprocess", f"Failed to create output dir: {e}", "ERROR")
        return False
    
    manifest = {
        "uuid": uuid,
        "folder": folder_name,
        "processed_at": datetime.now().isoformat(),
        "sources": {}
    }
    
    # Process cameras
    for name, info in sources.items():
        if name.startswith("melb-"):
            segments = info["segments"]
            output_file = output_dir / f"{name}.mp4"
            
            log("postprocess", f"Concatenating {name}: {len(segments)} segments", "INFO")
            success, error = concatenate_videos(segments, output_file)
            
            if success:
                size_mb = output_file.stat().st_size / (1024*1024)
                log("postprocess", f"Done {name}: {size_mb:.1f}MB", "INFO")
                manifest["sources"][name] = {
                    "file": f"{name}.mp4",
                    "segments": len(segments),
                    "size_mb": round(size_mb, 1)
                }
            else:
                log("postprocess", f"Failed {name}: {error}", "ERROR")
                manifest["sources"][name] = {"error": error}
    
    # Process phone
    if "phone" in sources:
        phone_out = output_dir / "phone"
        try:
            phone_out.mkdir(exist_ok=True)
            for csv_file in sources["phone"]["files"]:
                shutil.copy2(csv_file, phone_out / csv_file.name)
            
            manifest["sources"]["phone"] = {
                "files": [f.name for f in sources["phone"]["files"]]
            }
            log("postprocess", f"Copied {len(sources[phone][files])} phone files", "INFO")
        except Exception as e:
            log("postprocess", f"Failed to copy phone data: {e}", "ERROR")
            manifest["sources"]["phone"] = {"error": str(e)}
    
    # Write manifest
    try:
        manifest_path = output_dir / "manifest.json"
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)
        log("postprocess", f"Wrote manifest.json", "INFO")
    except Exception as e:
        log("postprocess", f"Failed to write manifest: {e}", "ERROR")
    
    log("postprocess", f"Complete: /mnt/sync/{folder_name}", "INFO")
    return True

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--uuid", help="Process specific UUID")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()
    
    uuids = find_all_uuids()
    
    if args.list:
        print(f"Found {len(uuids)} sessions:")
        for uuid in uuids:
            sources, t = get_session_sources(uuid)
            folder = get_folder_name(uuid, t)
            print(f"  {folder}  [{, .join(sources.keys())}]")
        return
    
    if args.uuid:
        full_uuid = next((u for u in uuids if u.startswith(args.uuid)), args.uuid)
        process_session(full_uuid, dry_run=args.dry_run)
    else:
        for uuid in uuids:
            process_session(uuid, dry_run=args.dry_run)

if __name__ == "__main__":
    main()
