from copy import deepcopy
import ssl
import sys
import time
import logging

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
from os import environ


def check_store(store):
    if not store:
        return

    store_type = current_app.config.get("S3_CONN_TYPE")
    store_type_v2 = current_app.config.get("S3_CONN_TYPE_V2")
    if store not in [store_type, store_type_v2]:
        raise BadRequest(f"Unsupported store type {store}")

def _mask_secret(secret):
    """Helper function to mask secrets for logging."""
    if not secret or len(secret) < 8:
        return "***masked***"
    return f"{secret[:3]}{'*'*(len(secret)-6)}{secret[-3:]}"


def create_connection(**kwargs):
    """Create boto connection with comprehensive logging for debugging."""

    # Log environment variables (masked)
    current_app.logger.info("=== Boto Connection Creation Start ===")

    # Check and log V2 environment variables
    v2_access = environ.get("AWS_V2_ACCESS_KEY_ID")
    v2_secret = environ.get("AWS_V2_SECRET_ACCESS_KEY")
    v2_region = environ.get("AWS_V2_REGION", "not_set")

    current_app.logger.info("AWS V2 Environment Variables:")
    current_app.logger.info("  AWS_V2_ACCESS_KEY_ID: %s", v2_access if v2_access else "not_set")
    current_app.logger.info("  AWS_V2_SECRET_ACCESS_KEY: %s", _mask_secret(v2_secret) if v2_secret else "not_set")
    current_app.logger.info("  AWS_V2_REGION: %s", v2_region)

    # Check and log standard AWS environment variables
    std_access = environ.get("AWS_ACCESS_KEY_ID")
    std_secret = environ.get("AWS_SECRET_ACCESS_KEY")
    std_region = environ.get("AWS_DEFAULT_REGION", environ.get("AWS_REGION", "not_set"))

    current_app.logger.info("Standard AWS Environment Variables:")
    current_app.logger.info("  AWS_ACCESS_KEY_ID: %s", std_access if std_access else "not_set")
    current_app.logger.info("  AWS_SECRET_ACCESS_KEY: %s", _mask_secret(std_secret) if std_secret else "not_set")
    current_app.logger.info("  AWS_DEFAULT_REGION/AWS_REGION: %s", std_region)

    # Log connection kwargs (mask secrets)
    masked_kwargs = {k: v for k, v in kwargs.items()}
    if "aws_secret_access_key" in masked_kwargs:
        masked_kwargs["aws_secret_access_key"] = _mask_secret(kwargs["aws_secret_access_key"])

    current_app.logger.info("Connection kwargs provided:")
    for key, value in masked_kwargs.items():
        current_app.logger.info("  %s: %s", key, value)

    # Log access key usage (from kwargs or env)
    access_key = kwargs.get("aws_access_key_id", std_access or v2_access or "not_provided")
    current_app.logger.info("Access Key to be used: %s", access_key)

    # Log connection settings
    endpoint = kwargs.get("endpoint", kwargs.get("host", "default_s3_endpoint"))
    current_app.logger.info("Connection Settings:")
    current_app.logger.info("  Endpoint/Host: %s", endpoint)
    current_app.logger.info("  Region: %s", kwargs.get("region", std_region))
    current_app.logger.info("  SSL Enabled: %s", kwargs.get("is_secure", True))
    current_app.logger.info("  SSL Verify: %s", not kwargs.get("s3_ssl_no_verify", False))
    current_app.logger.info("  Proxy URL: %s", kwargs.get("proxy_url", "not_set"))

    store = kwargs.pop("store", None)
    check_store(store)
    store_type_v2 = current_app.config.get("S3_CONN_TYPE_V2")

    current_app.logger.info("Store type: %s (V2 type: %s)", store, store_type_v2)

    if store and store == store_type_v2:
        current_app.logger.info("Creating CustomConnectionV2 (boto3)")
        return CustomConnectionV2(
            aws_access_key_id=kwargs.get("aws_access_key_id"),
            aws_secret_access_key=kwargs.get("aws_secret_access_key"),
            endpoint=kwargs.get("endpoint"),
            cert=kwargs.get("cert", False),
            proxy_url=kwargs.get("proxy_url")
        )
    if 'object_service' in kwargs:
        current_app.logger.info("Creating ProxiedConnection (boto2)")
        conn = ProxiedConnection(**kwargs)
    else:
        current_app.logger.info("Creating CustomConnection (boto2)")
        conn = CustomConnection(**kwargs)

    current_app.logger.info("=== Boto Connection Creation Complete ===")
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
        current_app.logger.info("CustomConnection.__init__ called")
        current_app.logger.info("  args count: %d", len(args))

        # Log connection parameters (mask secrets)
        log_kwargs = {k: v for k, v in kwargs.items()}
        if "aws_secret_access_key" in log_kwargs:
            log_kwargs["aws_secret_access_key"] = _mask_secret(kwargs.get("aws_secret_access_key"))
        current_app.logger.info("  kwargs: %s", log_kwargs)

        if not kwargs.get('calling_format'):
            kwargs['calling_format'] = OrdinaryCallingFormat()
            current_app.logger.info("  Using OrdinaryCallingFormat")

        kwargs['provider'] = CustomProvider('aws',
            kwargs.get('aws_access_key_id'),
            kwargs.get('aws_secret_access_key'),
            kwargs.get('security_token'),
            kwargs.get('profile_name'),
            kwargs.pop('object_service', None),
            kwargs.pop('auth_headers', None))

        current_app.logger.info("  Provider configured: aws_access_key_id=%s", kwargs['provider'].access_key)

        kwargs['bucket_class'] = CustomBucket

        ssl_no_verify = kwargs.pop('s3_ssl_no_verify', False)
        self.host_suffix = kwargs.pop('host_suffix', '')

        current_app.logger.info("  SSL no verify: %s", ssl_no_verify)
        current_app.logger.info("  Host suffix: %s", self.host_suffix)

        super(CustomConnection, self).__init__(*args, **kwargs)

        if kwargs.get('is_secure', True) and ssl_no_verify:
            self.https_validate_certificates = False
            context = ssl._create_unverified_context()
            self.http_connection_kwargs['context'] = context
            current_app.logger.info("  SSL verification disabled")

        current_app.logger.info("CustomConnection initialized: host=%s, port=%s", self.host, self.port)

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
        current_app.logger.info("CustomConnectionV2.__init__ called (boto3)")
        current_app.logger.info("  aws_access_key_id: %s", aws_access_key_id)
        current_app.logger.info("  aws_secret_access_key: %s", _mask_secret(aws_secret_access_key))
        current_app.logger.info("  endpoint: %s", endpoint)
        current_app.logger.info("  cert (SSL verify): %s", cert)
        current_app.logger.info("  proxy_url: %s", proxy_url)

        # Create boto3 session
        session = Session()
        current_app.logger.info("  boto3 Session created")

        # Build config for proxy
        config_kwargs = {}
        if proxy_url:
            config_kwargs['proxies'] = {"https": proxy_url, "http": proxy_url}
            current_app.logger.info("  Proxy configuration set: %s", config_kwargs['proxies'])

        self.client = session.client(
            service_name="s3",
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            use_ssl=True,
            verify=cert,
            endpoint_url=endpoint,
            config=Config(**config_kwargs) if config_kwargs else None,
        )

        current_app.logger.info("CustomConnectionV2 boto3 s3 client created successfully")
        current_app.logger.info("  Client endpoint: %s", self.client.meta.endpoint_url)
        current_app.logger.info("  Client region: %s", self.client.meta.region_name)


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
        current_app.logger.info("ProxiedConnection.__init__ called")
        current_app.logger.info("  client_id: %s", client_id)
        current_app.logger.info("  client_secret: %s", _mask_secret(client_secret))
        current_app.logger.info("  object_service: %s", object_service)

        self.client_id = client_id
        self.client_secret = client_secret
        kwargs['object_service'] = object_service
        super(ProxiedConnection, self).__init__(*args, **kwargs)
        self.set_bucket_class(ProxiedBucket)

        current_app.logger.info("ProxiedConnection initialized")

    def make_request(self, method, bucket='', key='', headers=None, data='',
            query_args=None, sender=None, override_num_retries=None,
            retry_handler=None):
        headers = headers or {}
        headers['jwt'] = self.create_jwt(method, self.host, bucket, key)
        headers['x-objectservice-id'] = self.provider.object_service.upper()

        current_app.logger.info("ProxiedConnection.make_request called")
        current_app.logger.info("  method: %s", method)
        current_app.logger.info("  bucket: %s", bucket)
        current_app.logger.info("  key: %s", key)
        current_app.logger.info("  x-objectservice-id: %s", headers['x-objectservice-id'])
        current_app.logger.info("  jwt token length: %d", len(headers['jwt']))

        return super(ProxiedConnection, self).make_request(method, bucket, key,
            headers, data, query_args, sender, override_num_retries,
            retry_handler)

    def create_jwt(self, method, host, bucket, key):
        now = int(time.time())
        path = self.get_path(self.calling_format.build_path_base(bucket, key))

        current_app.logger.info("ProxiedConnection.create_jwt called")
        current_app.logger.info("  method: %s", method)
        current_app.logger.info("  host: %s", host)
        current_app.logger.info("  bucket: %s", bucket)
        current_app.logger.info("  key: %s", key)
        current_app.logger.info("  path: %s", path)
        current_app.logger.info("  issuer (client_id): %s", self.client_id)

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
