"""Run directly with python3 test/test_chartist_assets.py."""

import hashlib
from html.parser import HTMLParser
from pathlib import Path
import re
import unittest
from urllib.parse import urlsplit

from flask import Flask, render_template_string


THEME = Path(__file__).resolve().parents[1] / 'pybossa/themes/default'
DASHBOARDS = ('dashboard.html', 'management_dashboard.html',
              'usage_dashboard.html')
RELEASE = 'vendor/chartist/0.11.0/'
CHECKSUMS = {
    'chartist.min.js':
        '5337df46e798872643c3c0a3dfd5029e7820bc17dad5f3dc0d0d1abaf09bbc27',
    'chartist.min.css':
        '4def7e69368bf63d14e4fccb86d007b7e497960213f0a4fd564c8e667ebc85a9',
}


class AssetParser(HTMLParser):

    def __init__(self):
        super().__init__()
        self.assets = []

    def handle_starttag(self, tag, attributes):
        if tag in ('script', 'link'):
            self.assets.append((tag, dict(attributes)))


class ChartistAssetsTest(unittest.TestCase):

    def setUp(self):
        self.app = Flask(__name__, static_folder=str(THEME / 'static'),
                         static_url_path='/static')

    def test_dashboards_load_local_script_and_stylesheet(self):
        for filename in DASHBOARDS:
            with self.subTest(dashboard=filename):
                source = (THEME / 'templates/admin' / filename).read_text()
                tags = re.findall(r'<(?:script|link)\b[^>]*>', source,
                                  flags=re.IGNORECASE)
                markup = '\n'.join(tag for tag in tags
                                   if 'chartist' in tag.lower())
                with self.app.test_request_context('/'):
                    rendered = render_template_string(markup)
                parser = AssetParser()
                parser.feed(rendered)
                self.assertEqual(len(parser.assets), 2)
                self.assertEqual({tag for tag, _ in parser.assets},
                                 {'script', 'link'})
                for tag, attributes in parser.assets:
                    address = attributes['src' if tag == 'script' else 'href']
                    parsed = urlsplit(address)
                    self.assertEqual(parsed.scheme, '')
                    self.assertEqual(parsed.netloc, '')
                    extension = 'js' if tag == 'script' else 'css'
                    self.assertEqual(parsed.path,
                                     '/static/' + RELEASE +
                                     'chartist.min.' + extension)
                    if tag == 'link':
                        self.assertEqual(attributes['rel'], 'stylesheet')
                    with self.app.test_client().get(address) as response:
                        self.assertEqual(response.status_code, 200)

    def test_dashboards_do_not_reference_the_chartist_cdn(self):
        for filename in DASHBOARDS:
            with self.subTest(dashboard=filename):
                source = (THEME / 'templates/admin' / filename).read_text()
                self.assertFalse('cdn.jsdelivr.net/chartist.js' in source,
                                 filename)

    def test_served_assets_match_the_reviewed_release(self):
        client = self.app.test_client()
        for filename, checksum in CHECKSUMS.items():
            with self.subTest(asset=filename):
                with client.get('/static/' + RELEASE + filename) as response:
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(hashlib.sha256(response.data).hexdigest(),
                                     checksum)


if __name__ == '__main__':
    unittest.main()
