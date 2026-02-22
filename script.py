#!/usr/bin/env python3
"""
Generate thumbnails for videos from mp4_downloads.json
Extracts a frame from the middle of each video using FFmpeg
"""

import json
import subprocess
import os
from pathlib import Path
from urllib.parse import urlparse
import sys

def parse_duration(title):
    """
    Extract duration from title like '(1h 21m, 704x512)' or '(14m 01s, 640x480)'
    Returns duration in seconds, or None if not found
    """
    import re
    
    # Try to find patterns like "1h 21m" or "14m 01s" or "38m 13s"
    match = re.search(r'\((\d+h\s*)?(\d+m)\s*(\d+s)?,', title)
    if not match:
        return None
    
    hours = match.group(1)
    minutes = match.group(2)
    seconds = match.group(3)
    
    total_seconds = 0
    if hours:
        total_seconds += int(hours.replace('h', '').strip()) * 3600
    if minutes:
        total_seconds += int(minutes.replace('m', '').strip()) * 60
    if seconds:
        total_seconds += int(seconds.replace('s', '').strip())
    
    return total_seconds

def get_video_duration(url):
    """
    Get video duration using ffprobe (requires downloading headers only)
    """
    try:
        cmd = [
            'ffprobe',
            '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            url
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            return float(result.stdout.strip())
    except Exception as e:
        print(f"  ⚠ Could not get duration via ffprobe: {e}")
    return None

def generate_thumbnail(video_url, output_path, seek_time=None):
    """
    Generate a thumbnail from a video URL using FFmpeg
    
    Args:
        video_url: URL of the video
        output_path: Path where thumbnail should be saved
        seek_time: Time in seconds to capture (None = let ffmpeg decide)
    """
    try:
        # FFmpeg command to extract a single frame
        cmd = [
            'ffmpeg',
            '-y',  # Overwrite output file
        ]
        
        if seek_time:
            cmd.extend(['-ss', str(seek_time)])  # Seek to position
        
        cmd.extend([
            '-i', video_url,  # Input URL
            '-vframes', '1',  # Extract 1 frame
            '-q:v', '2',  # Quality (2 is high quality)
            '-vf', 'scale=320:-1',  # Scale to 320px width, maintain aspect ratio
            output_path
        ])
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60  # 60 second timeout
        )
        
        if result.returncode == 0:
            return True
        else:
            print(f"  ✗ FFmpeg error: {result.stderr[:200]}")
            return False
            
    except subprocess.TimeoutExpired:
        print(f"  ✗ Timeout extracting thumbnail")
        return False
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False

def main():
    # Check if ffmpeg is installed
    try:
        subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("ERROR: ffmpeg is not installed!")
        print("Install it with: sudo apt-get install ffmpeg")
        sys.exit(1)
    
    # Load JSON
    json_path = 'mp4_downloads.json'
    if not os.path.exists(json_path):
        print(f"ERROR: {json_path} not found!")
        sys.exit(1)
    
    with open(json_path, 'r') as f:
        data = json.load(f)
    
    all_videos = data.get('mp4_files', [])
    
    print(f"Found {len(all_videos)} total MP4 files")
    
    # Deduplicate by identifier - keep only one MP4 per video
    # Prefer smaller file size (512kb version) for faster processing
    videos_by_id = {}
    for video in all_videos:
        identifier = video.get('identifier')
        if not identifier:
            continue
        
        # If we haven't seen this identifier, or this file is smaller, use it
        if identifier not in videos_by_id:
            videos_by_id[identifier] = video
        else:
            current_size = int(videos_by_id[identifier].get('size', 0))
            new_size = int(video.get('size', 0))
            if new_size < current_size and new_size > 0:
                videos_by_id[identifier] = video
    
    videos = list(videos_by_id.values())
    total = len(videos)
    
    print(f"Deduplicated to {total} unique videos (1 MP4 per video)")
    print(f"Creating thumbnails directory...")
    
    # Create thumbnails directory
    thumb_dir = Path('thumbnails')
    thumb_dir.mkdir(exist_ok=True)
    
    # Track statistics
    success_count = 0
    failed_count = 0
    skipped_count = 0
    
    # Process each video
    for i, video in enumerate(videos, 1):
        url = video.get('url')
        filename = video.get('filename')
        identifier = video.get('identifier')
        title = video.get('title', '')
        
        if not url or not identifier:
            print(f"[{i}/{total}] ⚠ Skipping: missing URL or identifier")
            skipped_count += 1
            continue
        
        # Generate thumbnail filename using identifier (unique per video)
        thumb_filename = identifier + '.jpg'
        thumb_path = thumb_dir / thumb_filename
        
        # Skip if already exists
        if thumb_path.exists():
            print(f"[{i}/{total}] ⏭ Exists: {thumb_filename}")
            skipped_count += 1
            continue
        
        print(f"[{i}/{total}] Processing: {title[:60]}...")
        
        # Try to parse duration from title
        duration = parse_duration(title)
        
        # Calculate seek time (middle of video)
        seek_time = None
        if duration:
            seek_time = duration / 2
            print(f"  → Duration: {duration}s, seeking to {seek_time}s (middle)")
        else:
            # Try to get duration via ffprobe
            print(f"  → Trying to detect duration...")
            duration = get_video_duration(url)
            if duration:
                seek_time = duration / 2
                print(f"  → Detected: {duration}s, seeking to {seek_time}s (middle)")
            else:
                # Fallback: seek to 30 seconds (better than 1 second)
                seek_time = 30
                print(f"  → Using fallback: seeking to 30s")
        
        # Generate thumbnail
        if generate_thumbnail(url, str(thumb_path), seek_time):
            print(f"  ✓ Saved: {thumb_filename}")
            success_count += 1
        else:
            failed_count += 1
    
    # Print summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"Total videos:    {total}")
    print(f"✓ Successful:    {success_count}")
    print(f"✗ Failed:        {failed_count}")
    print(f"⏭ Skipped:       {skipped_count}")
    print(f"\nThumbnails saved in: {thumb_dir.absolute()}")

if __name__ == '__main__':
    main()
