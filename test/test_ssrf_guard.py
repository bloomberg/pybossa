# -*- coding: utf8 -*-
import socket
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from unittest.mock import patch, MagicMock

from test import with_context, with_context_settings, with_request_context
from pybossa.forms.validator import Webhook
from pybossa.ssrf_guard import (
    validate_url, validate_ip, resolve_and_validate,
    safe_post, safe_get,
    SSRFError, SSRFBlockedAddress, SSRFInvalidScheme, SSRFDomainNotAllowed,
    _PinnedIPAdapter,
)
import pytest
from wtforms.validators import ValidationError


class TestValidateUrl:

    @with_context
    def test_https_url_accepted(self):
        scheme, hostname, port = validate_url('https://example.com/hook')
        assert scheme == 'https'
        assert hostname == 'example.com'
        assert port == 443

    @with_context
    def test_http_url_rejected_when_https_only(self):
        with pytest.raises(SSRFInvalidScheme):
            validate_url('http://example.com/hook')

    @with_context_settings(WEBHOOK_HTTPS_ONLY=False)
    def test_http_url_accepted_when_https_only_disabled(self):
        scheme, hostname, port = validate_url('http://example.com/hook')
        assert scheme == 'http'
        assert port == 80

    @with_context
    def test_ftp_scheme_rejected(self):
        with pytest.raises(SSRFInvalidScheme):
            validate_url('ftp://example.com/file')

    @with_context
    def test_empty_scheme_rejected(self):
        with pytest.raises(SSRFInvalidScheme):
            validate_url('://example.com')

    @with_context
    def test_no_hostname_rejected(self):
        with pytest.raises(SSRFError):
            validate_url('https://')

    @with_context
    def test_bare_hostname_no_dot_rejected(self):
        with pytest.raises(SSRFError):
            validate_url('https://localhost/path')

    @with_context_settings(WEBHOOK_ALLOWED_DOMAINS=['hooks.example.com'])
    def test_domain_in_allowlist_accepted(self):
        scheme, hostname, port = validate_url('https://hooks.example.com/wh')
        assert hostname == 'hooks.example.com'

    @with_context_settings(WEBHOOK_ALLOWED_DOMAINS=['hooks.example.com'])
    def test_domain_not_in_allowlist_rejected(self):
        with pytest.raises(SSRFDomainNotAllowed):
            validate_url('https://evil.com/wh')

    @with_context_settings(WEBHOOK_ALLOWED_DOMAINS=[])
    def test_empty_allowlist_permits_all(self):
        scheme, hostname, port = validate_url('https://any.domain.com/wh')
        assert hostname == 'any.domain.com'

    @with_context
    def test_custom_port_extracted(self):
        scheme, hostname, port = validate_url('https://example.com:8443/hook')
        assert port == 8443


class TestValidateIp:

    @with_context
    def test_public_ip_passes(self):
        validate_ip('8.8.8.8')

    @with_context
    def test_loopback_blocked(self):
        with pytest.raises(SSRFBlockedAddress):
            validate_ip('127.0.0.1')

    @with_context
    def test_private_10_blocked(self):
        with pytest.raises(SSRFBlockedAddress):
            validate_ip('10.0.0.1')

    @with_context
    def test_private_172_blocked(self):
        with pytest.raises(SSRFBlockedAddress):
            validate_ip('172.16.0.1')

    @with_context
    def test_private_192_blocked(self):
        with pytest.raises(SSRFBlockedAddress):
            validate_ip('192.168.1.1')

    @with_context
    def test_shared_address_space_blocked(self):
        with pytest.raises(SSRFBlockedAddress):
            validate_ip('100.64.0.1')

    @with_context
    def test_link_local_blocked(self):
        with pytest.raises(SSRFBlockedAddress):
            validate_ip('169.254.1.1')

    @with_context
    def test_multicast_blocked(self):
        with pytest.raises(SSRFBlockedAddress):
            validate_ip('224.0.0.1')

    @with_context
    def test_ipv6_loopback_blocked(self):
        with pytest.raises(SSRFBlockedAddress):
            validate_ip('::1')

    @with_context
    def test_ipv6_private_blocked(self):
        with pytest.raises(SSRFBlockedAddress):
            validate_ip('fd00::1')

    @with_context
    def test_ipv4_mapped_ipv6_private_blocked(self):
        with pytest.raises(SSRFBlockedAddress):
            validate_ip('::ffff:127.0.0.1')

    @with_context_settings(WEBHOOK_BLOCK_PRIVATE_IPS=False)
    def test_private_ip_allowed_when_blocking_disabled(self):
        validate_ip('127.0.0.1')


