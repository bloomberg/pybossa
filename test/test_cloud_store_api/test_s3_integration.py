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
from io import BytesIO
from unittest.mock import patch, MagicMock
from test import Test, with_context
from pybossa.cloud_store_api.s3 import (
    s3_upload_from_string, s3_upload_file_storage, get_content_from_s3,
    upload_json_data, upload_email_attachment, s3_get_email_attachment,
    check_type, validate_directory
)
from pybossa.encryption import AESWithGCM
from nose.tools import assert_raises
from werkzeug.exceptions import BadRequest
from werkzeug.datastructures import FileStorage
from tempfile import NamedTemporaryFile


class TestS3Integration(Test):
    """Integration tests for S3 functionality with realistic scenarios"""

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
        'S3_UPLOAD_DIRECTORY': 'uploads',
        'S3_REQUEST_BUCKET_V2': 'request-bucket',
        'S3_TASK_REQUEST_V2': {
            'host': 's3.request.com',
            'port': 443,
            'auth_headers': [('req', 'auth')]
        },
        'SERVER_URL': 'https://example.com'
    }

    @with_context
    @patch('pybossa.cloud_store_api.s3.create_connection')
    def test_full_upload_download_cycle_with_encryption(self, mock_create_connection):
        """Test full upload/download cycle with encryption"""
        with patch.dict(self.flask_app.config, self.default_config):
            # Mock S3 operations
            uploaded_content = None

            def mock_set_contents(file_obj, **kwargs):
                nonlocal uploaded_content
                uploaded_content = file_obj.read()
                file_obj.seek(0)  # Reset file pointer

            def mock_get_contents():
                return uploaded_content

            mock_key = MagicMock()
            mock_key.set_contents_from_file.side_effect = mock_set_contents
            mock_key.get_contents_as_string.side_effect = mock_get_contents
            mock_key.generate_url.return_value = 'https://s3.storage.com/bucket/test.txt'

            mock_bucket = MagicMock()
            mock_bucket.new_key.return_value = mock_key
            mock_bucket.get_key.return_value = mock_key

            mock_conn = MagicMock()
            mock_conn.get_bucket.return_value = mock_bucket

            mock_create_connection.return_value = mock_conn

            # Test data
            original_content = "Hello, encrypted world! 🌍"

            # Upload with encryption
            url = s3_upload_from_string(
                'bucket', original_content, 'test.txt',
                with_encryption=True
            )

            assert url == 'https://s3.storage.com/bucket/test.txt'
            assert uploaded_content is not None

            # Verify content was encrypted (should be different from original)
            assert uploaded_content != original_content.encode()

            # Download and decrypt
            retrieved_content = get_content_from_s3(
                'bucket', '/test.txt', decrypt=True
            )

            assert retrieved_content == original_content

    @with_context
    @patch('pybossa.cloud_store_api.s3.create_connection')
    def test_file_storage_upload_with_directory_structure(self, mock_create_connection):
        """Test FileStorage upload with complex directory structure"""
        with patch.dict(self.flask_app.config, self.default_config):
            # Mock S3 operations
            uploaded_key = None

            def capture_key(key_name):
                nonlocal uploaded_key
                uploaded_key = key_name
                mock_key = MagicMock()
                mock_key.generate_url.return_value = f'https://s3.storage.com/bucket/{key_name}'
                return mock_key

            mock_bucket = MagicMock()
            mock_bucket.new_key.side_effect = capture_key

            mock_conn = MagicMock()
            mock_conn.get_bucket.return_value = mock_bucket

            mock_create_connection.return_value = mock_conn

            # Create FileStorage with CSV content
            csv_content = "id,name,value\n1,Test,100\n2,Demo,200"
            stream = BytesIO(csv_content.encode())
            file_storage = FileStorage(
                stream=stream,
                filename='data.csv',
                content_type='text/csv'
            )

            url = s3_upload_file_storage(
                'bucket', file_storage,
                directory='projects/123/datasets'
            )

            # Verify the correct directory structure was used
            expected_key = 'uploads/projects/123/datasets/data.csv'
            assert uploaded_key == expected_key
            assert expected_key in url

    @with_context
    @patch('pybossa.cloud_store_api.s3.create_connection')
    @patch('pybossa.core.signer')
    @patch('time.time')
    def test_email_attachment_complete_flow(self, mock_time, mock_signer, mock_create_connection):
        """Test complete email attachment upload and retrieval flow"""
        with patch.dict(self.flask_app.config, self.default_config):
            mock_time.return_value = 1609459200
            mock_signer.dumps.return_value = "test_signature"

            # Mock S3 upload
            stored_content = None
            stored_path = None

            def mock_set_contents(content):
                nonlocal stored_content
                stored_content = content

            def mock_new_key(path):
                nonlocal stored_path
                stored_path = path
                mock_key = MagicMock()
                mock_key.set_contents_from_string.side_effect = mock_set_contents
                return mock_key

            mock_bucket = MagicMock()
            mock_bucket.new_key.side_effect = mock_new_key

            mock_conn = MagicMock()
            mock_conn.get_bucket.return_value = mock_bucket

            mock_create_connection.return_value = mock_conn

            # Upload attachment
            content = b"Test PDF content"
            filename = "document.pdf"
            user_email = "user@example.com"
            project_id = 456

            upload_url = upload_email_attachment(content, filename, user_email, project_id)

            expected_url = "https://example.com/attachment/test_signature/1609459200-document.pdf"
            assert upload_url == expected_url
            assert stored_content == content
            assert stored_path == "attachments/1609459200-document.pdf"

            # Mock S3 download for retrieval
            mock_key_retrieve = MagicMock()
            mock_key_retrieve.name = stored_path
            mock_key_retrieve.content_type = "application/pdf"

            with patch('pybossa.cloud_store_api.s3.get_content_and_key_from_s3') as mock_get:
                mock_get.return_value = (stored_content, mock_key_retrieve)

                # Retrieve attachment
                result = s3_get_email_attachment("1609459200-document.pdf")

                expected_result = {
                    "name": stored_path,
                    "type": "application/pdf",
                    "content": content
                }

                assert result == expected_result

    @with_context
    @patch('pybossa.cloud_store_api.s3.create_connection')
    def test_json_data_upload_with_complex_data(self, mock_create_connection):
        """Test JSON data upload with complex nested data structures"""
        with patch.dict(self.flask_app.config, self.default_config):
            # Mock S3 operations to capture uploaded content
            uploaded_content = None

            def mock_upload_from_string(bucket, content, filename, **kwargs):
                nonlocal uploaded_content
                uploaded_content = content
                return f"https://s3.example.com/{bucket}/{filename}"

            with patch('pybossa.cloud_store_api.s3.s3_upload_from_string', side_effect=mock_upload_from_string):
                # Complex test data with various data types
                complex_data = {
                    "metadata": {
                        "version": "1.0",
                        "created_at": "2021-01-01T00:00:00Z",
                        "tags": ["test", "demo", "json"]
                    },
                    "users": [
                        {"id": 1, "name": "Alice", "active": True},
                        {"id": 2, "name": "Bob", "active": False},
                        {"id": 3, "name": "李小明", "active": True}  # Unicode name
                    ],
                    "statistics": {
                        "total_users": 3,
                        "completion_rate": 0.85,
                        "scores": [95.5, 87.2, 92.8, None]
                    },
                    "settings": {
                        "notifications": {
                            "email": True,
                            "sms": False
                        },
                        "privacy_level": "high"
                    },
                    "unicode_text": "Hello 世界! 🌍 Café naïve résumé"
                }

                result = upload_json_data(
                    complex_data,
                    "test/data",
                    "complex.json",
                    encryption=False,
                    conn_name="S3_DEFAULT"
                )

                assert result == "https://s3.example.com/test-bucket-v2/complex.json"

                # Verify uploaded content is valid JSON and preserves data
                parsed_data = json.loads(uploaded_content)
                assert parsed_data == complex_data

                # Verify unicode is preserved (not escaped)
                assert "李小明" in uploaded_content
                assert "🌍" in uploaded_content

    def test_allowed_mime_types_comprehensive(self):
        """Test check_type with all allowed MIME types"""
        from pybossa.cloud_store_api.s3 import allowed_mime_types

        test_files = {
            'application/pdf': 'test.pdf',
            'text/csv': 'data.csv',
            'text/plain': 'readme.txt',
            'image/jpeg': 'photo.jpg',
            'image/png': 'screenshot.png',
            'audio/mpeg': 'song.mp3',
            'application/json': 'config.json',
            'application/zip': 'archive.zip'
        }

        for mime_type, filename in test_files.items():
            assert mime_type in allowed_mime_types, f"MIME type {mime_type} should be allowed"

            with patch('magic.from_file', return_value=mime_type):
                with NamedTemporaryFile() as tmp_file:
                    tmp_file.write(b'test content')
                    tmp_file.flush()
                    # Should not raise any exception
                    check_type(tmp_file.name)

    def test_directory_validation_edge_cases(self):
        """Test directory validation with various edge cases"""
        valid_cases = [
            "",  # Empty string should be valid
            "simple",
            "with_underscore",
            "123numbers",
            "path/with/slashes",
            "very/long/path/with/many/nested/directories/should/be/valid",
            "MixedCase_123/path",
            "/_leading_slash",
            "trailing_slash/",
            "a",  # Single character
            "1",  # Single number
        ]

        for directory in valid_cases:
            # Should not raise any exception
            validate_directory(directory)

        invalid_cases = [
            "with space",
            "with-dash",
            "with.dot",
            "with@symbol",
            "with#hash",
            "with%percent",
            "with&ampersand",
            "with+plus",
            "with=equals",
            "with?question",
            "with!exclamation",
            "path with space/subdir",
            "valid_path/but with space",
        ]

        for directory in invalid_cases:
            with assert_raises(RuntimeError):
                validate_directory(directory)

    @with_context
    @patch('pybossa.cloud_store_api.s3.create_connection')
    def test_error_handling_s3_connection_failure(self, mock_create_connection):
        """Test error handling when S3 connection fails"""
        with patch.dict(self.flask_app.config, self.default_config):
            # Mock connection failure
            mock_create_connection.side_effect = Exception("Connection failed")

            with assert_raises(Exception):
                s3_upload_from_string('bucket', 'test content', 'test.txt')

    @with_context
    @patch('pybossa.cloud_store_api.s3.create_connection')
    def test_s3_upload_with_custom_headers(self, mock_create_connection):
        """Test S3 upload with custom headers"""
        with patch.dict(self.flask_app.config, self.default_config):
            # Track the headers passed to S3
            captured_headers = None

            def mock_set_contents_from_file(file_obj, ExtraArgs=None):
                nonlocal captured_headers
                captured_headers = ExtraArgs

            mock_key = MagicMock()
            mock_key.set_contents_from_file.side_effect = mock_set_contents_from_file
            mock_key.generate_url.return_value = 'https://s3.storage.com/bucket/test.txt'

            mock_bucket = MagicMock()
            mock_bucket.new_key.return_value = mock_key

            mock_conn = MagicMock()
            mock_conn.get_bucket.return_value = mock_bucket

            mock_create_connection.return_value = mock_conn

            # Upload with custom headers
            custom_headers = {
                'Content-Type': 'application/json',
                'Cache-Control': 'max-age=3600',
                'X-Custom-Header': 'test-value'
            }

            s3_upload_from_string(
                'bucket', '{"test": "data"}', 'test.json',
                headers=custom_headers
            )

            # Verify headers were passed correctly
            assert captured_headers is not None
            assert captured_headers['ACL'] == 'bucket-owner-full-control'
            assert captured_headers['Content-Type'] == 'application/json'
            assert captured_headers['Cache-Control'] == 'max-age=3600'
            assert captured_headers['X-Custom-Header'] == 'test-value'