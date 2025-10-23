import io
import logging
import zlib
from abc import ABC, abstractmethod

from boto3.s3.transfer import TransferConfig
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class BaseConnection(ABC):
    @abstractmethod
    def __init__(
        self,
    ):
        self.client = None

    def get_key(self, bucket, path, **kwargs):
        try:
            fobj = self.client.get_object(
                Bucket=bucket,
                Key=path,
                **kwargs,
            )
            return fobj
        except ClientError as e:
            if "Error" in e.response:
                err_resp = e.response["Error"]
                http_status = e.response.get("ResponseMetadata", {}).get(
                    "HTTPStatusCode"
                )
                logger.warning(
                    "%s: %s, key %s. http status %d",
                    self.__class__.__name__,
                    str(e),
                    err_resp.get("Key", path),
                    http_status,
                )
            raise

    def get_contents(self, bucket, path, **kwargs):
        return self.get_contents_as_string(
            bucket=bucket, path=path, encoding=None, kwargs=kwargs
        )

    def get_head(self, bucket, path, **kwargs):
        return self.client.head_object(Bucket=bucket, Key=path, **kwargs)

    def get_contents_as_string(self, bucket, path, encoding="utf-8", **kwargs):
        """Returns contents as bytes or a string, depending on parameter
        "encoding". If encoding is None, returns bytes, otherwise, returns
        a string
        """
        try:
            fobj = self.client.get_object(
                Bucket=bucket,
                Key=path,
                **kwargs,
            )
            content = fobj["Body"].read()

            if encoding is None:
                return content

            if fobj.get("ContentEncoding") == "gzip":
                decompress_bits = (
                    32 + 15
                )  # https://docs.python.org/3/library/zlib.html#zlib.decompress
                content = zlib.decompress(content, decompress_bits)

            return content.decode(encoding)
        except ClientError as e:
            if "Error" in e.response:
                err_resp = e.response["Error"]
                http_status = e.response.get("ResponseMetadata", {}).get(
                    "HTTPStatusCode"
                )
                logger.warning(
                    "%s: %s, key %s. http status %d",
                    self.__class__.__name__,
                    str(e),
                    err_resp.get("Key", path),
                    http_status,
                )
            raise

    def set_contents(self, bucket, path, content, **kwargs):
        if type(content) == str:
            content = content.encode()
        try:
            source = io.BytesIO(content)
            config = TransferConfig(multipart_threshold=float("inf"))
            self.client.upload_fileobj(
                source, bucket, path, Config=config, ExtraArgs=kwargs
            )
        except ClientError as e:
            if "Error" in e.response:
                err_resp = e.response["Error"]
                http_status = e.response.get("ResponseMetadata", {}).get(
                    "HTTPStatusCode"
                )
                logger.warning(
                    "%s: %s, key %s. http status %d",
                    self.__class__.__name__,
                    str(e),
                    err_resp.get("Key", path),
                    http_status,
                )
            raise

    def set_contents_from_file(self, source_file, bucket, path, **kwargs):
        try:
            headers = kwargs.get("ExtraArgs", {}).get("headers", {})
            content_type = headers.get("Content-Type")
            extra_args = {"ContentType": content_type} if content_type else {}
            self.client.upload_fileobj(
                source_file, bucket, path, ExtraArgs=extra_args
            )
        except ClientError as e:
            if "Error" in e.response:
                err_resp = e.response["Error"]
                http_status = e.response.get("ResponseMetadata", {}).get(
                    "HTTPStatusCode"
                )
                logger.warning(
                    "%s: %s, key %s. http status %d",
                    self.__class__.__name__,
                    str(e),
                    err_resp.get("Key", path),
                    http_status,
                )
            raise
    def delete_key(self, bucket, path, **kwargs):
        try:
            self.client.delete_object(
                Bucket=bucket,
                Key=path,
                **kwargs,
            )
        except ClientError as e:
            if "Error" in e.response:
                err_resp = e.response["Error"]
                http_status = e.response.get("ResponseMetadata", {}).get(
                    "HTTPStatusCode"
                )
                logger.warning(
                    "%s: %s, key %s. http status %d",
                    self.__class__.__name__,
                    str(e),
                    err_resp.get("Key", path),
                    http_status,
                )
            raise

    def generate_url(self, bucket: str, key: str, **kwargs) -> str:
        return self.client.generate_presigned_url(
            "get_object", Params={"Bucket": bucket, "Key": key}, **kwargs
        )

    def get_bucket(
        self, bucket_name, validate=False, **kwargs
    ):  # pylint: disable=W0613
        return BaseClientBucketAdapter(self, bucket_name)

    def new_key(self, bucket, path):
        try:
            self.client.put_object(Bucket=bucket, Key=path)
        except ClientError as e:
            if "Error" in e.response:
                err_resp = e.response["Error"]
                http_status = e.response.get("ResponseMetadata", {}).get(
                    "HTTPStatusCode"
                )
                logger.warning(
                    "%s: %s, key %s. http status %d",
                    self.__class__.__name__,
                    str(e),
                    err_resp.get("Key", path),
                    http_status,
                )
            raise

    def copy_key(self, bucket, source_key, target_key, **kwargs):
        try:
            copy_source = {"Bucket": bucket, "Key": source_key}
            self.client.copy(CopySource=copy_source, Bucket=bucket, Key=target_key, ExtraArgs=kwargs)
        except ClientError as e:
            if "Error" in e.response:
                err_resp = e.response["Error"]
                http_status = e.response.get("ResponseMetadata", {}).get(
                    "HTTPStatusCode"
                )
                logger.warning(
                    "%s: %s, key %s. http status %d",
                    self.__class__.__name__,
                    str(e),
                    err_resp.get("Key", target_key),
                    http_status,
                )
            raise


