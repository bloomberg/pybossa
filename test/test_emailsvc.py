"""This module tests the EmailService class."""

from test import Test, with_context
from pybossa.emailsvc import EmailService
from unittest.mock import patch
from requests.exceptions import ConnectionError
from pybossa.jobs import send_mail


class TestEmailService(Test):
    """Test EmailService module."""

    def setUp(self):
        """SetUp method."""
        super(TestEmailService, self).setUp()
        with self.flask_app.app_context():
            self.create()

    @with_context
    def test_emailsvc_init(self):
        """Test EmailService init method works."""

        esvc = EmailService()
        assert esvc.app == None
        
        service_config = {
            "uri": "https://path/to/service",
            "email_service": {
                "name": "sendemailservice",
                "major_version": 101,
                "minor_version": 1456,
                "requests": ["sendMsg"],
                "headers": {'service-identity': '{"access_key": "xxx"}'}
            }
        }
        expected_url = f"{service_config['uri']}/{service_config['email_service']['name']}/{service_config['email_service']['major_version']}/{service_config['email_service']['minor_version']}"
        cert_path = "/home/ssl/certs"
        with patch.dict(self.flask_app.config,
                        {"PROXY_SERVICE_CONFIG": service_config, "SSL_CERT_PATH": cert_path}):
            esvc.init_app(self.flask_app)
            assert esvc.url == expected_url, esvc.url
            assert esvc.ssl_cert == cert_path

    @with_context
    @patch('pybossa.emailsvc.requests.post')
    def test_emailsvc_send_email(self, sendmail):
        """Test EmailService send method works."""

        service_config = {
            "uri": "https://path/to/service",
            "email_service": {
                "name": "sendemailservice",
                "major_version": 101,
                "minor_version": 1456,
                "requests": ["sendMsg"],
                "headers": {'service-identity': '{"access_key": "xxx"}'}
            }
        }
        expected_url = f"{service_config['uri']}/{service_config['email_service']['name']}/{service_config['email_service']['major_version']}/{service_config['email_service']['minor_version']}"
        cert_path = "/home/ssl/certs"
        with patch.dict(self.flask_app.config,
                        {"PROXY_SERVICE_CONFIG": service_config, "SSL_CERT_PATH": cert_path}):
            esvc = EmailService(self.flask_app)
            message = {"recipients": ["abc@def.com"], "subject": "Welcome", "body": "Greetings from xyz"}
            expected_svc_payload = {
                service_config["email_service"]["requests"][0]: message
            }            
            esvc.send(message)
            sendmail.assert_called_with(expected_url, json=expected_svc_payload,
                headers=service_config["email_service"]["headers"], verify=cert_path)
            
    @with_context
    @patch('pybossa.emailsvc.requests.post')
    def test_emailsvc_send_email_exception(self, sendmail):
        """Test email service handles send email connection error."""

        sendmail.side_effect = [ConnectionError]
        
        service_config = {
            "uri": "https://path/to/service",
            "email_service": {
                "name": "sendemailservice",
                "major_version": 101,
                "minor_version": 1456,
                "requests": ["sendMsg"],
                "headers": {'service-identity': '{"access_key": "xxx"}'}
            }
        }
        cert_path = "/home/ssl/certs"
        with patch.dict(self.flask_app.config,
                        {"PROXY_SERVICE_CONFIG": service_config, "SSL_CERT_PATH": cert_path}):        
            esvc = EmailService(self.flask_app)
            message = "hi"
            esvc.send(message)
            sendmail.assert_called_once()

    @with_context
    @patch('pybossa.jobs.email_service')
    def test_jobs_use_emailsvc_to_send_email(self, mock_email_service):
        """Test to verify that the email service is used to send an email."""

        message = {"recipients": ["abc@def.com"], "subject": "Welcome", "body": "Greetings from xyz"}        
        send_mail(message_dict=message, mail_all=True)
        mock_email_service.send.assert_called_once_with(message)
