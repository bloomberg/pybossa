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


from test import Test, with_context
from unittest.mock import patch
from pybossa.emailsvc import EmailService


class TestEmailService(Test):
    """Test EmailService module."""

    def __init__(self):
        super().__init__()
        self.service_config = {
                "email_service": {
                    "uri": "https://path/to/service",
                    "name": "sendemailservice",
                    "major_version": 101,
                    "minor_version": 1456,
                    "requests": ["sendMsg"],
                    "headers": {'service-identity': '{"access_key": "xxx"}'}
                }
            }


    @with_context
    def test_emailsvc_init(self):
        """Test EmailService init method works."""

        esvc = EmailService()
        assert esvc.app == None
        
        expected_url = f"{self.service_config['email_service']['uri']}/{self.service_config['email_service']['name']}/{self.service_config['email_service']['major_version']}/{self.service_config['email_service']['minor_version']}"
        cert_path = "/home/ssl/certs"
        with patch.dict(self.flask_app.config,
                        {"PROXY_SERVICE_CONFIG": self.service_config, "SSL_CERT_PATH": cert_path}):
            esvc.init_app(self.flask_app)
            assert esvc.url == expected_url, esvc.url
            assert esvc.ssl_cert == cert_path

    @with_context
    @patch('pybossa.emailsvc.requests.post')
    def test_emailsvc_send_email(self, sendmail):
        """Test EmailService send method works."""

        expected_url = f"{self.service_config['email_service']['uri']}/{self.service_config['email_service']['name']}/{self.service_config['email_service']['major_version']}/{self.service_config['email_service']['minor_version']}"
        cert_path = "/home/ssl/certs"
        with patch.dict(self.flask_app.config,
                        {"PROXY_SERVICE_CONFIG": self.service_config, "SSL_CERT_PATH": cert_path}):
            esvc = EmailService(self.flask_app)
            message = {"recipients": ["abc@def.com"], "subject": "Welcome", "body": "Greetings from xyz"}
            expected_svc_payload = {
                self.service_config["email_service"]["requests"][0]: message
            }            
            esvc.send(message)
            sendmail.assert_called_with(expected_url, json=expected_svc_payload,
                headers=self.service_config["email_service"]["headers"], verify=cert_path)
            
    @with_context
    @patch('pybossa.emailsvc.requests.post')
    def test_emailsvc_send_email_exception(self, mock_post):
        """Test email service handles send email connection error."""

        cert_path = "/home/ssl/certs"
        with patch.dict(self.flask_app.config,
                        {"PROXY_SERVICE_CONFIG": self.service_config, "SSL_CERT_PATH": cert_path}):
            esvc = EmailService(self.flask_app)
            message = "hi"
            esvc.send(message)
            mock_post.assert_not_called()
