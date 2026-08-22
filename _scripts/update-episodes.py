#!/usr/bin/env python3
"""
Fetch the latest uploads from a YouTube channel via the YouTube Data API v3
and generate Jekyll markdown files for any episodes not already present in
_hospitality-talks/.

Requires a YOUTUBE_API_KEY environment variable (see README.md).
"""

import json
import os
import re
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

COLLECTION_DIR = "_hospitality-talks"
CHANNEL_ID = "UCVBfsbg4K5sq6aPljJdWDBg"
API_BASE = "https://www.googleapis.com/youtube/v3"
MAX_PAGES = 3  # 3 pages x 50 items = up to 150 most recent uploads per run

DURATION_RE = re.compile(r"^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$")
SHORT_CLIP_TAGS_RE = re.compile(r"#(shorts?|clips?|youtubeshorts?)\b")

API_KEY = None  # set in main() from YOUTUBE_API_KEY env var


def api_get(endpoint: str, params: dict) -> dict:
    """Call a YouTube Data API v3 endpoint and return the parsed JSON body."""
    query = dict(params)
    query["key"] = API_KEY
    url = f"{API_BASE}/{endpoint}?{urllib.parse.urlencode(query)}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def get_uploads_playlist_id() -> str:
    """Look up the channel's "uploads" playlist ID (contains every public upload)."""
    data = api_get("channels", {"part": "contentDetails", "id": CHANNEL_ID})
    items = data.get("items", [])
    if not items:
        raise RuntimeError(f"No channel found for ID {CHANNEL_ID}")
    return items[0]["contentDetails"]["relatedPlaylists"]["uploads"]


def iter_playlist_items(playlist_id: str, max_pages: int = MAX_PAGES):
    """Yield {video_id, title, description, published} dicts, newest first."""
    page_token = None
    for _ in range(max_pages):
        params = {"part": "snippet", "playlistId": playlist_id, "maxResults": 50}
        if page_token:
            params["pageToken"] = page_token
        data = api_get("playlistItems", params)
        for item in data.get("items", []):
            snippet = item.get("snippet", {})
            resource = snippet.get("resourceId", {})
            if resource.get("kind") != "youtube#video":
                continue
            title = snippet.get("title", "")
            if title in ("Private video", "Deleted video"):
                continue
            yield {
                "video_id": resource.get("videoId"),
                "title": title,
                "description": snippet.get("description") or "",
                "published": snippet.get("publishedAt", ""),
            }
        page_token = data.get("nextPageToken")
        if not page_token:
            break


def get_video_durations(video_ids: list) -> dict:
    """Return {video_id: duration_in_seconds} for the given video IDs."""
    durations = {}
    for i in range(0, len(video_ids), 50):
        batch = [v for v in video_ids[i:i + 50] if v]
        if not batch:
            continue
        data = api_get("videos", {"part": "contentDetails", "id": ",".join(batch)})
        for item in data.get("items", []):
            durations[item["id"]] = parse_iso8601_duration(item["contentDetails"]["duration"])
    return durations


def parse_iso8601_duration(duration: str) -> int:
    """Convert an ISO 8601 duration (e.g. 'PT1H7M52S') to whole seconds."""
    match = DURATION_RE.match(duration or "")
    if not match:
        return 0
    hours, minutes, seconds = (int(g) if g else 0 for g in match.groups())
    return hours * 3600 + minutes * 60 + seconds


def generate_slug(title: str) -> str:
    """Generate a URL-safe slug matching the existing filename convention."""
    slug = title.lower()
    # Normalize unicode characters
    slug = unicodedata.normalize("NFKD", slug)
    # Apostrophes become -s (e.g. Africa's -> africa-s)
    slug = re.sub(r"['’]s\b", "-s", slug)
    slug = re.sub(r"['’]", "", slug)
    # Remove ampersands and common symbols
    slug = slug.replace("&", "")
    # Remove dashes (em/en)
    slug = re.sub(r"[–—]", "", slug)
    # Remove punctuation
    slug = re.sub(r'[?.,!:;"“”()\[\]]', "", slug)
    # Spaces to hyphens
    slug = re.sub(r"\s+", "-", slug)
    # Collapse multiple hyphens
    slug = re.sub(r"-+", "-", slug)
    # Trim leading/trailing hyphens
    slug = slug.strip("-")
    return slug


def format_date(iso_date: str) -> str:
    """Convert ISO 8601 date to Jekyll front matter format."""
    dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
    return dt.strftime("%Y-%m-%d")


