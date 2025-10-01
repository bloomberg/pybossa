from urllib.parse import urlsplit, urlunsplit
from botocore.exceptions import ClientError
from botocore.config import Config
import boto3


class S3ClientWrapper:
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
        aws_access_key_id=None,
        aws_secret_access_key=None,
        aws_session_token=None,
        profile_name=None,
        endpoint_url=None,
        region_name=None,
        object_service=None,   # kept for API compatibility; not used by boto3 directly
        auth_headers=None,     # dict of headers to inject into every request
        s3_ssl_no_verify=False,
        # string to prefix to every request path (e.g., "/proxy")
        host_suffix="",
    ):
        self.auth_headers = auth_headers or {}
        self.host_suffix = host_suffix or ""

        session = (
            boto3.session.Session(profile_name=profile_name)
            if profile_name
            else boto3.session.Session()
        )

        # Emulate OrdinaryCallingFormat via path-style addressing
        config = Config(
            region_name=region_name,
            s3={"addressing_style": "path"},
        )

        # If s3_ssl_no_verify=True, disable cert verification
        verify = False if s3_ssl_no_verify else None  # None = default verify behavior

        self.client = session.client(
            "s3",
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            aws_session_token=aws_session_token,
            endpoint_url=endpoint_url,
            config=config,
            verify=verify,
        )

        # Register event hook to inject headers and prefix the path
        if self.auth_headers or self.host_suffix:
            self.client.meta.events.register(
                "before-sign.s3",
                self._before_sign_hook,
            )

    # --- event hooks ---

    def _before_sign_hook(self, request, **kwargs):
        """
        Runs before the request is signed. We can:
          - add custom headers
          - modify the URL to add a path prefix (host_suffix)
        """
        # Inject headers
        if self.auth_headers:
            for k, v in self.auth_headers.items():
                # Don't clobber existing values unless we mean to
                if v is not None:
                    request.headers[k] = str(v)

        # Prepend host_suffix to the URL path if provided
        if self.host_suffix:
            parts = urlsplit(request.url)
            # Ensure we don't double-prefix
            new_path = (self.host_suffix.rstrip("/") + "/" +
                        parts.path.lstrip("/")).replace("//", "/")
            request.url = urlunsplit(
                (parts.scheme, parts.netloc, new_path, parts.query, parts.fragment))

    # --- convenience helpers mirroring old usage ---

    def delete_key(self, bucket, key):
        """
        Delete an object, treating 200 and 204 as success (boto3 typically returns 204).
        Raises if a different error occurs.
        """
        try:
            resp = self.client.delete_object(Bucket=bucket, Key=key)
            status = resp.get("ResponseMetadata", {}).get("HTTPStatusCode", 0)
            if status not in (200, 204):
                raise ClientError(
                    {
                        "Error": {"Code": str(status), "Message": "Unexpected status"},
                        "ResponseMetadata": {"HTTPStatusCode": status},
                    },
                    operation_name="DeleteObject",
                )
            return True
        except ClientError as e:
            # Some proxies/services may return 200 on a successful delete; boto3 often returns 204.
            # If it's anything else, propagate the error.
            raise

    def get_object(self, bucket, key, **kwargs):
        return self.client.get_object(Bucket=bucket, Key=key, **kwargs)

    def put_object(self, bucket, key, body, **kwargs):
        return self.client.put_object(Bucket=bucket, Key=key, Body=body, **kwargs)

    def list_objects(self, bucket, prefix="", **kwargs):
        return self.client.list_objects_v2(Bucket=bucket, Prefix=prefix, **kwargs)

    # expose the raw client if you need more
    def raw(self):
        return self.client

