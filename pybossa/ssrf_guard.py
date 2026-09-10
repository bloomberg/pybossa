"""SSRF protection for outbound HTTP requests."""
import ipaddress
import socket
from urllib.parse import urlparse

import requests
from flask import current_app
from requests.adapters import HTTPAdapter
from requests.utils import select_proxy
from urllib3.connectionpool import HTTPConnectionPool, HTTPSConnectionPool


class SSRFError(Exception):
    pass


class SSRFBlockedAddress(SSRFError):
    pass


class SSRFInvalidScheme(SSRFError):
    pass


class SSRFDomainNotAllowed(SSRFError):
    pass


class _PinnedIPAdapter(HTTPAdapter):

    def __init__(self, scheme, hostname, port, pinned_ip):
        self.scheme = scheme
        self.hostname = hostname
        self.port = port
        self.pinned_ip = pinned_ip
        super().__init__()
        pool_class = (HTTPSConnectionPool if scheme == 'https'
                      else HTTPConnectionPool)
        pool_kwargs = self._pool_kwargs()
        self.direct_pool = pool_class(
            pinned_ip,
            port=port,
            maxsize=self._pool_maxsize,
            block=self._pool_block,
            **pool_kwargs)

    def get_connection(self, url, proxies=None):
        self._validate_origin(url)
        proxy = select_proxy(url, proxies)
        if proxy and self.scheme == 'https':
            manager = self.proxy_manager_for(proxy)
            return manager.connection_from_host(
                self.pinned_ip,
                port=self.port,
                scheme=self.scheme,
                pool_kwargs=self._pool_kwargs())
        return self.direct_pool

    def request_url(self, request, proxies):
        return request.path_url

    def add_headers(self, request, **kwargs):
        request.headers['Host'] = self._host_header()

    def close(self):
        self.direct_pool.close()
        super().close()

    def _pool_kwargs(self):
        if self.scheme == 'https':
            return {
                'assert_hostname': self.hostname,
                'server_hostname': self.hostname,
            }
        return {}

    def _validate_origin(self, url):
        parsed = urlparse(url)
        port = parsed.port or (443 if parsed.scheme == 'https' else 80)
        if (parsed.scheme.lower(), parsed.hostname, port) != (
                self.scheme, self.hostname, self.port):
            raise SSRFError('Request target changed after SSRF validation')

    def _host_header(self):
        default_port = 443 if self.scheme == 'https' else 80
        if self.port == default_port:
            return self.hostname
        return '{}:{}'.format(self.hostname, self.port)


def validate_url(url):
    """Validate URL scheme, hostname structure, and domain allowlist.

    Returns (scheme, hostname, port) on success. Raises SSRFError subclass on failure.
    """
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    hostname = parsed.hostname

    if current_app.config.get('WEBHOOK_HTTPS_ONLY', True):
        if scheme != 'https':
            raise SSRFInvalidScheme(
                "Only HTTPS webhook URLs are allowed, got '{}'".format(scheme))
    else:
        if scheme not in ('http', 'https'):
            raise SSRFInvalidScheme(
                "Webhook URL scheme must be http or https, got '{}'".format(scheme))

    if not hostname or '.' not in hostname:
        raise SSRFError("Invalid hostname in webhook URL")

    allowed = current_app.config.get('WEBHOOK_ALLOWED_DOMAINS', [])
    if allowed and hostname not in allowed:
        raise SSRFDomainNotAllowed(
            "Domain '{}' is not in the webhook allowlist".format(hostname))

    port = parsed.port or (443 if scheme == 'https' else 80)
    return scheme, hostname, port


def validate_ip(ip_str):
    """Raise SSRFBlockedAddress if an IP is not globally routable."""
    if not current_app.config.get('WEBHOOK_BLOCK_PRIVATE_IPS', True):
        return

    addr = ipaddress.ip_address(ip_str)

    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        addr = addr.ipv4_mapped

    if not addr.is_global or addr.is_private or addr.is_loopback or addr.is_link_local \
            or addr.is_multicast or addr.is_reserved or addr.is_unspecified:
        raise SSRFBlockedAddress(
            "Webhook target resolves to blocked address: {}".format(ip_str))


def resolve_and_validate(hostname, port=443):
    """Resolve hostname and validate all returned IPs against blocklists.

    Returns first resolved IP string on success.
    """
    try:
        results = socket.getaddrinfo(hostname, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except socket.gaierror as e:
        raise SSRFError("DNS resolution failed for '{}': {}".format(hostname, e))

    if not results:
        raise SSRFError("DNS resolution returned no results for '{}'".format(hostname))

    for family, socktype, proto, canonname, sockaddr in results:
        ip_str = sockaddr[0]
        validate_ip(ip_str)

    return results[0][4][0]


def safe_post(url, **kwargs):
    """POST to the validated IP while preserving the URL hostname."""
    return _safe_request('post', url, **kwargs)


def safe_get(url, **kwargs):
    """GET from the validated IP while preserving the URL hostname."""
    return _safe_request('get', url, **kwargs)


def _safe_request(method, url, **kwargs):
    scheme, hostname, port = validate_url(url)
    pinned_ip = resolve_and_validate(hostname, port)
    kwargs.setdefault('timeout', _get_timeout())
    kwargs['allow_redirects'] = False
    if kwargs.get('stream'):
        raise SSRFError('Streaming SSRF-safe requests is not supported')

    adapter = _PinnedIPAdapter(scheme, hostname, port, pinned_ip)
    with requests.Session() as session:
        session.mount('{}://'.format(scheme), adapter)
        return session.request(method, url, **kwargs)


def _validate_before_request(url):
    scheme, hostname, port = validate_url(url)
    resolve_and_validate(hostname, port)


def _get_timeout():
    connect = current_app.config.get('WEBHOOK_CONNECT_TIMEOUT', 5)
    read = current_app.config.get('WEBHOOK_READ_TIMEOUT', 10)
    return (connect, read)