class BaseClientBucketAdapter:
    def __init__(self, base_client, bucket_name):
        self.connection = base_client
        self.name = bucket_name

    def get_key(self, key_name, *args, **kwargs):  # pylint: disable=W0613
        response = self.connection.get_key(self.name, key_name)
        return BaseClientKeyAdapter(self.connection, self.name, key_name, **response)

    def delete_key(self, key_name, **kwargs):
        kwargs["VersionId"] = kwargs.pop("version_id", None)
        self.connection.delete_key(bucket=self.name, path=key_name)

    def new_key(self, key_name, *args, **kwargs):  # pylint: disable=W0613
        self.connection.new_key(bucket=self.name, path=key_name, **kwargs)
        return BaseClientKeyAdapter(self.connection, self.name, key_name)

    def copy_key(self, source_key, target_key, **kwargs):
        source_bucket = self.name
        self.connection.copy_key(self.name, source_key, target_key, **kwargs)


class BaseClientKeyAdapter:
    def __init__(self, base_client, bucket_name, key_name, **kwargs):
        self.base_client = base_client
        self.bucket = bucket_name
        self.name = key_name
        self.version_id = kwargs.get("VersionId")
        self.content_type = kwargs.get("ContentType")
        self.content_encoding = kwargs.get("ContentEncoding")
        self.content_language = kwargs.get("ContentLanguage")

    def get_contents_as_string(self, encoding=None, **kwargs):  # pylint: disable=W0613
        """Returns contents as bytes or string, depending on encoding parameter.
        If encoding is None, returns bytes, otherwise, returns
        a string.

        parameter "encoding" is default to None. This is consistent with boto2
        get_contents_as_string() method:
        http://boto.cloudhackers.com/en/latest/ref/s3.html#boto.s3.key.Key.get_contents_as_string
        """
        return self.base_client.get_contents_as_string(
            bucket=self.bucket, path=self.name, encoding=encoding
        )

    def set_contents_from_string(self, content, **kwargs):
        self.base_client.set_contents(
            bucket=self.bucket, path=self.name, content=content, **kwargs
        )

    def set_contents_from_file(self, source_file, **kwargs):
        return self.base_client.set_contents_from_file(
            source_file, bucket=self.bucket, path=self.name, ExtraArgs=kwargs
        )

    def get_object_head(self):
        return self.base_client.get_head(self.bucket, self.name)

    def generate_url(self, expire=0, query_auth=True):  # pylint: disable=W0613
        return self.base_client.generate_url(
            bucket=self.bucket, key=self.name, ExpiresIn=expire
        )

    def delete(self, **kwargs):
        self.base_client.delete_key(bucket=self.bucket, path=self.name, **kwargs)
