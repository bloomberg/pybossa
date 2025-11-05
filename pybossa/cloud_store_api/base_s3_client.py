from urllib.parse import urlsplit, urlunsplit
from botocore.exceptions import ClientError
from botocore.config import Config
import boto3
from pybossa.cloud_store_api.base_conn import BaseConnection


class BaseS3Client(BaseConnection):
    """
    Base class for S3 clients that provides common boto3 initialization
    and request modification patterns.

    This class extends BaseConnection to maintain compatibility with existing
    code while providing shared functionality for S3 client implementations.
    """

    def __init__(
        self,
        aws_access_key_id=None,
        aws_secret_access_key=None,
        aws_session_token=None,
        profile_name=None,
        endpoint_url=None,
        region_name=None,
        s3_ssl_no_verify=False,
        host_suffix="",
        **kwargs
    ):
        self.host_suffix = host_suffix or ""
        self.aws_access_key_id = aws_access_key_id
        self.aws_secret_access_key = aws_secret_access_key

        # Initialize http_connection_kwargs for compatibility with legacy tests
        self.http_connection_kwargs = {}
        if s3_ssl_no_verify:
            import ssl
            self.http_connection_kwargs['context'] = ssl._create_unverified_context()

        # Create boto3 session
        session = (
            boto3.session.Session(profile_name=profile_name)
            if profile_name
            else boto3.session.Session()
        )

        # Configure path-style addressing (emulates OrdinaryCallingFormat)
        config = Config(
            region_name=region_name,
            s3={"addressing_style": "path"},
        )

        # Handle SSL verification
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

        # Register hooks if needed - subclasses can override this logic
        if self._should_register_hooks():
            self.client.meta.events.register(
                "before-sign.s3",
                self._before_sign_hook,
            )

    def _should_register_hooks(self):
        """
        Determine when hooks should be registered.
        Subclasses can override this to customize hook registration logic.
        """
        return bool(self.host_suffix)

    def _before_sign_hook(self, request, **kwargs):
        """
        Base hook that handles host_suffix path modification.
        Subclasses can override or extend this method for additional functionality.
        """
        if self.host_suffix:
            self._apply_host_suffix(request)

    def _apply_host_suffix(self, request):
        """Apply host_suffix to the request URL path."""
        parts = urlsplit(request.url)
        # Ensure we don't double-prefix
        new_path = (self.host_suffix.rstrip("/") + "/" +
                    parts.path.lstrip("/")).replace("//", "/")
        request.url = urlunsplit(
            (parts.scheme, parts.netloc, new_path, parts.query, parts.fragment))

    def get_path(self, path):
        """
        Return the path with host_suffix prepended, for compatibility with legacy tests.
        This emulates the behavior that was expected from the old boto2 implementation.
        """
        if not self.host_suffix:
            return path
        
        # Normalize the path to ensure proper formatting
        if not path.startswith('/'):
            path = '/' + path
        
        # Combine host_suffix and path, avoiding double slashes
        combined = (self.host_suffix.rstrip("/") + "/" + path.lstrip("/")).replace("//", "/")
        
        # Ensure trailing slash if the original path was just '/'
        if path == '/' and not combined.endswith('/'):
            combined += '/'
            
        return combined

    # Override BaseConnection's delete_key to provide tolerant delete behavior
    def delete_key(self, bucket, path, **kwargs):
        """
        Delete an object, treating 200 and 204 as success.
        This overrides BaseConnection's delete_key to provide more tolerant behavior.
        """
        try:
            resp = self.client.delete_object(Bucket=bucket, Key=path, **kwargs)
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
        except ClientError:
            # Propagate any other errors
            raise

    # Additional convenience methods for boto3 compatibility
    def get_object(self, bucket, key, **kwargs):
        """Get object using boto3 client interface."""
        return self.client.get_object(Bucket=bucket, Key=key, **kwargs)

    def put_object(self, bucket, key, body, **kwargs):
        """Put object using boto3 client interface."""
        return self.client.put_object(Bucket=bucket, Key=key, Body=body, **kwargs)

    def list_objects(self, bucket, prefix="", **kwargs):
        """List objects using boto3 client interface."""
        return self.client.list_objects_v2(Bucket=bucket, Prefix=prefix, **kwargs)

    def upload_file(self, filename, bucket, key, **kwargs):
        """Upload file using boto3 client interface."""
        return self.client.upload_file(filename, bucket, key, ExtraArgs=kwargs or {})

    def raw(self):
        """Access the underlying boto3 client for advanced operations."""
        return self.client