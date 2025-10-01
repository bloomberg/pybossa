from typing import Optional, Dict
from urllib.parse import urlsplit, urlunsplit
from botocore.exceptions import ClientError
from botocore.config import Config
import boto3
import time
import jwt
import logging


class ProxiedS3Client:
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
        host_suffix: str = "",                  # prepended to every request path
        extra_headers: Optional[Dict[str, str]] = None,      # any additional headers to inject
        endpoint_url: Optional[str] = None,
        region_name: Optional[str] = None,
        profile_name: Optional[str] = None,
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
        aws_session_token: Optional[str] = None,
        s3_ssl_no_verify: bool = False,
        # optional logger with .info(...)
        logger: Optional[logging.Logger] = None,
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.object_service = object_service
        self.region_claim = region_claim
        self.host_suffix = host_suffix or ""
        self.extra_headers = extra_headers or {}
        self.logger = logger

        session = (
            boto3.session.Session(profile_name=profile_name)
            if profile_name else boto3.session.Session()
        )

        config = Config(
            region_name=region_name,
            # OrdinaryCallingFormat equivalent
            s3={"addressing_style": "path"},
        )

        verify = False if s3_ssl_no_verify else None  # None -> default verify

        self.client = session.client(
            "s3",
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            aws_session_token=aws_session_token,
            endpoint_url=endpoint_url,
            config=config,
            verify=verify,
        )

        # One hook to: (1) prefix path, (2) add headers, (3) attach JWT
        self.client.meta.events.register(
            "before-sign.s3", self._before_sign_hook)

    # ---------------------------
    # Event hook: adjust request
    # ---------------------------
    def _before_sign_hook(self, request, operation_name, **kwargs):
        """
        request: botocore.awsrequest.AWSRequest
        operation_name: e.g. "GetObject", "PutObject", etc.
        """
        parts = urlsplit(request.url)

        # 1) Prefix request path with host_suffix (if set)
        path = parts.path
        if self.host_suffix:
            path = (self.host_suffix.rstrip("/") + "/" +
                    path.lstrip("/")).replace("//", "/")
            request.url = urlunsplit(
                (parts.scheme, parts.netloc, path, parts.query, parts.fragment))

        # Recompute parts so host/path match the (possibly) updated URL
        parts = urlsplit(request.url)
        method = request.method
        host = parts.netloc
        path_for_jwt = parts.path  # include the prefixed path exactly as sent

        # 2) Build headers (x-objectservice-id + any extra)
        headers = dict(self.extra_headers)
        headers["x-objectservice-id"] = self.object_service.upper()

        # 3) Add JWT header
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
    def delete_key(self, bucket: str, key: str) -> bool:
        """
        Delete object: accept HTTP 200 or 204 as success (mirrors CustomBucket).
        """
        try:
            resp = self.client.delete_object(Bucket=bucket, Key=key)
            status = resp.get("ResponseMetadata", {}).get("HTTPStatusCode", 0)
            if status not in (200, 204):
                raise ClientError(
                    {"Error": {"Code": str(status), "Message": "Unexpected status"},
                     "ResponseMetadata": {"HTTPStatusCode": status}},
                    operation_name="DeleteObject",
                )
            return True
        except ClientError:
            # Propagate non-success/delete errors
            raise

    def get_object(self, bucket: str, key: str, **kwargs):
        return self.client.get_object(Bucket=bucket, Key=key, **kwargs)

    def put_object(self, bucket: str, key: str, body, **kwargs):
        return self.client.put_object(Bucket=bucket, Key=key, Body=body, **kwargs)

    def list_objects(self, bucket: str, prefix: str = "", **kwargs):
        return self.client.list_objects_v2(Bucket=bucket, Prefix=prefix, **kwargs)

    def upload_file(self, filename: str, bucket: str, key: str, **kwargs):
        # Uses s3transfer under the hood (built-in retries/backoff)
        return self.client.upload_file(filename, bucket, key, ExtraArgs=kwargs or {})

    def raw(self):
        """Access the underlying boto3 client if you need operations not wrapped here."""
        return self.client