# abambassadors.com

## Hospitality Talks Episodes

New episodes are added by running `_scripts/update-episodes.py`, which calls the [YouTube Data API v3](https://developers.google.com/youtube/v3) to list the channel's uploads. The script creates a markdown file in `_hospitality-talks/` for each new video it finds.

The script needs a `YOUTUBE_API_KEY` environment variable, set from the `YOUTUBE_API_KEY` repo secret in [update-episodes.yml](.github/workflows/update-episodes.yml). The key only needs the (default, free) YouTube Data API v3 quota — no billing account required.

### Filtering Shorts and Clips

The script skips a video if either is true:

- Its duration is 60 seconds or under (YouTube's Shorts threshold), or
- Its title or description contains one of the following hashtags:

  | Tag | Filters |
  |-----|---------|
  | `#shorts` or `#short` | YouTube Shorts |
  | `#youtubeshorts` | YouTube Shorts (alternate tag) |
  | `#clips` or `#clip` | YouTube Clips |

To ensure a Short or Clip is never published to the site, add at least one of the relevant hashtags to the **YouTube video description** before the feed is fetched.