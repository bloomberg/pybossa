from copy import deepcopy
import ssl
import sys
import time

from flask import current_app

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

def create_connection(**kwargs):
    # TODO: remove later
    v2_access = environ.get("AWS_V2_ACCESS_KEY_ID")
    v2_secret = environ.get("AWS_V2_SECRET_ACCESS_KEY")
    if v2_access and v2_secret:
        masked_v2_secret = f"{v2_secret[:3]}{'x'*(len(v2_secret)-6)}{v2_secret[-3:]}"
        current_app.logger.info("v2_access %s, v2_secret %s", v2_access, masked_v2_secret)
    else:
        current_app.logger.info("v2_access, v2_secret not found")

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

    current_app.logger.info("Calling CustomConnection")
    conn = CustomConnection(**kwargs)
    return conn


class CustomConnection(BaseConnection):

    def __init__(self, *args, **kwargs):
        super().__init__()  # super(CustomConnection, self).__init__(*args, **kwargs)

        aws_access_key_id = kwargs.get("aws_access_key_id")
        aws_secret_access_key = kwargs.get("aws_secret_access_key")
        region_name = kwargs.get("region_name", "us-east-1")
        cert = kwargs.get('cert', False)
        proxy_url = kwargs.get('proxy_url', None)
        proxies = {"https": proxy_url, "http": proxy_url} if proxy_url else None
        ssl_verify = kwargs.get('ssl_verify', True)
        self.client = Session().client(
            service_name="s3",
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            region_name=region_name,
            use_ssl=ssl_verify,
            verify=cert,
            config=Config(
                proxies=proxies,
                s3={"addressing_style": "path"} # equivalent to OrdinaryCallingFormat under old boto
            ),
        )


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
