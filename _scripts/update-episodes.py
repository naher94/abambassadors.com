#!/usr/bin/env python3
"""
Parse a YouTube RSS feed XML file and generate Jekyll markdown files
for any episodes not already present in _hospitality-talks/.
"""

import os
import re
import sys
import unicodedata
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

COLLECTION_DIR = "_hospitality-talks"

NAMESPACES = {
    "atom": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
    "media": "http://search.yahoo.com/mrss/",
}


def generate_slug(title: str) -> str:
    """Generate a URL-safe slug matching the existing filename convention."""
    slug = title.lower()
    # Normalize unicode characters
    slug = unicodedata.normalize("NFKD", slug)
    # Apostrophes become -s (e.g. Africa's -> africa-s)
    slug = re.sub(r"['\u2019]s\b", "-s", slug)
    slug = re.sub(r"['\u2019]", "", slug)
    # Remove ampersands and common symbols
    slug = slug.replace("&", "")
    # Remove dashes (em/en)
    slug = re.sub(r"[\u2013\u2014]", "", slug)
    # Remove punctuation
    slug = re.sub(r'[?.,!:;"\u201c\u201d()\[\]]', "", slug)
    # Spaces to hyphens
    slug = re.sub(r"\s+", "-", slug)
    # Collapse multiple hyphens
    slug = re.sub(r"-+", "-", slug)
    # Trim leading/trailing hyphens
    slug = slug.strip("-")
    return slug


def format_date(iso_date: str) -> str:
    """Convert ISO 8601 date to Jekyll front matter format."""
    dt = datetime.fromisoformat(iso_date)
    return dt.strftime("%Y-%m-%d") + " 00:00:00 -0500"


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


def escape_yaml_title(title: str) -> str:
    """Escape a title for use in YAML double-quoted string."""
    return title.replace("\\", "\\\\").replace('"', '\\"')


def main():
    if len(sys.argv) < 2:
        print("Usage: update-episodes.py <feed.xml>")
        sys.exit(1)

    feed_path = sys.argv[1]

    if not os.path.exists(feed_path):
        print(f"Error: Feed file not found: {feed_path}")
        sys.exit(1)

    tree = ET.parse(feed_path)
    root = tree.getroot()

    entries = root.findall("atom:entry", NAMESPACES)
    print(f"Found {len(entries)} entries in feed")

    # Collect existing slugs
    existing_files = set()
    if os.path.isdir(COLLECTION_DIR):
        for f in os.listdir(COLLECTION_DIR):
            if f.endswith(".md"):
                existing_files.add(f[:-3])  # strip .md

    created = 0
    for entry in entries:
        video_id_el = entry.find("yt:videoId", NAMESPACES)
        title_el = entry.find("atom:title", NAMESPACES)
        published_el = entry.find("atom:published", NAMESPACES)
        media_group = entry.find("media:group", NAMESPACES)

        if video_id_el is None or title_el is None or published_el is None:
            print("Skipping entry with missing data")
            continue

        video_id = video_id_el.text.strip()
        title = title_el.text.strip()
        published = published_el.text.strip()

        desc_el = media_group.find("media:description", NAMESPACES) if media_group is not None else None
        description = clean_description(desc_el.text if desc_el is not None and desc_el.text else "")

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
