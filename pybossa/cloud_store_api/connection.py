from copy import deepcopy
import ssl
import sys
import time

from flask import current_app
from boto.auth_handler import AuthHandler
import boto.auth

from boto.exception import S3ResponseError
from boto.s3.key import Key
from boto.s3.bucket import Bucket
from boto.s3.connection import S3Connection, OrdinaryCallingFormat
from boto.provider import Provider
import jwt
from werkzeug.exceptions import BadRequest
from boto3.session import Session
from botocore.client import Config
from pybossa.cloud_store_api.base_conn import BaseConnection


def check_store(store):
    if not store:
        return

    store_type = current_app.config.get("S3_CONN_TYPE")
    store_type_v2 = current_app.config.get("S3_CONN_TYPE_V2")
    if store not in [store_type, store_type_v2]:
        raise BadRequest(f"Unsupported store type {store}")

def create_connection(**kwargs):
    if kwargs.get("aws_secret_access_key"):
        masked_kwargs = {k:v for k, v in kwargs.items()}
        secret = kwargs["aws_secret_access_key"]
        masked_kwargs["aws_secret_access_key"] = f"{secret[:3]}{'x'*(len(secret)-6)}{secret[-3:]}"
        current_app.logger.info(f"create_connection kwargs: %s", str(masked_kwargs))
    else:
        current_app.logger.info(f"create_connection kwargs: %s", str(kwargs))

    store = kwargs.pop("store", None)
    check_store(store)
    store_type_v2 = current_app.config.get("S3_CONN_TYPE_V2")
    if store and store == store_type_v2:
        current_app.logger.info("Calling CustomConnectionV2")
        return CustomConnectionV2(
            aws_access_key_id=kwargs.get("aws_access_key_id"),
            aws_secret_access_key=kwargs.get("aws_secret_access_key"),
            endpoint=kwargs.get("endpoint"),
            cert=kwargs.get("cert", False),
            proxy_url=kwargs.get("proxy_url")
        )
    if 'object_service' in kwargs:
        current_app.logger.info("Calling ProxiedConnection")
        conn = ProxiedConnection(**kwargs)
    else:
        current_app.logger.info("Calling CustomConnection")
        conn = CustomConnection(**kwargs)
    return conn


class CustomProvider(Provider):
    """Extend Provider to carry information about the end service provider, in
       case the service is being proxied.
    """

    def __init__(self, name, access_key=None, secret_key=None,
                 security_token=None, profile_name=None, object_service=None,
                 auth_headers=None):
        self.object_service = object_service or name
        self.auth_headers = auth_headers
        super(CustomProvider, self).__init__(name, access_key, secret_key,
            security_token, profile_name)


class CustomConnection(S3Connection):

    def __init__(self, *args, **kwargs):
        if not kwargs.get('calling_format'):
            kwargs['calling_format'] = OrdinaryCallingFormat()

        kwargs['provider'] = CustomProvider('aws',
            kwargs.get('aws_access_key_id'),
            kwargs.get('aws_secret_access_key'),
            kwargs.get('security_token'),
            kwargs.get('profile_name'),
            kwargs.pop('object_service', None),
            kwargs.pop('auth_headers', None))

        kwargs['bucket_class'] = CustomBucket

        ssl_no_verify = kwargs.pop('s3_ssl_no_verify', False)
        self.host_suffix = kwargs.pop('host_suffix', '')

        super(CustomConnection, self).__init__(*args, **kwargs)

        if kwargs.get('is_secure', True) and ssl_no_verify:
            self.https_validate_certificates = False
            context = ssl._create_unverified_context()
            self.http_connection_kwargs['context'] = context

    def get_path(self, path='/', *args, **kwargs):
        ret = super(CustomConnection, self).get_path(path, *args, **kwargs)
        return self.host_suffix + ret


class CustomConnectionV2(BaseConnection):
    def __init__(
        self,
        aws_access_key_id,
        aws_secret_access_key,
        endpoint,
        cert,
        proxy_url
    ):
        self.client = Session().client(
            service_name="s3",
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            use_ssl=True,
            verify=cert,
            endpoint_url=endpoint,
            config=Config(
                proxies={"https": proxy_url, "http": proxy_url},
            ),
        )


class CustomBucket(Bucket):
    """Handle both 200 and 204 as response code"""

    def delete_key(self, *args, **kwargs):
        try:
            super(CustomBucket, self).delete_key(*args, **kwargs)
        except S3ResponseError as e:
            if e.status != 200:
                raise


class ProxiedKey(Key):

    def should_retry(self, response, chunked_transfer=False):
        if 200 <= response.status <= 299:
            return True
        return super(ProxiedKey, self).should_retry(response, chunked_transfer)


class ProxiedBucket(CustomBucket):

    def __init__(self, *args, **kwargs):
        super(ProxiedBucket, self).__init__(*args, **kwargs)
        self.set_key_class(ProxiedKey)


class ProxiedConnection(CustomConnection):
    """Object Store connection through proxy API. Sets the proper headers and
       creates the jwt; use the appropriate Bucket and Key classes.
    """

    def __init__(self, client_id, client_secret, object_service, *args, **kwargs):
        self.client_id = client_id
        self.client_secret = client_secret
        kwargs['object_service'] = object_service
        super(ProxiedConnection, self).__init__(*args, **kwargs)
        self.set_bucket_class(ProxiedBucket)

    def make_request(self, method, bucket='', key='', headers=None, data='',
            query_args=None, sender=None, override_num_retries=None,
            retry_handler=None):
        headers = headers or {}
        headers['jwt'] = self.create_jwt(method, self.host, bucket, key)
        headers['x-objectservice-id'] = self.provider.object_service.upper()
        current_app.logger.info("Calling ProxiedConnection.make_request. headers %s", str(headers))
        return super(ProxiedConnection, self).make_request(method, bucket, key,
            headers, data, query_args, sender, override_num_retries,
            retry_handler)

    def create_jwt(self, method, host, bucket, key):
        now = int(time.time())
        path = self.get_path(self.calling_format.build_path_base(bucket, key))
        current_app.logger.info("create_jwt called. method %s, host %s, bucket %s, key %s, path %s", method, host, str(bucket), str(key), str(path))
        payload = {
            'iat': now,
            'nbf': now,
            'exp': now + 300,
            'method': method,
            'iss': self.client_id,
            'host': host,
            'path': path,
            'region': 'ny'
        }
        return jwt.encode(payload, self.client_secret, algorithm='HS256')


class CustomAuthHandler(AuthHandler):
    """Implements sending of custom auth headers"""

    capability = ['s3']

    def __init__(self, host, config, provider):
        if not provider.auth_headers:
            raise boto.auth_handler.NotReadyToAuthenticate()
        self._provider = provider
        super(CustomAuthHandler, self).__init__(host, config, provider)

    def add_auth(self, http_request, **kwargs):
        headers = http_request.headers
        for header, attr in self._provider.auth_headers:
            headers[header] = getattr(self._provider, attr)

    def sign_string(self, *args, **kwargs):
        return ''
