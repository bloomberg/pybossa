import logging
import socket
import unittest
from unittest.mock import MagicMock, patch

from flask import Flask

from pybossa.importers import BulkImportException
from pybossa.importers.iiif import BulkTaskIIIFImporter


class TestIIIFImporterSecurity(unittest.TestCase):

    def setUp(self):
        self.app = Flask(__name__)
        self.app.logger.setLevel(logging.INFO)
        self.manifest_uri = 'https://iiif.example.com/manifest'
        self.importer = BulkTaskIIIFImporter(self.manifest_uri, '2.1')

    @patch('pybossa.ssrf_guard.requests.Session.request')
    @patch('pybossa.ssrf_guard.socket.getaddrinfo')
    def test_private_target_is_blocked_before_request(self, getaddrinfo,
                                                      request):
        getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('10.0.0.7', 443))
        ]
        request.return_value = MagicMock(status_code=200,
                                         text='not a manifest')

        with self.app.app_context(), self.assertRaises(BulkImportException):
            self.importer._get_validated_manifest(self.manifest_uri, '2.1')

        request.assert_not_called()

    @patch('pybossa.ssrf_guard.requests.Session.request')
    @patch('pybossa.ssrf_guard.socket.getaddrinfo')
    def test_fetch_disables_redirects_and_sets_timeout(self, getaddrinfo,
                                                       request):
        getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, '',
             ('93.184.216.34', 443))
        ]
        request.return_value = MagicMock(status_code=404, text='missing')

        with self.app.app_context(), self.assertRaises(BulkImportException):
            self.importer._get_validated_manifest(self.manifest_uri, '2.1')

        request.assert_called_once_with(
            'get',
            self.manifest_uri,
            timeout=(5, 10),
            allow_redirects=False,
        )

    @patch('pybossa.importers.iiif.ManifestReader')
    @patch('pybossa.ssrf_guard.requests.Session.request')
    @patch('pybossa.ssrf_guard.socket.getaddrinfo')
    def test_parser_error_is_generic_for_user(self, getaddrinfo, request,
                                              reader):
        internal_detail = 'INTERNAL-RESPONSE-DETAIL'
        getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, '',
             ('93.184.216.34', 443))
        ]
        request.return_value = MagicMock(status_code=200, text='invalid')
        reader.return_value.read.side_effect = Exception(internal_detail)

        with self.app.app_context(), \
                self.assertLogs(self.app.logger, level='ERROR') as captured:
            with self.assertRaises(BulkImportException) as raised:
                self.importer._get_validated_manifest(
                    self.manifest_uri, '2.1')

        self.assertEqual(str(raised.exception), 'Unable to parse IIIF manifest')
        self.assertNotIn(internal_detail, str(raised.exception))
        self.assertIn(internal_detail, '\n'.join(captured.output))


if __name__ == '__main__':
    unittest.main()
