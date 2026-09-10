import logging
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from flask import Flask

from pybossa.cloud_store_api import connection


class TestConnectionLogging(unittest.TestCase):

    def setUp(self):
        self.app = Flask(__name__)
        self.app.logger.setLevel(logging.INFO)

    def test_create_connection_logs_names_without_credential_values(self):
        environment = {
            "AWS_V2_ACCESS_KEY_ID": "V2-ACCESS-IDENTIFIER",
            "AWS_V2_SECRET_ACCESS_KEY": "ZXQmiddlePLM",
        }
        kwargs = {
            "aws_access_key_id": "KWARG-ACCESS-IDENTIFIER",
            "aws_secret_access_key": "QAZsensitiveWSX",
            "client_secret": "CLIENT-SECRET-VALUE",
            "host": "object-store.example",
        }

        with self.app.app_context(), \
                patch.dict(os.environ, environment, clear=False), \
                patch.object(connection, "CustomConnection") as constructor, \
                self.assertLogs(self.app.logger, level="INFO") as captured:
            result = connection.create_connection(**kwargs)

        self.assertIs(result, constructor.return_value)
        log_output = "\n".join(captured.output)
        for key in kwargs:
            self.assertIn(key, log_output)
        for credential_value in (
                environment["AWS_V2_ACCESS_KEY_ID"],
                "ZXQ",
                "PLM",
                kwargs["aws_access_key_id"],
                "QAZ",
                "WSX",
                kwargs["client_secret"]):
            self.assertNotIn(credential_value, log_output)

    def test_proxied_request_logs_header_names_without_values(self):
        jwt_value = "DISTINCTIVE-BEARER-JWT"
        correlation_value = "DISTINCTIVE-CORRELATION-VALUE"
        proxied_connection = object.__new__(connection.ProxiedConnection)
        proxied_connection.host = "object-store.example"
        proxied_connection.provider = SimpleNamespace(object_service="s3")
        proxied_connection.create_jwt = lambda *args: jwt_value

        with self.app.app_context(), \
                patch.object(connection.S3Connection, "make_request") as request, \
                self.assertLogs(self.app.logger, level="INFO") as captured:
            proxied_connection.make_request(
                "GET",
                "bucket",
                "key",
                headers={"X-Correlation-ID": correlation_value},
            )

        request.assert_called_once()
        log_output = "\n".join(captured.output)
        for header_name in ("X-Correlation-ID", "jwt", "x-objectservice-id"):
            self.assertIn(header_name, log_output)
        self.assertNotIn(jwt_value, log_output)
        self.assertNotIn(correlation_value, log_output)


if __name__ == "__main__":
    unittest.main()
