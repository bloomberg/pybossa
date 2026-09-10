import ssl
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from pybossa.cloud_store_api.boto_compat import new_http_connection_py3


class TestBotoCompat(unittest.TestCase):

    @staticmethod
    def _connection(validate_certificates=True, ca_certificates_file=None):
        return SimpleNamespace(
            https_validate_certificates=validate_certificates,
            ca_certificates_file=ca_certificates_file,
            use_proxy=True,
            proxy='proxy.test',
            proxy_port=8080,
            skip_proxy=lambda host: False,
            server_name=lambda: 'storage.test')

    def test_proxied_https_verifies_certificates(self):
        connection = self._connection()

        result = new_http_connection_py3(
            connection, 'storage.test', 443, True)

        self.assertEqual(result._context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(result._context.check_hostname)
        self.assertEqual(result._tunnel_host, 'storage.test')

    def test_proxied_https_honors_explicit_no_verify(self):
        connection = self._connection(validate_certificates=False)

        result = new_http_connection_py3(
            connection, 'storage.test', 443, True)

        self.assertEqual(result._context.verify_mode, ssl.CERT_NONE)
        self.assertFalse(result._context.check_hostname)

    def test_proxied_https_uses_configured_ca_file(self):
        ca_file = '/opt/bbinfra/etc/ssl/ca-certificates.crt'
        context = ssl.create_default_context()
        connection = self._connection(ca_certificates_file=ca_file)

        with patch(
                'pybossa.cloud_store_api.boto_compat.ssl.create_default_context',
                return_value=context) as create_default_context:
            result = new_http_connection_py3(
                connection, 'storage.test', 443, True)

        create_default_context.assert_called_once_with(cafile=ca_file)
        self.assertIs(result._context, context)


if __name__ == '__main__':
    unittest.main()
