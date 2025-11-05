# -*- coding: utf8 -*-
# This file is part of PYBOSSA.
#
# Copyright (C) 2018 Scifabric LTD.
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

import json
import os
import tempfile
from io import BytesIO
from unittest.mock import patch, MagicMock, mock_open
from test import Test, with_context
from pybossa.cloud_store_api.s3 import (
    tmp_file_from_string, form_upload_directory, get_content_and_key_from_s3,
    get_content_from_s3, upload_json_data, upload_email_attachment,
    s3_get_email_attachment, validate_directory, s3_upload_tmp_file,
    s3_upload_from_string, delete_file_from_s3
)
from pybossa.encryption import AESWithGCM
from nose.tools import assert_raises
from werkzeug.exceptions import BadRequest
from botocore.exceptions import ClientError


class TestS3Additional(Test):

    default_config = {
        'S3_DEFAULT': {
            'host': 's3.storage.com',
            'port': 443,
            'auth_headers': [('test', 'name')]
        },
        'FILE_ENCRYPTION_KEY': 'test_secret_key_12345678901234567890',
        'S3_BUCKET': 'test-bucket',
        'S3_BUCKET_V2': 'test-bucket-v2',
        'S3_CONN_TYPE_V2': True,
        'S3_REQUEST_BUCKET_V2': 'request-bucket',
        'S3_TASK_REQUEST_V2': {
            'host': 's3.request.com',
            'port': 443,
            'auth_headers': [('req', 'auth')]
        },
        'SERVER_URL': 'https://example.com'
    }

    def test_tmp_file_from_string_success(self):
        """Test successful creation of temporary file from string"""
        test_content = "Hello, World! 你好世界"
        tmp_file = tmp_file_from_string(test_content)

        # Read the file content back
        with open(tmp_file.name, 'r', encoding='utf8') as fp:
            content = fp.read()

        assert content == test_content
        # Clean up
        os.unlink(tmp_file.name)

    @patch('pybossa.cloud_store_api.s3.io.open')
    def test_tmp_file_from_string_exception(self, mock_open):
        """Test tmp_file_from_string handles file creation exceptions"""
        mock_open.side_effect = IOError("Permission denied")

        with assert_raises(IOError):
            tmp_file_from_string("test content")

    def test_form_upload_directory_with_all_parts(self):
        """Test form_upload_directory with all parameters"""
        result = form_upload_directory("subdir/nested", "file.txt", "uploads")
        assert result == "uploads/subdir/nested/file.txt"

    def test_form_upload_directory_no_upload_root(self):
        """Test form_upload_directory without upload root"""
        result = form_upload_directory("subdir", "file.txt", None)
        assert result == "subdir/file.txt"

    def test_form_upload_directory_no_directory(self):
        """Test form_upload_directory without directory"""
        result = form_upload_directory("", "file.txt", "uploads")
        assert result == "uploads/file.txt"

    def test_form_upload_directory_empty_parts(self):
        """Test form_upload_directory with empty parts"""
        result = form_upload_directory("", "file.txt", "")
        assert result == "file.txt"

    def test_validate_directory_valid_cases(self):
        """Test validate_directory with valid directory names"""
        valid_dirs = [
            "simple",
            "with_underscore",
            "with123numbers",
            "path/with/slashes",
            "path_with/mixed_123/chars"
        ]
        for directory in valid_dirs:
            # Should not raise any exception
            validate_directory(directory)

    def test_validate_directory_invalid_cases(self):
        """Test validate_directory with invalid directory names"""
        invalid_dirs = [
            "with-dash",
            "with space",
            "with@symbol",
            "with$dollar",
            "with%percent",
            "with.dot",
            "with|pipe"
        ]
        for directory in invalid_dirs:
            with assert_raises(RuntimeError):
                validate_directory(directory)

    @with_context
    @patch('pybossa.cloud_store_api.s3.create_connection')
    def test_get_content_and_key_from_s3_with_decryption(self, mock_create_connection):
        """Test get_content_and_key_from_s3 with decryption enabled"""
        with patch.dict(self.flask_app.config, self.default_config):
            # Prepare encrypted content
            secret = self.default_config['FILE_ENCRYPTION_KEY']
            cipher = AESWithGCM(secret)
            original_content = "Hello, encrypted world!"
            encrypted_content = cipher.encrypt(original_content.encode())

            # Create mock objects
            mock_key = MagicMock()
            mock_key.get_contents_as_string.return_value = encrypted_content

            mock_bucket = MagicMock()
            mock_bucket.get_key.return_value = mock_key

            mock_conn = MagicMock()
            mock_conn.get_bucket.return_value = mock_bucket

            mock_create_connection.return_value = mock_conn

            content, key = get_content_and_key_from_s3(
                's3_bucket', '/test/path', decrypt=True)

            assert content == original_content
            assert key == mock_key

    @with_context
    @patch('pybossa.cloud_store_api.s3.create_connection')
    def test_get_content_and_key_from_s3_with_custom_secret(self, mock_create_connection):
        """Test get_content_and_key_from_s3 with custom decryption secret"""
        with patch.dict(self.flask_app.config, self.default_config):
            # Prepare encrypted content with custom secret
            custom_secret = "custom_secret_123456789012345678901234"
            cipher = AESWithGCM(custom_secret)
            original_content = "Custom secret content!"
            encrypted_content = cipher.encrypt(original_content.encode())

            # Create mock objects
            mock_key = MagicMock()
            mock_key.get_contents_as_string.return_value = encrypted_content

            mock_bucket = MagicMock()
            mock_bucket.get_key.return_value = mock_key

            mock_conn = MagicMock()
            mock_conn.get_bucket.return_value = mock_bucket

            mock_create_connection.return_value = mock_conn

            content, key = get_content_and_key_from_s3(
                's3_bucket', '/test/path', decrypt=True, secret=custom_secret)

            assert content == original_content
            assert key == mock_key

    @with_context
    @patch('pybossa.cloud_store_api.s3.create_connection')
    def test_get_content_and_key_from_s3_binary_content(self, mock_create_connection):
        """Test get_content_and_key_from_s3 with binary content that can't be decoded"""
        with patch.dict(self.flask_app.config, self.default_config):
            # Binary content that will cause UnicodeDecodeError
            binary_content = b'\x80\x81\x82\x83'

            # Create mock objects
            mock_key = MagicMock()
            mock_key.get_contents_as_string.return_value = binary_content

            mock_bucket = MagicMock()
            mock_bucket.get_key.return_value = mock_key

            mock_conn = MagicMock()
            mock_conn.get_bucket.return_value = mock_bucket

            mock_create_connection.return_value = mock_conn

            content, key = get_content_and_key_from_s3('s3_bucket', '/test/path')

            # Should return binary content as-is when decode fails
            assert content == binary_content
            assert key == mock_key

    @with_context
    @patch('pybossa.cloud_store_api.s3.create_connection')
    def test_get_content_from_s3_wrapper(self, mock_create_connection):
        """Test get_content_from_s3 as wrapper function"""
        with patch.dict(self.flask_app.config, self.default_config):
            test_content = "Test content"

            # Create mock objects
            mock_key = MagicMock()
            mock_key.get_contents_as_string.return_value = test_content.encode()

            mock_bucket = MagicMock()
            mock_bucket.get_key.return_value = mock_key

            mock_conn = MagicMock()
            mock_conn.get_bucket.return_value = mock_bucket

            mock_create_connection.return_value = mock_conn

            content = get_content_from_s3('s3_bucket', '/test/path')

            assert content == test_content

    @with_context
    @patch('pybossa.cloud_store_api.s3.s3_upload_from_string')
    def test_upload_json_data_with_bucket_v2(self, mock_upload):
        """Test upload_json_data with S3_BUCKET_V2 configuration"""
        with patch.dict(self.flask_app.config, self.default_config):
            mock_upload.return_value = "https://s3.example.com/bucket/file.json"

            test_data = {"key": "value", "number": 123, "unicode": "测试"}

            result = upload_json_data(
                test_data, "test/path", "data.json",
                encryption=True, conn_name="S3_DEFAULT"
            )

            assert result == "https://s3.example.com/bucket/file.json"

            # Verify the call was made with correct parameters
            mock_upload.assert_called_once()
            args, kwargs = mock_upload.call_args

            # Check that JSON was properly serialized
            uploaded_content = args[1]
            parsed_data = json.loads(uploaded_content)
            assert parsed_data == test_data

            assert kwargs['with_encryption'] == True
            assert kwargs['conn_name'] == "S3_DEFAULT"

    @with_context
    @patch('pybossa.cloud_store_api.s3.s3_upload_from_string')
    def test_upload_json_data_with_default_bucket(self, mock_upload):
        """Test upload_json_data with default S3_BUCKET configuration"""
        config = self.default_config.copy()
        config['S3_CONN_TYPE_V2'] = False  # Use default bucket

        with patch.dict(self.flask_app.config, config):
            mock_upload.return_value = "https://s3.example.com/bucket/file.json"

            test_data = {"test": "data"}

            result = upload_json_data(
                test_data, "test/path", "data.json",
                encryption=False, conn_name="S3_DEFAULT",
                bucket="custom-bucket"
            )

            assert result == "https://s3.example.com/bucket/file.json"
            mock_upload.assert_called_once()

    @with_context
    @patch('pybossa.cloud_store_api.s3.create_connection')
    @patch('pybossa.core.signer')
    @patch('time.time')
    def test_upload_email_attachment_success(self, mock_time, mock_signer, mock_create_connection):
        """Test successful email attachment upload"""
        with patch.dict(self.flask_app.config, self.default_config):
            # Mock time for consistent timestamps
            mock_time.return_value = 1609459200  # 2021-01-01 00:00:00 UTC

            # Mock signer
            mock_signer.dumps.return_value = "signed_payload_123"

            # Create mock S3 objects
            mock_key = MagicMock()
            mock_bucket = MagicMock()
            mock_bucket.new_key.return_value = mock_key
            mock_conn = MagicMock()
            mock_conn.get_bucket.return_value = mock_bucket
            mock_create_connection.return_value = mock_conn

            content = b"Test file content"
            filename = "test file.txt"
            user_email = "test@example.com"
            project_id = 123

            result = upload_email_attachment(content, filename, user_email, project_id)

            expected_url = "https://example.com/attachment/signed_payload_123/1609459200-test_file.txt"
            assert result == expected_url

            # Verify signer was called with correct payload
            mock_signer.dumps.assert_called_once_with({
                "project_id": project_id,
                "user_email": user_email
            })

            # Verify S3 operations
            mock_bucket.new_key.assert_called_once_with("attachments/1609459200-test_file.txt")
            mock_key.set_contents_from_string.assert_called_once_with(content)

    @with_context
    @patch('pybossa.cloud_store_api.s3.create_connection')
    @patch('pybossa.core.signer')
    @patch('time.time')
    def test_upload_email_attachment_without_project_id(self, mock_time, mock_signer, mock_create_connection):
        """Test email attachment upload without project_id"""
        with patch.dict(self.flask_app.config, self.default_config):
            mock_time.return_value = 1609459200
            mock_signer.dumps.return_value = "signed_payload_456"

            # Create mock S3 objects
            mock_key = MagicMock()
            mock_bucket = MagicMock()
            mock_bucket.new_key.return_value = mock_key
            mock_conn = MagicMock()
            mock_conn.get_bucket.return_value = mock_bucket
            mock_create_connection.return_value = mock_conn

            content = b"Test content"
            filename = "test.pdf"
            user_email = "user@test.com"

            result = upload_email_attachment(content, filename, user_email)

            # Verify signer was called without project_id
            mock_signer.dumps.assert_called_once_with({
                "user_email": user_email
            })

    @with_context
    def test_upload_email_attachment_missing_bucket_config(self):
        """Test upload_email_attachment raises error when bucket not configured"""
        config = self.default_config.copy()
        del config['S3_REQUEST_BUCKET_V2']

        with patch.dict(self.flask_app.config, config):
            with assert_raises(RuntimeError) as context:
                upload_email_attachment(b"content", "file.txt", "user@example.com")

            assert "S3_REQUEST_BUCKET_V2 is not configured" in str(context.exception)

    @with_context
    @patch('pybossa.cloud_store_api.s3.get_content_and_key_from_s3')
    def test_s3_get_email_attachment_success(self, mock_get_content):
        """Test successful email attachment retrieval"""
        with patch.dict(self.flask_app.config, self.default_config):
            # Mock the S3 response
            mock_key = MagicMock()
            mock_key.name = "attachments/1609459200-test.pdf"
            mock_key.content_type = "application/pdf"

            mock_content = b"PDF file content"
            mock_get_content.return_value = (mock_content, mock_key)

            result = s3_get_email_attachment("1609459200-test.pdf")

            expected = {
                "name": "attachments/1609459200-test.pdf",
                "type": "application/pdf",
                "content": mock_content
            }

            assert result == expected
            mock_get_content.assert_called_once_with(
                s3_bucket="request-bucket",
                path="attachments/1609459200-test.pdf",
                conn_name="S3_TASK_REQUEST_V2"
            )

    @with_context
    @patch('pybossa.cloud_store_api.s3.get_content_and_key_from_s3')
    def test_s3_get_email_attachment_no_content(self, mock_get_content):
        """Test email attachment retrieval when file not found"""
        with patch.dict(self.flask_app.config, self.default_config):
            # Mock empty response
            mock_get_content.return_value = (None, None)

            result = s3_get_email_attachment("nonexistent.pdf")

            expected = {
                "name": "",
                "type": "application/octet-stream",
                "content": b""
            }

            assert result == expected

    @with_context
    def test_s3_get_email_attachment_no_bucket_config(self):
        """Test s3_get_email_attachment when bucket not configured"""
        config = self.default_config.copy()
        del config['S3_REQUEST_BUCKET_V2']

        with patch.dict(self.flask_app.config, config):
            result = s3_get_email_attachment("test.pdf")

            expected = {
                "name": "",
                "type": "application/octet-stream",
                "content": b""
            }

            assert result == expected

    @with_context
    @patch('pybossa.cloud_store_api.s3.create_connection')
    def test_delete_file_from_s3_client_error(self, mock_create_connection):
        """Test delete_file_from_s3 handles ClientError"""
        with patch.dict(self.flask_app.config, self.default_config):
            # Create mock objects that raise ClientError
            mock_bucket = MagicMock()
            mock_bucket.delete_key.side_effect = ClientError(
                {'Error': {'Code': 'NoSuchKey'}}, 'DeleteObject'
            )
            mock_bucket.get_key.return_value = MagicMock(name='/test/key', version_id=None)

            mock_conn = MagicMock()
            mock_conn.get_bucket.return_value = mock_bucket
            mock_create_connection.return_value = mock_conn

            # Should not raise exception, just log it
            delete_file_from_s3('test_bucket', '/test/key')

    @with_context
    @patch('pybossa.cloud_store_api.s3.create_connection')
    @patch('pybossa.cloud_store_api.s3.check_type')
    @patch('os.unlink')
    def test_s3_upload_tmp_file_with_encryption(self, mock_unlink, mock_check_type, mock_create_connection):
        """Test s3_upload_tmp_file with encryption enabled"""
        with patch.dict(self.flask_app.config, self.default_config):
            # Create a real temporary file for testing
            import tempfile
            tmp_file = tempfile.NamedTemporaryFile(delete=False)
            tmp_file.write(b"test content")
            tmp_file.close()

            # Create mock S3 objects
            mock_key = MagicMock()
            mock_key.generate_url.return_value = 'https://s3.storage.com/bucket/test.txt'
            mock_bucket = MagicMock()
            mock_bucket.new_key.return_value = mock_key
            mock_conn = MagicMock()
            mock_conn.get_bucket.return_value = mock_bucket
            mock_create_connection.return_value = mock_conn

            # Mock the temporary file object
            mock_tmp_file = MagicMock()
            mock_tmp_file.name = tmp_file.name
            mock_tmp_file.read.return_value = b"test content"

            result = s3_upload_tmp_file(
                's3_bucket', mock_tmp_file, 'test.txt',
                headers={'Content-Type': 'text/plain'},
                directory='uploads',
                file_type_check=True,
                return_key_only=False,
                conn_name='S3_DEFAULT',
                with_encryption=True,
                upload_root_dir='root'
            )

            assert result == 'https://s3.storage.com/bucket/test.txt'
            mock_check_type.assert_called_once_with(tmp_file.name)
            mock_unlink.assert_called_once_with(tmp_file.name)

            # Clean up the test file
            try:
                os.unlink(tmp_file.name)
            except FileNotFoundError:
                pass

    @with_context
    @patch('pybossa.cloud_store_api.s3.create_connection')
    def test_s3_upload_from_string_with_bcosv2_url_transformation(self, mock_create_connection):
        """Test s3_upload_from_string with BCOSV2 URL transformation"""
        config = self.default_config.copy()
        config['BCOSV2_PROD_UTIL_URL'] = "https://s3.storage.env-util.com"

        with patch.dict(self.flask_app.config, config):
            # Create mock objects - similar to existing working test
            mock_key = MagicMock()
            mock_key.generate_url.return_value = 'https://s3.storage.env-util.com/bucket/test.txt'
            mock_key.name = 'test.txt'

            mock_bucket = MagicMock()
            mock_bucket.new_key.return_value = mock_key

            mock_conn = MagicMock()
            mock_conn.get_bucket.return_value = mock_bucket

            mock_create_connection.return_value = mock_conn

            result = s3_upload_from_string(
                'bucket', 'test content', 'test.txt'
            )

            # Should transform -util URL to non-util URL
            expected_url = "https://s3.storage.env.com/bucket/test.txt"
            assert result == expected_url

    @with_context
    @patch('pybossa.cloud_store_api.s3.create_connection')
    def test_s3_upload_from_string_without_bcosv2_transformation(self, mock_create_connection):
        """Test s3_upload_from_string without BCOSV2 URL transformation"""
        with patch.dict(self.flask_app.config, self.default_config):
            # Create mock objects
            mock_key = MagicMock()
            mock_key.generate_url.return_value = 'https://s3.storage.com/bucket/test.txt'
            mock_key.name = 'test.txt'

            mock_bucket = MagicMock()
            mock_bucket.new_key.return_value = mock_key

            mock_conn = MagicMock()
            mock_conn.get_bucket.return_value = mock_bucket

            mock_create_connection.return_value = mock_conn

            result = s3_upload_from_string(
                'bucket', 'test content', 'test.txt'
            )

            # Should return URL unchanged
            assert result == 'https://s3.storage.com/bucket/test.txt'

    @with_context
    @patch('pybossa.cloud_store_api.s3.create_connection')
    def test_s3_upload_file_storage_with_content_type(self, mock_create_connection):
        """Test s3_upload_file_storage preserves content type from FileStorage"""
        with patch.dict(self.flask_app.config, self.default_config):
            # Create mock S3 objects
            mock_key = MagicMock()
            mock_key.generate_url.return_value = 'https://s3.storage.com/bucket/test.csv'
            mock_bucket = MagicMock()
            mock_bucket.new_key.return_value = mock_key
            mock_conn = MagicMock()
            mock_conn.get_bucket.return_value = mock_bucket
            mock_create_connection.return_value = mock_conn

            # Create FileStorage with specific content type
            from werkzeug.datastructures import FileStorage
            stream = BytesIO(b'col1,col2\nval1,val2')
            file_storage = FileStorage(
                stream=stream,
                filename='test.csv',
                content_type='text/csv'
            )

            from pybossa.cloud_store_api.s3 import s3_upload_file_storage
            result = s3_upload_file_storage('bucket', file_storage)

            assert result == 'https://s3.storage.com/bucket/test.csv'
            # Verify that set_contents_from_file was called with Content-Type header
            mock_key.set_contents_from_file.assert_called_once()
            call_args = mock_key.set_contents_from_file.call_args
            extra_args = call_args[1]['ExtraArgs']
            assert extra_args['Content-Type'] == 'text/csv'

    @with_context
    def test_tmp_file_from_string_unicode_content(self):
        """Test tmp_file_from_string with unicode content"""
        unicode_content = "Hello 世界! 🌍 Café naïve résumé"
        tmp_file = tmp_file_from_string(unicode_content)

        # Read back and verify unicode is preserved
        with open(tmp_file.name, 'r', encoding='utf8') as fp:
            content = fp.read()

        assert content == unicode_content
        os.unlink(tmp_file.name)

    @with_context
    @patch('pybossa.cloud_store_api.s3.create_connection')
    def test_get_content_and_key_string_content(self, mock_create_connection):
        """Test get_content_and_key_from_s3 with string content from S3"""
        with patch.dict(self.flask_app.config, self.default_config):
            test_content = "String content from S3"

            # Create mock objects - S3 returns string content
            mock_key = MagicMock()
            mock_key.get_contents_as_string.return_value = test_content

            mock_bucket = MagicMock()
            mock_bucket.get_key.return_value = mock_key

            mock_conn = MagicMock()
            mock_conn.get_bucket.return_value = mock_bucket

            mock_create_connection.return_value = mock_conn

            content, key = get_content_and_key_from_s3('s3_bucket', '/test/path')

            # String content should be returned as-is
            assert content == test_content
            assert key == mock_key

    @with_context
    @patch('pybossa.cloud_store_api.s3.secure_filename')
    @patch('pybossa.cloud_store_api.s3.create_connection')
    def test_s3_upload_file_with_insecure_filename(self, mock_create_connection, mock_secure_filename):
        """Test s3_upload_file properly secures filenames"""
        with patch.dict(self.flask_app.config, self.default_config):
            # Mock secure_filename to return sanitized name
            mock_secure_filename.return_value = "safe_filename.txt"

            # Create mock S3 objects
            mock_key = MagicMock()
            mock_key.generate_url.return_value = 'https://s3.storage.com/bucket/safe_filename.txt'
            mock_bucket = MagicMock()
            mock_bucket.new_key.return_value = mock_key
            mock_conn = MagicMock()
            mock_conn.get_bucket.return_value = mock_bucket
            mock_create_connection.return_value = mock_conn

            from pybossa.cloud_store_api.s3 import s3_upload_file
            source_file = BytesIO(b"test content")

            result = s3_upload_file(
                's3_bucket', source_file, '../../../malicious_file.txt',
                {}, 'uploads', 'subdir'
            )

            # Verify secure_filename was called
            mock_secure_filename.assert_called_once_with('../../../malicious_file.txt')
            # Verify the key was created with the secured filename
            expected_path = 'uploads/subdir/safe_filename.txt'
            mock_bucket.new_key.assert_called_once_with(expected_path)

    @with_context
    @patch('pybossa.cloud_store_api.s3.create_connection')
    def test_s3_upload_file_long_key_assertion(self, mock_create_connection):
        """Test s3_upload_file assertion for key length < 256"""
        with patch.dict(self.flask_app.config, self.default_config):
            # Create mock S3 objects
            mock_bucket = MagicMock()
            mock_conn = MagicMock()
            mock_conn.get_bucket.return_value = mock_bucket
            mock_create_connection.return_value = mock_conn

            from pybossa.cloud_store_api.s3 import s3_upload_file
            source_file = BytesIO(b"test content")

            # Create a very long filename that would exceed 256 chars
            long_filename = "a" * 250 + ".txt"  # This should cause assertion error
            long_directory = "b" * 50

            with assert_raises(AssertionError):
                s3_upload_file(
                    's3_bucket', source_file, long_filename,
                    {}, long_directory, long_directory
                )

    @with_context
    @patch('pybossa.cloud_store_api.s3.create_connection')
    @patch('magic.from_file')
    def test_check_type_with_unsupported_mime(self, mock_magic, mock_create_connection):
        """Test check_type raises BadRequest for unsupported MIME types"""
        mock_magic.return_value = 'application/x-executable'

        from pybossa.cloud_store_api.s3 import check_type
        with assert_raises(BadRequest) as context:
            check_type('/fake/file.exe')

        assert 'File type not supported' in str(context.exception)
        assert 'application/x-executable' in str(context.exception)

    @with_context
    @patch('pybossa.cloud_store_api.s3.create_connection')
    def test_get_s3_bucket_key_function(self, mock_create_connection):
        """Test get_s3_bucket_key utility function"""
        with patch.dict(self.flask_app.config, self.default_config):
            mock_key = MagicMock()
            mock_bucket = MagicMock()
            mock_bucket.get_key.return_value = mock_key
            mock_conn = MagicMock()
            mock_conn.get_bucket.return_value = mock_bucket
            mock_create_connection.return_value = mock_conn

            from pybossa.cloud_store_api.s3 import get_s3_bucket_key

            s3_url = "https://s3.example.com/bucket/path/to/file.txt"
            bucket, key = get_s3_bucket_key('test_bucket', s3_url)

            assert bucket == mock_bucket
            assert key == mock_key

            # Verify the path was extracted correctly from URL
            mock_bucket.get_key.assert_called_once_with('/bucket/path/to/file.txt', validate=False)

    @with_context
    @patch('pybossa.cloud_store_api.s3.create_connection')
    def test_get_file_from_s3_returns_temp_file(self, mock_create_connection):
        """Test get_file_from_s3 returns proper temporary file"""
        with patch.dict(self.flask_app.config, self.default_config):
            test_content = b"Binary test content"

            mock_key = MagicMock()
            mock_key.get_contents_as_string.return_value = test_content
            mock_bucket = MagicMock()
            mock_bucket.get_key.return_value = mock_key
            mock_conn = MagicMock()
            mock_conn.get_bucket.return_value = mock_bucket
            mock_create_connection.return_value = mock_conn

            from pybossa.cloud_store_api.s3 import get_file_from_s3

            temp_file = get_file_from_s3('test_bucket', '/test/path')

            # Verify temp file contains the right content
            content = temp_file.read()
            assert content == test_content

            # Verify file pointer is at the beginning
            temp_file.seek(0)
            assert temp_file.read() == test_content

    @with_context
    @patch('pybossa.cloud_store_api.s3.create_connection')
    def test_get_file_from_s3_with_string_content(self, mock_create_connection):
        """Test get_file_from_s3 handles string content from S3"""
        with patch.dict(self.flask_app.config, self.default_config):
            test_content = "String content from S3"

            mock_key = MagicMock()
            mock_key.get_contents_as_string.return_value = test_content
            mock_bucket = MagicMock()
            mock_bucket.get_key.return_value = mock_key
            mock_conn = MagicMock()
            mock_conn.get_bucket.return_value = mock_bucket
            mock_create_connection.return_value = mock_conn

            from pybossa.cloud_store_api.s3 import get_file_from_s3

            temp_file = get_file_from_s3('test_bucket', '/test/path')

            # String should be encoded to bytes
            content = temp_file.read()
            assert content == test_content.encode()

    @with_context
    @patch('pybossa.core.signer')
    @patch('time.time')
    def test_upload_email_attachment_filename_sanitization(self, mock_time, mock_signer):
        """Test upload_email_attachment properly sanitizes filenames"""
        with patch.dict(self.flask_app.config, self.default_config):
            mock_time.return_value = 1609459200
            mock_signer.dumps.return_value = "signature"

            # Mock S3 operations
            with patch('pybossa.cloud_store_api.s3.create_connection') as mock_create_connection:
                mock_key = MagicMock()
                mock_bucket = MagicMock()
                mock_bucket.new_key.return_value = mock_key
                mock_conn = MagicMock()
                mock_conn.get_bucket.return_value = mock_bucket
                mock_create_connection.return_value = mock_conn

                # Test with filename that needs sanitization
                unsafe_filename = "../../../etc/passwd"
                content = b"malicious content"
                user_email = "test@example.com"

                result = upload_email_attachment(content, unsafe_filename, user_email)

                # Should use secure_filename internally
                expected_url = "https://example.com/attachment/signature/1609459200-etc_passwd"
                assert result == expected_url

                # Verify S3 path was created with sanitized filename
                expected_s3_path = "attachments/1609459200-etc_passwd"
                mock_bucket.new_key.assert_called_once_with(expected_s3_path)

    @with_context
    @patch('pybossa.cloud_store_api.s3.get_content_and_key_from_s3')
    def test_s3_get_email_attachment_with_binary_content(self, mock_get_content):
        """Test s3_get_email_attachment with binary content"""
        with patch.dict(self.flask_app.config, self.default_config):
            # Mock binary content that can't be decoded as text
            mock_key = MagicMock()
            mock_key.name = "attachments/1609459200-image.png"
            mock_key.content_type = "image/png"

            binary_content = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR'  # PNG header
            mock_get_content.return_value = (binary_content, mock_key)

            result = s3_get_email_attachment("1609459200-image.png")

            expected = {
                "name": "attachments/1609459200-image.png",
                "type": "image/png",
                "content": binary_content
            }

            assert result == expected

    @with_context
    @patch('pybossa.cloud_store_api.s3.s3_upload_from_string')
    def test_upload_json_data_ensure_ascii_false(self, mock_upload):
        """Test upload_json_data preserves unicode characters"""
        with patch.dict(self.flask_app.config, self.default_config):
            mock_upload.return_value = "https://s3.example.com/bucket/unicode.json"

            # Data with unicode characters
            test_data = {
                "english": "Hello",
                "chinese": "你好",
                "japanese": "こんにちは",
                "emoji": "🌍🚀",
                "special_chars": "café naïve résumé"
            }

            result = upload_json_data(
                test_data, "test/path", "unicode.json",
                encryption=False, conn_name="S3_DEFAULT"
            )

            assert result == "https://s3.example.com/bucket/unicode.json"

            # Verify the uploaded content preserves unicode
            mock_upload.assert_called_once()
            args, kwargs = mock_upload.call_args
            uploaded_content = args[1]

            # Parse back to verify unicode is preserved
            parsed_data = json.loads(uploaded_content)
            assert parsed_data == test_data

            # Verify ensure_ascii=False was used (unicode chars not escaped)
            assert "你好" in uploaded_content  # Should be literal, not \u escaped
            assert "🌍" in uploaded_content