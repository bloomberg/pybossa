from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlsplit

from test import with_context, with_context_settings
from test.factories import UserFactory
from test.helper.web import Helper

from pybossa.cloud_store_api.s3 import upload_email_attachment
from pybossa.core import signer


ATTACHMENT_SIGNATURE_SALT = 'email-attachment'
ATTACHMENT_SIGNATURE_MAX_AGE = 90 * 24 * 60 * 60


class TestAttachmentTokens(Helper):

    @with_context
    @patch('pybossa.view.attachment.s3_get_email_attachment')
    def test_unsalted_token_cannot_select_an_attachment(self, get_attachment):
        email = 'worker@example.com'
        user = UserFactory.create(email_addr=email, name='worker')
        self.signin_user(user)
        get_attachment.return_value = {
            'content': b'private export',
            'name': 'attachments/export.csv',
            'type': 'text/csv',
        }
        signature = signer.dumps({'user_email': email})

        response = self.app.get(
            '/attachment/{}/export.csv'.format(signature))

        assert response.status_code != 200
        get_attachment.assert_not_called()

    @with_context
    @patch('pybossa.view.attachment.s3_get_email_attachment')
    def test_attachment_token_is_bound_to_its_storage_key(self, get_attachment):
        email = 'worker2@example.com'
        user = UserFactory.create(email_addr=email, name='worker2')
        self.signin_user(user)
        signature = signer.dumps(
            {
                'user_email': email,
                's3_key': 'attachments/original.csv',
            },
            salt=ATTACHMENT_SIGNATURE_SALT)

        response = self.app.get(
            '/attachment/{}/different.csv'.format(signature))

        assert response.status_code == 403
        get_attachment.assert_not_called()

    @with_context
    @patch('pybossa.view.attachment.s3_get_email_attachment')
    def test_attachment_verifier_uses_purpose_and_expiry(self, get_attachment):
        email = 'worker3@example.com'
        user = UserFactory.create(email_addr=email, name='worker3')
        self.signin_user(user)
        get_attachment.return_value = {
            'content': b'private export',
            'name': 'attachments/export.csv',
            'type': 'text/csv',
        }
        signature = signer.dumps(
            {
                'user_email': email,
                's3_key': 'attachments/export.csv',
            },
            salt=ATTACHMENT_SIGNATURE_SALT)

        with patch.object(signer, 'loads', wraps=signer.loads) as loads:
            response = self.app.get(
                '/attachment/{}/export.csv'.format(signature))

        assert response.status_code == 200
        loads.assert_called_once_with(
            signature,
            salt=ATTACHMENT_SIGNATURE_SALT,
            max_age=ATTACHMENT_SIGNATURE_MAX_AGE)

    @with_context
    @patch('pybossa.view.attachment.s3_get_email_attachment')
    def test_expired_attachment_token_is_rejected(self, get_attachment):
        email = 'worker4@example.com'
        user = UserFactory.create(email_addr=email, name='worker4')
        self.signin_user(user)
        with patch('time.time', return_value=1):
            signature = signer.dumps(
                {
                    'user_email': email,
                    's3_key': 'attachments/export.csv',
                },
                salt=ATTACHMENT_SIGNATURE_SALT)

        response = self.app.get(
            '/attachment/{}/export.csv'.format(signature))

        assert response.status_code == 400
        get_attachment.assert_not_called()

    @with_context_settings(
        S3_REQUEST_BUCKET_V2='email-attachments',
        SERVER_URL='https://gigwork.example')
    @patch('pybossa.cache.users.get_user_by_email')
    @patch('pybossa.redis_lock.register_user_exported_report')
    @patch('pybossa.cloud_store_api.s3.create_connection')
    def test_uploader_mints_a_bound_attachment_token(
            self, create_connection, register_report, get_user_by_email):
        bucket = create_connection.return_value.get_bucket.return_value
        get_user_by_email.return_value = SimpleNamespace(id=12)

        url = upload_email_attachment(
            b'private export', 'export.csv', 'owner@example.com', project_id=42)

        signature, path = urlsplit(url).path.rsplit('/', 2)[-2:]
        payload = signer.loads(
            signature,
            salt=ATTACHMENT_SIGNATURE_SALT,
            max_age=ATTACHMENT_SIGNATURE_MAX_AGE)
        assert payload == {
            'project_id': 42,
            'user_email': 'owner@example.com',
            's3_key': 'attachments/{}'.format(path),
        }
        bucket.new_key.assert_called_once_with(payload['s3_key'])
        register_report.assert_called_once()
