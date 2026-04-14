#!/usr/bin/env python3
"""
Post-process recorded sessions:
1. Scan /mnt/logging for session UUIDs
2. Combine camera segments + phone data
3. Output to /mnt/sync/<date>_<shortid>/
"""

import os
import json
import shutil
import subprocess
from pathlib import Path
from datetime import datetime

# Paths
LOGGING_DIR = Path("/mnt/logging")
SYNC_DIR = Path("/mnt/sync")
CAMERAS = ["melb-01-cam-01", "melb-01-cam-02", "melb-01-cam-03"]

def find_all_uuids():
    """Find all unique session UUIDs across cameras and phone"""
    uuids = set()
    
    # From cameras
    for cam in CAMERAS:
        cam_dir = LOGGING_DIR / cam
        if cam_dir.exists():
            for d in cam_dir.iterdir():
                if d.is_dir() and len(d.name) == 36:  # UUID length
                    uuids.add(d.name)
    
    # From phone
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
    
    # Camera sources
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
                # Get earliest segment time for folder naming
                first_seg_time = segments[0].stat().st_mtime
                if earliest_time is None or first_seg_time < earliest_time:
                    earliest_time = first_seg_time
    
    # Phone source
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
    
    short_id = uuid[:6]
    return f"{date_str}_{short_id}"

def concatenate_videos(segments, output_path):
    """Concatenate video segments using ffmpeg"""
    if not segments:
        return False
    
    # Create concat file
    concat_file = output_path.parent / "concat.txt"
    with open(concat_file, "w") as f:
        for seg in segments:
            f.write(f"file {seg}\n")
    
    # Run ffmpeg
    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(concat_file),
        "-c", "copy",
        str(output_path)
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=600)
        concat_file.unlink()  # Clean up
        return result.returncode == 0
    except Exception as e:
        print(f"  Error concatenating: {e}")
        return False

def process_session(uuid, dry_run=False):
    """Process a single session"""
    print(f"\nProcessing: {uuid[:8]}...")
    
    sources, earliest_time = get_session_sources(uuid)
    if not sources:
        print("  No data found, skipping")
        return False
    
    folder_name = get_folder_name(uuid, earliest_time)
    
    # Show what we found
    for name, info in sources.items():
        count = info.get("count", 0)
        print(f"  Found {name}: {count} files")
    print(f"  Output folder: {folder_name}")
    
    if dry_run:
        return True
    
    # Create output directory
    output_dir = SYNC_DIR / folder_name
    output_dir.mkdir(parents=True, exist_ok=True)
    
    manifest = {
        "uuid": uuid,
        "folder": folder_name,
        "processed_at": datetime.now().isoformat(),
        "sources": {}
    }
    
    # Process cameras - concatenate videos
    for name, info in sources.items():
        if name.startswith("melb-"):
            segments = info["segments"]
            output_file = output_dir / f"{name}.mp4"
            
            print(f"  Concatenating {len(segments)} segments -> {name}.mp4")
            if concatenate_videos(segments, output_file):
                manifest["sources"][name] = {
                    "file": f"{name}.mp4",
                    "segments": len(segments)
                }
            else:
                print(f"  Failed to concatenate {name}")
    
    # Process phone - copy CSVs
    if "phone" in sources:
        phone_out = output_dir / "phone"
        phone_out.mkdir(exist_ok=True)
        
        for csv_file in sources["phone"]["files"]:
            shutil.copy2(csv_file, phone_out / csv_file.name)
        
        manifest["sources"]["phone"] = {
            "files": [f.name for f in sources["phone"]["files"]]
        }
        print(f"  Copied {len(sources[phone][files])} phone files")
    
    # Write manifest
    manifest_path = output_dir / "manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    
    print(f"  Done -> /mnt/sync/{folder_name}")
    return True

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Post-process recorded sessions")
    parser.add_argument("--uuid", help="Process specific UUID only")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done")
    parser.add_argument("--list", action="store_true", help="List available sessions")
    args = parser.parse_args()
    
    uuids = find_all_uuids()
    
    if args.list:
        print(f"Found {len(uuids)} sessions:\n")
        for uuid in uuids:
            sources, earliest_time = get_session_sources(uuid)
            folder = get_folder_name(uuid, earliest_time)
            parts = ", ".join(sources.keys()) if sources else "no data"
            print(f"  {folder}  [{parts}]")
        return
    
    if args.uuid:
        if args.uuid in uuids or any(u.startswith(args.uuid) for u in uuids):
            # Find full UUID from prefix
            full_uuid = next((u for u in uuids if u.startswith(args.uuid)), args.uuid)
            process_session(full_uuid, dry_run=args.dry_run)
        else:
            print(f"UUID not found: {args.uuid}")
    else:
        # Process all
        print(f"Found {len(uuids)} sessions to process")
        for uuid in uuids:
            process_session(uuid, dry_run=args.dry_run)

if __name__ == "__main__":
    main()
