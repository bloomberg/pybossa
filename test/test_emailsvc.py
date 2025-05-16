"""This module tests the EmailService class."""

from test import Test, with_context
from pybossa.emailsvc import EmailService
from unittest.mock import patch
from requests.exceptions import ConnectionError
from pybossa.jobs import send_mail
from pybossa.core import setup_email_service


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
    def test_emailsvc_send_email_exception(self, sendmail):
        """Test email service handles send email connection error."""

        sendmail.side_effect = [ConnectionError]
        cert_path = "/home/ssl/certs"
        with patch.dict(self.flask_app.config,
                        {"PROXY_SERVICE_CONFIG": self.service_config, "SSL_CERT_PATH": cert_path}):
            esvc = EmailService(self.flask_app)
            message = "hi"
            esvc.send(message)
            sendmail.assert_called_once()

    @with_context
    @patch('pybossa.core.email_service')
    def test_setup_email_service(self, mock_email_service):
        cert_path = "/home/ssl/certs"
        with self.flask_app.app_context():
            from pybossa.core import email_service
            with patch.dict(self.flask_app.config,
                            {"PROXY_SERVICE_CONFIG": self.service_config, "SSL_CERT_PATH": cert_path}):
                setup_email_service(self.flask_app)
                assert mock_email_service.enabled
