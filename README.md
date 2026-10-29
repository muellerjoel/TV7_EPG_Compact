# TV7 Compact EPG public publisher

Publishes publicly available TV programme guide data as a compact GZIP-compressed
JSON file, using the XMLTV feed from
[mathewmeconry/TV7_EPG_Data](https://github.com/mathewmeconry/TV7_EPG_Data)
(MIT license). No private TV7 Android code is included here.

The workflow runs once daily after the upstream's scheduled nightly update.
Manual run: **Actions** -> **Update compact TV7 EPG** -> **Run workflow**.

Output URL after first successful run:

`https://raw.githubusercontent.com/muellerjoel/TV7_EPG_Compact/main/epg.json.gz`

Python 3.11+ only, no third-party dependencies. To run locally:

```bash
python3 -m unittest discover -s tests -v
python3 scripts/prepare_epg.py --output epg.json.gz
```

Format `version=1`: `generated_at`, `from`, `until` are Unix timestamps in
milliseconds. `channels` array contains objects with `id`, `names`, and
`programmes` where each programme is `[startMs, endMs, title, subtitle, desc]`.
The guide covers the current day and the next day in Europe/Zurich plus 6h.
