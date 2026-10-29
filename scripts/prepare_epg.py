#!/usr/bin/env python3
"""Prepare a compact TV7 EPG for Android TV, using only Python's stdlib.

Input: original upstream XMLTV (.xml.gz). Output: epg.json.gz (version 1).
Publish the result from a separate public repository; never publish a private
Android project or its configuration merely to host this feed.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, time, timezone
import gzip
import json
import logging
import os
from pathlib import Path
import re
import tempfile
import urllib.request
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

SOURCE = 'https://raw.githubusercontent.com/mathewmeconry/TV7_EPG_Data/master/tv7_epg.xml.gz'
ZONE = ZoneInfo('Europe/Zurich')
MAX_COMPRESSED = 30 * 1024 * 1024
MAX_XML = 350 * 1024 * 1024
MAX_CHANNELS = 500
MAX_PROGRAMMES = 20000
MAX_PER_CHANNEL = 250

class LimitedStream:
    def __init__(self, source, limit: int):
        self.source, self.limit, self.count = source, limit, 0

    def read(self, size=-1):
        # ET/GzipFile normally request bounded chunks; cap unrestricted reads too.
        size = 65536 if size is None or size < 0 else size
        chunk = self.source.read(size)
        self.count += len(chunk)
        if self.count > self.limit:
            raise ValueError(f'Input exceeds {self.limit} bytes')
        return chunk

    def readable(self):
        return True


def epg_time(value: str | None) -> int | None:
    if not value:
        return None
    matched = re.fullmatch(r'(\d{12}|\d{14})(?:\s+([+-]\d{4}))?', value.strip())
    if not matched:
        return None
    digits, offset = matched.groups()
    if len(digits) == 12:
        digits += '00'
    try:
        dt = datetime.strptime(digits, '%Y%m%d%H%M%S')
        if offset:
            hours, minutes = int(offset[1:3]), int(offset[3:5])
            if hours > 23 or minutes > 59:
                return None
            seconds = (hours * 60 + minutes) * 60
            if offset[0] == '-':
                seconds = -seconds
            dt = dt.replace(tzinfo=timezone(timedelta(seconds=seconds)))
        else:
            dt = dt.replace(tzinfo=ZONE)
        return int(dt.timestamp() * 1000)
    except ValueError:
        return None


def local_name(tag: str) -> str:
    return tag.rsplit('}', 1)[-1]


def child_text(element, tag: str, cap: int) -> str:
    for child in element:
        if local_name(child.tag) == tag:
            return (child.text or '').strip()[:cap]
    return ''


def preprocess(source, *, now: datetime | None = None) -> dict:
    now = (now or datetime.now(timezone.utc)).astimezone(ZONE)
    start_day = now.date()
    # Today, tomorrow and the first six hours of the next day.
    from_ms = int(datetime.combine(start_day, time.min, ZONE).timestamp() * 1000)
    until_ms = int((datetime.combine(start_day + timedelta(days=2), time.min, ZONE)
                    + timedelta(hours=6)).timestamp() * 1000)
    names: dict[str, list[str]] = {}
    schedules: dict[str, list] = {}
    total = 0
    root = None
    for event, elem in ET.iterparse(source, events=('start', 'end')):
        if root is None:
            root = elem
        if event != 'end':
            continue
        tag = local_name(elem.tag)
        if tag == 'channel':
            channel_id = (elem.get('id') or '')[:130]
            if channel_id and len(names) < MAX_CHANNELS:
                display = []
                for child in elem:
                    if local_name(child.tag) == 'display-name' and child.text:
                        clean = child.text.strip()[:100]
                        if clean and clean not in display:
                            display.append(clean)
                            if len(display) >= 12:
                                break
                names[channel_id] = display
            elem.clear()
            if root is not None:
                root.clear()
        elif tag == 'programme':
            channel_id = (elem.get('channel') or '')[:130]
            start, end = epg_time(elem.get('start')), epg_time(elem.get('stop'))
            if (channel_id and start is not None and end is not None and
                    from_ms < end and start < until_ms and end > start and
                    len(schedules.get(channel_id, [])) < MAX_PER_CHANNEL):
                title = child_text(elem, 'title', 170)
                if title:
                    schedules.setdefault(channel_id, []).append([
                        start, end, title,
                        child_text(elem, 'sub-title', 130),
                        child_text(elem, 'desc', 420),
                    ])
                    total += 1
                    if total > MAX_PROGRAMMES:
                        raise ValueError('Too many EPG programmes')
            elem.clear()
            if root is not None:
                root.clear()

    if not schedules:
        raise ValueError('Upstream XMLTV has no programmes in the requested time window')
    channels = []
    for channel_id in sorted(schedules):
        programmes = sorted(schedules[channel_id], key=lambda item: item[0])
        channels.append({'id': channel_id, 'names': names.get(channel_id, []),
                         'programmes': programmes})
    return {
        'version': 1,
        'generated_at': int(now.timestamp() * 1000),
        'from': from_ms,
        'until': until_ms,
        'channels': channels,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--source', default=SOURCE, help='XMLTV .gz URL or local file')
    ap.add_argument('--output', default='epg.json.gz', help='Destination file')
    args = ap.parse_args()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    if args.source.startswith(('http://', 'https://')):
        request = urllib.request.Request(args.source, headers={'User-Agent': 'TV7-EPG-Compact/1.0'})
        remote = urllib.request.urlopen(request, timeout=45)
    else:
        remote = open(args.source, 'rb')
    with remote:
        with gzip.GzipFile(fileobj=LimitedStream(remote, MAX_COMPRESSED), mode='rb') as zipped:
            data = preprocess(LimitedStream(zipped, MAX_XML))
    fd, temporary = tempfile.mkstemp(prefix='.epg-', suffix='.gz', dir=output.parent)
    try:
        with os.fdopen(fd, 'wb') as dest:
            with gzip.GzipFile(filename='', fileobj=dest, mode='wb', mtime=0, compresslevel=9) as zipped:
                zipped.write(json.dumps(data, ensure_ascii=False, separators=(',', ':')).encode('utf-8'))
        os.replace(temporary, output)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    print(f"Created {output}: {output.stat().st_size:,} compressed bytes; "
          f"{len(data['channels'])} channels; "
          f"{sum(len(ch['programmes']) for ch in data['channels'])} programmes")


if __name__ == '__main__':
    main()
