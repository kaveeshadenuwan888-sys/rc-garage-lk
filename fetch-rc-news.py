#!/usr/bin/env python3
"""Fetch RC RSS feeds server-side during GitHub Actions and write rc-news.json."""
import json, re, time, urllib.request, urllib.parse, xml.etree.ElementTree as ET
from datetime import datetime, timezone
from html import unescape
from pathlib import Path

FEEDS = [
    ("RC Driver", "https://www.rcdriver.com/feed/"),
    ("Big Squid RC", "https://www.bigsquidrc.com/feed/"),
    ("RC Car Action", "https://www.rccaraction.com/feed/"),
]
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; RCGarageSLNewsBot/1.0; +https://rc-garage-sl.web.app)"}

def localname(tag):
    return tag.rsplit('}', 1)[-1].lower()

def child_text(node, wanted):
    wanted = {x.lower() for x in wanted}
    for child in node.iter():
        if localname(child.tag) in wanted and child.text and child.text.strip():
            return child.text.strip()
    return ""

def get_attr(node, attr):
    for el in node.iter():
        if localname(el.tag) in ('enclosure', 'thumbnail', 'content'):
            val = el.attrib.get(attr) or el.attrib.get('{' + 'http://search.yahoo.com/mrss/' + '}' + attr)
            if val: return val
    return ""

def parse_feed(source, url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=25) as resp:
        raw = resp.read()
    root = ET.fromstring(raw)
    nodes = [n for n in root.iter() if localname(n.tag) in ('item', 'entry')]
    out = []
    for node in nodes[:12]:
        title = child_text(node, ['title'])
        link = ''
        for el in node.iter():
            if localname(el.tag) == 'link':
                link = el.attrib.get('href') or (el.text or '').strip()
                if link: break
        if not link:
            link = child_text(node, ['guid'])
        if not title or not link.startswith(('http://', 'https://')): continue
        desc = child_text(node, ['description', 'summary', 'encoded', 'content'])
        pub = child_text(node, ['pubdate', 'published', 'updated', 'date', 'issued'])
        
        thumb = get_attr(node, 'url') or get_attr(node, 'href')
        if not thumb:
            image_match = re.search(
                r'<img[^>]+src=["\']([^"\']+)["\']',
                desc,
                re.IGNORECASE
            )
            if image_match:
                thumb = unescape(image_match.group(1))
        if thumb.startswith('//'):
            thumb = 'https:' + thumb

        out.append({"title": unescape(title), "link": link, "pubDate": pub,
                    "description": unescape(desc), "content": unescape(desc),
                    "thumbnail": thumb, "source": source})
    return out

items=[]
for source, url in FEEDS:
    try:
        feed_items=parse_feed(source,url)
        print(f"{source}: {len(feed_items)} articles")
        items.extend(feed_items)
    except Exception as exc:
        print(f"WARNING: {source} feed failed: {exc}")

# Sort by date where parseable, retaining undated articles at the end.
def date_key(item):
    value=item.get('pubDate','')
    try:
        from email.utils import parsedate_to_datetime
        dt=parsedate_to_datetime(value)
        return dt.timestamp()
    except Exception:
        try: return datetime.fromisoformat(value.replace('Z','+00:00')).timestamp()
        except Exception: return 0
items.sort(key=date_key, reverse=True)
Path('rc-news.json').write_text(json.dumps({"updatedAt": datetime.now(timezone.utc).isoformat(), "items": items[:30]}, ensure_ascii=False), encoding='utf-8')
print(f"Wrote rc-news.json with {min(len(items),30)} items")
