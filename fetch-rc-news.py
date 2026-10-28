
#!/usr/bin/env python3
"""Fetch RC RSS feeds and generate rc-news.json."""

import json
import re
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path

FEEDS = [
    ("RC Driver", "https://www.rcdriver.com/feed/"),
    ("Big Squid RC", "https://www.bigsquidrc.com/feed/"),
    ("RC Car Action", "https://www.rccaraction.com/feed/"),
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; RCGarageSLNewsBot/1.0; "
        "+https://rc-garage-sl.web.app)"
    )
}


def localname(tag):
    return tag.rsplit("}", 1)[-1].lower()


def child_text(node, wanted):
    wanted = {name.lower() for name in wanted}

    for child in node.iter():
        if (
            localname(child.tag) in wanted
            and child.text
            and child.text.strip()
        ):
            return child.text.strip()

    return ""


def get_attr(node, attr):
    """Read image URLs from RSS enclosure and Media RSS elements."""
    for element in node.iter():
        tag = localname(element.tag)

        if tag not in ("enclosure", "thumbnail", "content"):
            continue

        value = (
            element.attrib.get(attr)
            or element.attrib.get(
                "{http://search.yahoo.com/mrss/}" + attr
            )
        )

        if value and (
            attr != "url"
            or element.attrib.get("type", "").startswith("image/")
            or tag != "content"
        ):
            return value.strip()

    return ""


def extract_image(node, description, article_link):
    """Try RSS image metadata first, then image tags in the description."""
    thumbnail = (
        get_attr(node, "url")
        or get_attr(node, "href")
    )

    # Some feeds include images inside their HTML description.
    if not thumbnail:
        html = unescape(description)

        image_match = re.search(
            r"""<img\b[^>]*?\b(?:src|data-src|data-lazy-src)\s*=\s*["']([^"']+)["']""",
            html,
            re.IGNORECASE,
        )

        if image_match:
            thumbnail = unescape(image_match.group(1)).strip()

    if not thumbnail:
        return ""

    if thumbnail.startswith("//"):
        thumbnail = "https:" + thumbnail
    elif thumbnail.startswith("/"):
        thumbnail = urllib.parse.urljoin(article_link, thumbnail)

    if not thumbnail.startswith(("http://", "https://")):
        return ""

    return thumbnail


def parse_feed(source, feed_url):
    request = urllib.request.Request(
        feed_url,
        headers=HEADERS,
    )

    with urllib.request.urlopen(request, timeout=25) as response:
        raw = response.read()

    root = ET.fromstring(raw)

    nodes = [
        node
        for node in root.iter()
        if localname(node.tag) in ("item", "entry")
    ]

    articles = []

    for node in nodes[:12]:
        title = child_text(node, ["title"])

        link = ""
        for element in node.iter():
            if localname(element.tag) == "link":
                link = (
                    element.attrib.get("href")
                    or (element.text or "").strip()
                )
                if link:
                    break

        if not link:
            link = child_text(node, ["guid"])

        if not title or not link.startswith(("http://", "https://")):
            continue

        description = child_text(
            node,
            ["description", "summary", "encoded", "content"],
        )

        pub_date = child_text(
            node,
            ["pubdate", "published", "updated", "date", "issued"],
        )

        thumbnail = extract_image(node, description, link)

        articles.append({
            "title": unescape(title),
            "link": link,
            "pubDate": pub_date,
            "description": unescape(description),
            "content": unescape(description),
            "thumbnail": thumbnail,
            "source": source,
        })

    return articles


items = []

for source, feed_url in FEEDS:
    try:
        feed_items = parse_feed(source, feed_url)
        image_count = sum(
            1 for item in feed_items if item["thumbnail"]
        )

        print(
            f"{source}: {len(feed_items)} articles, "
            f"{image_count} image URLs"
        )

        items.extend(feed_items)

    except Exception as exc:
        print(f"WARNING: {source} feed failed: {exc}")


def date_key(item):
    value = item.get("pubDate", "")

    try:
        parsed_date = parsedate_to_datetime(value)
        return parsed_date.timestamp()
    except (TypeError, ValueError, OverflowError):
        try:
            return datetime.fromisoformat(
                value.replace("Z", "+00:00")
            ).timestamp()
        except (TypeError, ValueError, OverflowError):
            return 0


items.sort(key=date_key, reverse=True)
items = items[:30]

output = {
    "updatedAt": datetime.now(timezone.utc).isoformat(),
    "items": items,
}

output_path = Path(__file__).resolve().parent / "rc-news.json"
output_path.write_text(
    json.dumps(output, ensure_ascii=False),
    encoding="utf-8",
)

image_total = sum(1 for item in items if item["thumbnail"])

print(f"Wrote rc-news.json with {len(items)} items")
print(f"Articles with image URLs: {image_total}/{len(items)}")
print(f"JSON file size: {output_path.stat().st_size} bytes")