class TestResolveAndValidate:

    @with_context
    @patch('pybossa.ssrf_guard.socket.getaddrinfo')
    def test_public_ip_passes(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 443))
        ]
        ip = resolve_and_validate('example.com', 443)
        assert ip == '93.184.216.34'

    @with_context
    @patch('pybossa.ssrf_guard.socket.getaddrinfo')
    def test_private_ip_blocked(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('127.0.0.1', 443))
        ]
        with pytest.raises(SSRFBlockedAddress):
            resolve_and_validate('evil.com', 443)

    @with_context
    @patch('pybossa.ssrf_guard.socket.getaddrinfo')
    def test_dns_failure_raises(self, mock_getaddrinfo):
        mock_getaddrinfo.side_effect = socket.gaierror('Name resolution failed')
        with pytest.raises(SSRFError, match='DNS resolution failed'):
            resolve_and_validate('nonexistent.invalid', 443)

    @with_context
    @patch('pybossa.ssrf_guard.socket.getaddrinfo')
    def test_multiple_ips_all_checked(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('8.8.8.8', 443)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('10.0.0.1', 443)),
        ]
        with pytest.raises(SSRFBlockedAddress):
            resolve_and_validate('mixed.example.com', 443)


class TestWebhookValidator:

    @with_context
    @patch('pybossa.ssrf_guard.requests.Session.request')
    @patch('pybossa.ssrf_guard.socket.getaddrinfo')
    def test_valid_url_is_not_fetched(self, mock_getaddrinfo, mock_request):
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 443))
        ]
        mock_request.return_value = MagicMock(status_code=200)

        Webhook()(None, MagicMock(data='https://example.com/hook'))

        mock_request.assert_not_called()

    @with_request_context
    @patch('pybossa.ssrf_guard.socket.getaddrinfo')
    def test_private_target_is_rejected(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('10.0.0.1', 443))
        ]

        with pytest.raises(ValidationError, match='Invalid URL'):
            Webhook()(None, MagicMock(data='https://internal.example.com/hook'))


class TestSafePost:

    @with_context
    @patch('pybossa.ssrf_guard.requests.Session.request')
    @patch('pybossa.ssrf_guard.socket.getaddrinfo')
    def test_success(self, mock_getaddrinfo, mock_request):
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 443))
        ]
        mock_request.return_value = MagicMock(status_code=200, text='ok')
        resp = safe_post('https://example.com/hook', data='{}')
        assert resp.status_code == 200
        mock_request.assert_called_once()
        call_kwargs = mock_request.call_args[1]
        assert call_kwargs['allow_redirects'] is False
        assert call_kwargs['timeout'] == (5, 10)

    @with_context
    @patch('pybossa.ssrf_guard.requests.Session.request')
    @patch('pybossa.ssrf_guard.socket.getaddrinfo')
    def test_ssrf_blocked_no_request_made(self, mock_getaddrinfo, mock_request):
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('10.0.0.1', 443))
        ]
        with pytest.raises(SSRFBlockedAddress):
            safe_post('https://internal.example.com/hook', data='{}')
        mock_request.assert_not_called()

    @with_context
    @patch('pybossa.ssrf_guard.requests.Session.request')
    def test_invalid_scheme_no_dns_lookup(self, mock_request):
        with pytest.raises(SSRFInvalidScheme):
            safe_post('http://example.com/hook', data='{}')
        mock_request.assert_not_called()

    @with_context_settings(WEBHOOK_CONNECT_TIMEOUT=3, WEBHOOK_READ_TIMEOUT=7)
    @patch('pybossa.ssrf_guard.requests.Session.request')
    @patch('pybossa.ssrf_guard.socket.getaddrinfo')
    def test_custom_timeout_from_config(self, mock_getaddrinfo, mock_request):
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 443))
        ]
        mock_request.return_value = MagicMock(status_code=200)
        safe_post('https://example.com/hook', data='{}')
        call_kwargs = mock_request.call_args[1]
        assert call_kwargs['timeout'] == (3, 7)


