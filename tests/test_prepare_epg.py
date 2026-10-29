import gzip
import io
import unittest
from datetime import datetime, timezone
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

if __name__ == '__main__':
    unittest.main()
