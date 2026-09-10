import ssl
from http import client as http_client

from boto.utils import parse_host


def _ssl_context(connection):
    if connection.https_validate_certificates:
        return ssl.create_default_context(
            cafile=connection.ca_certificates_file)
    return ssl._create_unverified_context()


def new_http_connection_py3(connection, host, port, is_secure):
    if host is None:
        host = connection.server_name()
    host = parse_host(host)

    if is_secure:
        context = _ssl_context(connection)
        if connection.use_proxy and not connection.skip_proxy(host):
            proxied_connection = http_client.HTTPSConnection(
                connection.proxy, int(connection.proxy_port), context=context)
            proxied_connection.set_tunnel(host, port)
            return proxied_connection
        return http_client.HTTPSConnection(host, port, context=context)

    if connection.use_proxy and not connection.skip_proxy(host):
        host = connection.proxy
        port = int(connection.proxy_port)
    return http_client.HTTPConnection(host, port)