class TestSafeGet:

    def test_https_pool_pins_ip_and_preserves_tls_hostname(self):
        adapter = _PinnedIPAdapter(
            'https', 'example.com', 443, '93.184.216.34')
        try:
            pool = adapter.get_connection('https://example.com/path', {})
            connection = pool._new_conn()
            assert pool.host == '93.184.216.34'
            assert connection.host == '93.184.216.34'
            assert connection.server_hostname == 'example.com'
            assert connection.assert_hostname == 'example.com'
            request = MagicMock(headers={})
            adapter.add_headers(request)
            assert request.headers['Host'] == 'example.com'
        finally:
            adapter.close()

    def test_https_proxy_receives_pinned_ip(self):
        adapter = _PinnedIPAdapter(
            'https', 'example.com', 443, '93.184.216.34')
        manager = MagicMock()
        manager.connection_from_host.return_value = MagicMock()
        try:
            with patch.object(adapter, 'proxy_manager_for',
                              return_value=manager):
                adapter.get_connection(
                    'https://example.com/path',
                    {'https': 'http://proxy.example.com:8080'})
            manager.connection_from_host.assert_called_once_with(
                '93.184.216.34',
                port=443,
                scheme='https',
                pool_kwargs={
                    'assert_hostname': 'example.com',
                    'server_hostname': 'example.com',
                })
        finally:
            adapter.close()

    @with_context_settings(
        WEBHOOK_HTTPS_ONLY=False,
        WEBHOOK_BLOCK_PRIVATE_IPS=False)
    def test_connection_is_pinned_to_validated_ip(self):
        class Handler(BaseHTTPRequestHandler):

            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'ok')

            def log_message(self, format, *args):
                pass

        server = HTTPServer(('127.0.0.1', 0), Handler)
        server_thread = Thread(target=server.serve_forever)
        server_thread.start()
        real_getaddrinfo = socket.getaddrinfo
        hostname_lookups = []

        def rebinding_getaddrinfo(host, port, *args, **kwargs):
            if host == 'rebind.example.com':
                hostname_lookups.append(host)
                address = ('127.0.0.1' if len(hostname_lookups) == 1
                           else '127.0.0.2')
                return real_getaddrinfo(address, port, *args, **kwargs)
            return real_getaddrinfo(host, port, *args, **kwargs)

        try:
            with patch('socket.getaddrinfo', side_effect=rebinding_getaddrinfo):
                response = safe_get(
                    'http://rebind.example.com:{}'.format(server.server_port),
                    proxies={'http': None, 'https': None, 'all': None})
            assert response.status_code == 200
            assert response.text == 'ok'
            assert hostname_lookups == ['rebind.example.com']
        finally:
            server.shutdown()
            server.server_close()
            server_thread.join()

    @with_context
    @patch('pybossa.ssrf_guard.requests.Session.request')
    @patch('pybossa.ssrf_guard.socket.getaddrinfo')
    def test_success(self, mock_getaddrinfo, mock_request):
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 443))
        ]
        mock_request.return_value = MagicMock(status_code=200, text='ok')
        resp = safe_get('https://example.com/hook')
        assert resp.status_code == 200
        call_kwargs = mock_request.call_args[1]
        assert call_kwargs['allow_redirects'] is False

    @with_context
    @patch('pybossa.ssrf_guard.requests.Session.request')
    @patch('pybossa.ssrf_guard.socket.getaddrinfo')
    def test_ssrf_blocked(self, mock_getaddrinfo, mock_request):
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('192.168.0.1', 443))
        ]
        with pytest.raises(SSRFBlockedAddress):
            safe_get('https://internal.example.com/hook')
        mock_request.assert_not_called()
