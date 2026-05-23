# abambassadors.com

## Hospitality Talks Episodes

New episodes are added by running `_scripts/update-episodes.py` against a downloaded YouTube channel RSS feed. The script creates a markdown file in `_hospitality-talks/` for each new video it finds.

### Filtering Shorts and Clips

The script skips any video whose title or description contains one of the following hashtags:

| Tag | Filters |
|-----|---------|
| `#shorts` or `#short` | YouTube Shorts |
| `#youtubeshorts` | YouTube Shorts (alternate tag) |
| `#clips` or `#clip` | YouTube Clips |

To ensure a Short or Clip is never published to the site, add at least one of the relevant hashtags to the **YouTube video description** before the feed is fetched.
