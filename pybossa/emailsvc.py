# -*- coding: utf8 -*-
# This file is part of PYBOSSA.
#
# Copyright (C) 2025 Scifabric LTD.
#
# PYBOSSA is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# PYBOSSA is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with PYBOSSA.  If not, see <http://www.gnu.org/licenses/>.
import requests

class EmailService(object):
    def __init__(self, app=None):
        self.app = app
        self.required_keys = {"recipients", "subject", "body"}
        self.enabled = False
        if app is not None:  # pragma: no cover
            self.init_app(app)

    def init_app(self, app):
        self.app = app
        proxy_service_config = app.config["PROXY_SERVICE_CONFIG"]
        email_config = proxy_service_config["email_service"]

        self.url = f'{email_config["uri"]}/{email_config["name"]}/{email_config["major_version"]}/{email_config["minor_version"]}'
        self.request_type = email_config["requests"][0]
        self.headers = email_config["headers"]
        self.ssl_cert = app.config.get('SSL_CERT_PATH', True)
        self.enabled = True
        app.logger.info("Email service url %s, request %s", self.url, self.request_type)

    def send(self, message):
        try:
            # validate  message
            if not (isinstance(message, dict) and self.required_keys.issubset(message.keys())):
                raise ValueError(f"Incorrect email message format. message {message}")

            payload = {
                self.request_type: {
                    "recipients": message["recipients"],
                    "subject": message["subject"],
                    "body": message["body"],
                    "bcc": message.get("bcc", [])
                }
            }
            response = requests.post(self.url, headers=self.headers, json=payload, verify=self.ssl_cert)
            self.app.logger.info("Email service response %s for message %s", response, message)
        except Exception as ex:
            self.app.logger.error("Error sending email %s. message %s", str(ex), str(message))
