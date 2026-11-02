import gzip
import io
import unittest
from datetime import datetime, timedelta, timezone
from scripts.prepare_epg import preprocess, epg_time

class TestCompactEpg(unittest.TestCase):
    def test_timezone(self):
        self.assertEqual(epg_time('20261029200000 +0100'),
                         int(datetime(2026, 10, 29, 19, tzinfo=timezone.utc).timestamp()*1000))
        self.assertIsNone(epg_time('bad'))

    def test_programmes_and_names(self):
        xml = b'''<tv>
        <channel id="srf"><display-name>SRF 1</display-name></channel>
        <programme channel="srf" start="20261029193000 +0100" stop="20261029203000 +0100">
          <title lang="de">Tagesschau</title><desc>Neuigkeiten</desc>
        </programme>
        <programme channel="srf" start="20261110193000 +0100" stop="20261110203000 +0100">
          <title>Too far away</title>
        </programme></tv>'''
        now = datetime(2026, 10, 29, 11, tzinfo=timezone.utc)
        payload = preprocess(io.BytesIO(xml), now=now)
        self.assertEqual(payload['version'], 1)
        self.assertEqual(payload['channels'][0]['names'], ['SRF 1'])
        self.assertEqual(payload['channels'][0]['programmes'][0][2], 'Tagesschau')
        self.assertEqual(len(payload['channels'][0]['programmes']), 1)

    def test_exact_two_days_back_and_ahead(self):
        now = datetime(2026, 11, 2, 12, tzinfo=timezone.utc)
        xml = b'''<tv>
          <channel id="srf"><display-name>SRF</display-name></channel>
          <programme channel="srf" start="20261031100000 +0000" stop="20261031115959 +0000">
            <title>Expired</title>
          </programme>
          <programme channel="srf" start="20261031110000 +0000" stop="20261031120100 +0000">
            <title>Past</title>
          </programme>
          <programme channel="srf" start="20261104115900 +0000" stop="20261104130000 +0000">
            <title>Future</title>
          </programme>
          <programme channel="srf" start="20261104120000 +0000" stop="20261104130000 +0000">
            <title>Beyond future window</title>
          </programme>
        </tv>'''
        payload = preprocess(io.BytesIO(xml), now=now)
        self.assertEqual(payload['from'], int((now - timedelta(hours=48)).timestamp() * 1000))
        self.assertEqual(payload['until'], int((now + timedelta(hours=48)).timestamp() * 1000))
        self.assertEqual(
            [item[2] for item in payload['channels'][0]['programmes']],
            ['Past', 'Future'])

    def test_more_than_20000_programmes(self):
        # Reproduce the 20,001-programme crash reported in GitHub Actions.
        now = datetime(2026, 11, 2, 12, tzinfo=timezone.utc)
        programme = (b'<programme channel="%03d" start="20261102130000 +0000" '
                     b'stop="20261102133000 +0000"><title>Show</title></programme>')
        xml = io.BytesIO()
        xml.write(b'<tv>')
        for channel in range(101):
            xml.write(b'<channel id="%03d"><display-name>Channel</display-name></channel>' % channel)
            for _ in range(201):
                xml.write(programme % channel)
        xml.write(b'</tv>')
        xml.seek(0)
        payload = preprocess(xml, now=now)
        self.assertEqual(len(payload['channels']), 101)
        self.assertEqual(sum(len(ch['programmes']) for ch in payload['channels']), 20301)

    def test_per_channel_cap_prefers_newer_entries(self):
        from scripts.prepare_epg import MAX_PER_CHANNEL
        now = datetime(2026, 11, 2, 12, tzinfo=timezone.utc)
        xml = io.BytesIO()
        xml.write(b'<tv><channel id="a"><display-name>A</display-name></channel>')
        base = now - timedelta(hours=40)
        for index in reversed(range(MAX_PER_CHANNEL + 20)):
            start = base + timedelta(minutes=5 * index)
            stop = start + timedelta(minutes=5)
            programme = (
                f'<programme channel="a" start="{start:%Y%m%d%H%M%S} +0000" '
                f'stop="{stop:%Y%m%d%H%M%S} +0000"><title>{index}</title></programme>'
            )
            xml.write(programme.encode('utf-8'))
        xml.write(b'</tv>')
        xml.seek(0)
        payload = preprocess(xml, now=now)
        programmes = payload['channels'][0]['programmes']
        self.assertEqual(len(programmes), MAX_PER_CHANNEL)
        self.assertEqual(programmes[0][2], '20')
        self.assertEqual(programmes[-1][2], str(MAX_PER_CHANNEL + 19))

if __name__ == '__main__':
    unittest.main()
