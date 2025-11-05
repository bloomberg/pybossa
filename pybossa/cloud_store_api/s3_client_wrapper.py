from urllib.parse import urlsplit, urlunsplit
from botocore.exceptions import ClientError
from botocore.config import Config
import boto3
from pybossa.cloud_store_api.base_s3_client import BaseS3Client


class S3ClientWrapper(BaseS3Client):
    """
    A thin wrapper around boto3's S3 client that emulates the old boto2 behavior:
      - path-style addressing (OrdinaryCallingFormat)
      - ability to disable SSL cert verification (s3_ssl_no_verify)
      - prepend a host_suffix to every request path
      - inject custom auth headers on every request
      - tolerant delete (treat 200/204 as success)
    """

    def __init__(
        self,
        auth_headers=None,     # dict of headers to inject into every request
        object_service=None,   # kept for API compatibility; not used by boto3 directly
        **kwargs
    ):
        # Convert auth_headers to dict if it's a list of tuples
        if isinstance(auth_headers, list):
            self.auth_headers = dict(auth_headers)
        else:
            self.auth_headers = auth_headers or {}

        # Initialize parent class with all other parameters
        super().__init__(**kwargs)

    def _should_register_hooks(self):
        """Register hooks if we have auth_headers or host_suffix."""
        return bool(self.auth_headers or self.host_suffix)

    # --- event hooks ---

    def _before_sign_hook(self, request, **kwargs):
        """
        Runs before the request is signed. We can:
          - add custom headers
          - modify the URL to add a path prefix (host_suffix)
        """
        # Inject headers first
        if self.auth_headers:
            for k, v in self.auth_headers.items():
                # Don't clobber existing values unless we mean to
                if v is not None:
                    request.headers[k] = str(v)

        # Apply host_suffix from base class
        super()._before_sign_hook(request, **kwargs)

    # --- convenience helpers mirroring old usage ---

    def build_base_http_request(self, method, path, auth_path, headers=None):
        """
        Build a base HTTP request object for testing purposes.
        This provides compatibility with legacy boto2-style interface.
        """
        return MockHTTPRequest(method, path, auth_path, headers or {})

    # Inherited methods from BaseS3Client:
    # - delete_key(bucket, key)
    # - get_object(bucket, key, **kwargs)
    # - put_object(bucket, key, body, **kwargs)
    # - list_objects(bucket, prefix="", **kwargs)
    # - raw()


class MockHTTPRequest:
    """Mock HTTP request object to support legacy test interface."""

    def __init__(self, method, path, auth_path, headers):
        self.method = method
        self.path = path
        self.auth_path = auth_path
        self.headers = headers.copy()

    def authorize(self, connection):
        """
        Authorize the request by processing auth_headers.
        This simulates the legacy boto2 authorization behavior.
        """
        if hasattr(connection, 'auth_headers'):
            for key, value in connection.auth_headers.items():
                # Special handling: if value is 'access_key', replace with actual access key
                if value == 'access_key':
                    if hasattr(connection, 'aws_access_key_id') and connection.aws_access_key_id:
                        self.headers[key] = connection.aws_access_key_id
                    else:
                        self.headers[key] = value
                else:
                    self.headers[key] = value

