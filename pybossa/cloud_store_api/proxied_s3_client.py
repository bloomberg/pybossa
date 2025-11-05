from typing import Optional, Dict
from urllib.parse import urlsplit, urlunsplit
from botocore.exceptions import ClientError
from botocore.config import Config
import boto3
import time
import jwt
import logging
from pybossa.cloud_store_api.base_s3_client import BaseS3Client


class ProxiedS3Client(BaseS3Client):
    """
    Emulates the old ProxiedConnection/ProxiedBucket/ProxiedKey behavior using boto3.

    Features:
      - Path-style addressing (OrdinaryCallingFormat equivalent)
      - Optional SSL verification disable
      - host_suffix is prepended to every request path (like get_path() override)
      - Per-request JWT header and x-objectservice-id header
      - Delete tolerant of HTTP 200 and 204
    """

    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        object_service: str,
        region_claim: str = "ny",               # value used in the JWT "region" claim
        extra_headers: Optional[Dict[str, str]] = None,      # any additional headers to inject
        logger: Optional[logging.Logger] = None,
        **kwargs
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.object_service = object_service
        self.region_claim = region_claim
        self.extra_headers = extra_headers or {}
        self.logger = logger

        # Initialize parent class with all parameters
        super().__init__(**kwargs)

    def _should_register_hooks(self):
        """Always register hooks for JWT and header injection."""
        return True

    # ---------------------------
    # Event hook: adjust request
    # ---------------------------
    def _before_sign_hook(self, request, operation_name, **kwargs):
        """
        request: botocore.awsrequest.AWSRequest
        operation_name: e.g. "GetObject", "PutObject", etc.
        """
        # Apply host_suffix from base class first
        super()._before_sign_hook(request, **kwargs)

        # Get updated URL parts after host_suffix application
        parts = urlsplit(request.url)
        method = request.method
        host = parts.netloc
        path_for_jwt = parts.path  # include the prefixed path exactly as sent

        # Build headers (x-objectservice-id + any extra)
        headers = dict(self.extra_headers)
        headers["x-objectservice-id"] = self.object_service.upper()

        # Add JWT header
        headers["jwt"] = self._create_jwt(method, host, path_for_jwt)

        # Inject/override headers
        for k, v in headers.items():
            request.headers[k] = str(v)

        if self.logger:
            self.logger.info(
                "ProxiedS3Client before-sign: op=%s method=%s host=%s path=%s headers=%s",
                operation_name, method, host, path_for_jwt, list(
                    headers.keys())
            )

    def _create_jwt(self, method: str, host: str, path: str) -> str:
        now = int(time.time())
        payload = {
            "iat": now,
            "nbf": now,
            "exp": now + 300,         # 5 minutes
            "method": method,
            "iss": self.client_id,
            "host": host,
            "path": path,
            "region": self.region_claim,
        }
        token = jwt.encode(payload, self.client_secret, algorithm="HS256")
        # PyJWT may return bytes in older versions; ensure str
        return token if isinstance(token, str) else token.decode("utf-8")

    # ---------------------------
    # Convenience helpers
    # ---------------------------
    def get_bucket(self, bucket_name, validate=False, **kwargs):
        """Return a bucket adapter for boto2-style interface compatibility."""
        return ProxiedBucketAdapter(self, bucket_name)

    # Inherited methods from BaseS3Client:
    # - delete_key(bucket, path, **kwargs)
    # - get_object(bucket, key, **kwargs)
    # - put_object(bucket, key, body, **kwargs)
    # - list_objects(bucket, prefix="", **kwargs)
    # - upload_file(filename, bucket, key, **kwargs)
    # - raw()


class ProxiedBucketAdapter:
    """Adapter to provide boto2-style bucket interface for ProxiedS3Client."""

    def __init__(self, client, bucket_name):
        self.client = client
        self.name = bucket_name

    def get_key(self, key_name, validate=False, **kwargs):
        """Return a key adapter for boto2-style interface compatibility."""
        return ProxiedKeyAdapter(self.client, self.name, key_name)


class ProxiedKeyAdapter:
    """Adapter to provide boto2-style key interface for ProxiedS3Client."""

    def __init__(self, client, bucket_name, key_name):
        self.client = client
        self.bucket = bucket_name
        self.name = key_name

    def generate_url(self, expire=0, query_auth=True):
        """Generate a URL for this key."""
        # For the test, we need to construct the URL manually since ProxiedS3Client
        # doesn't have a direct generate_url method
        endpoint_url = self.client.client.meta.endpoint_url
        host_suffix = getattr(self.client, 'host_suffix', '')
        if host_suffix:
            return f"{endpoint_url}{host_suffix}/{self.bucket}/{self.name}"
        else:
            return f"{endpoint_url}/{self.bucket}/{self.name}"