def clean_description(desc: str) -> str:
    """Clean up YouTube description for use in front matter.

    Strips trailing social media link blocks, hashtag lines, timestamp
    chapters, and other boilerplate commonly found in YouTube descriptions.
    """
    if not desc:
        return ""

    lines = desc.split("\n")

    # Find where the social/footer block starts by scanning from the end
    # Look for patterns like "Follow us on:", URLs, "LinkedIn (...)", hashtags
    footer_patterns = [
        re.compile(r"^(follow|subscribe|connect|find|join) ", re.IGNORECASE),
        re.compile(r"^https?://"),
        re.compile(r"^(facebook|linkedin|instagram|twitter|podcast|spotify|youtube|apple)", re.IGNORECASE),
        re.compile(r"^[A-Za-z]+ \(https?://"),
        re.compile(r"^#\w+"),
    ]

    # Find the first "footer" line by scanning forward
    footer_start = len(lines)
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        # Check if this line starts a footer block
        if any(p.match(stripped) for p in footer_patterns):
            # Verify it's truly a footer: all remaining non-empty lines should match footer patterns
            remaining = [l.strip() for l in lines[i:] if l.strip()]
            if all(any(p.match(r) for p in footer_patterns) or r == "" for r in remaining):
                footer_start = i
                break

    # Also strip trailing "Video Content:" / timestamp blocks
    cleaned = lines[:footer_start]
    while cleaned:
        stripped = cleaned[-1].strip()
        if not stripped:
            cleaned.pop()
            continue
        # Remove timestamp lines like "0:00 Introduction" or "1:07:52 Conclusion"
        if re.match(r"^\d+:\d+", stripped):
            cleaned.pop()
            continue
        # Remove "Video Content:---" type headers
        if re.match(r"^video content", stripped, re.IGNORECASE):
            cleaned.pop()
            continue
        break

    result = "\n".join(cleaned).strip()
    return result


def is_short_or_clip(title: str, description: str, duration_seconds: int = 0) -> bool:
    """Return True if the video appears to be a YouTube Short or Clip."""
    if duration_seconds and duration_seconds <= 60:
        return True
    combined = f"{title} {description}".lower()
    return bool(SHORT_CLIP_TAGS_RE.search(combined))


def escape_yaml_title(title: str) -> str:
    """Escape a title for use in YAML double-quoted string."""
    return title.replace("\\", "\\\\").replace('"', '\\"')


def main():
    global API_KEY
    API_KEY = os.environ.get("YOUTUBE_API_KEY")
    if not API_KEY:
        print("Error: YOUTUBE_API_KEY environment variable is not set.")
        sys.exit(1)

    try:
        uploads_playlist_id = get_uploads_playlist_id()
        entries = list(iter_playlist_items(uploads_playlist_id))
        durations = get_video_durations([e["video_id"] for e in entries])
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:500]
        if e.code in (400, 401, 403, 404):
            print(f"Error: YouTube API request failed ({e.code}): {body}")
            print("This looks like a configuration problem (invalid/missing API key, "
                  "quota exceeded, or wrong channel ID) rather than a transient issue.")
            sys.exit(1)
        print(f"Warning: YouTube API returned a server error ({e.code}). "
              "Skipping this run — will retry on next scheduled run.")
        sys.exit(0)
    except urllib.error.URLError as e:
        print(f"Warning: Could not reach the YouTube API ({e.reason}). "
              "Skipping this run — will retry on next scheduled run.")
        sys.exit(0)

    print(f"Found {len(entries)} entries in channel uploads")

    # Collect existing slugs
    existing_files = set()
    if os.path.isdir(COLLECTION_DIR):
        for f in os.listdir(COLLECTION_DIR):
            if f.endswith(".md"):
                existing_files.add(f[:-3])  # strip .md

    created = 0
    for entry in entries:
        video_id = entry["video_id"]
        title = entry["title"]
        published = entry["published"]
        raw_description = entry["description"]
        description = clean_description(raw_description)
        duration = durations.get(video_id, 0)

        if not video_id or not title or not published:
            print("Skipping entry with missing data")
            continue

        if is_short_or_clip(title, raw_description, duration):
            print(f"  Skipped (Short/Clip): {title}")
            continue

        slug = generate_slug(title)
        file_path = os.path.join(COLLECTION_DIR, f"{slug}.md")

        if slug in existing_files:
            print(f"  Skipped (exists): {slug}.md")
            continue

        formatted_date = format_date(published)
        escaped_title = escape_yaml_title(title)
        indented_desc = description.replace("\n", "\n  ")

        content = f"""---
title: "{escaped_title}"
description: |
  {indented_desc}
video: https://youtu.be/{video_id}
date: {formatted_date}
---
"""

        os.makedirs(COLLECTION_DIR, exist_ok=True)
        with open(file_path, "w") as f:
            f.write(content)
        print(f"  Created: {slug}.md")
        created += 1

    print(f"\nDone. Created {created} new episode(s).")


if __name__ == "__main__":
    main()
