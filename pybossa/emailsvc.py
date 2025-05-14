import requests

class EmailService(object):
    def __init__(self, app=None):
        self.app = app
        if app is not None:  # pragma: no cover
            self.init_app(app)

    def init_app(self, app):
        proxy_service_config = app.config["PROXY_SERVICE_CONFIG"]
        uri = proxy_service_config["uri"]
        email_config = proxy_service_config["email_service"]
        
        self.url = f'{uri}/{email_config["name"]}/{email_config["major_version"]}/{email_config["minor_version"]}'
        self.request_type = email_config["requests"][0]
        self.headers = email_config["headers"]
        self.ssl_cert = app.config.get('SSL_CERT_PATH', True)
        app.logger.info("Email service url %s, request %s", self.url, self.request_type)

    def send(self, message):
        try:
            payload = {self.request_type: message}
            response = requests.post(self.url, headers=self.headers, json=payload, verify=self.ssl_cert)
            self.app.logger.info("Email service response %s for message %s", response, message)
        except Exception as ex:
            self.app.logger.error("Error sending email %s. message %s", str(ex), str(message))
