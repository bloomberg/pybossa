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

from io import StringIO, BytesIO
from unittest.mock import patch, MagicMock
from test import Test, with_context
from pybossa.cloud_store_api.s3 import *
from pybossa.encryption import AESWithGCM
from nose.tools import assert_raises
from werkzeug.exceptions import BadRequest
from werkzeug.datastructures import FileStorage
from tempfile import NamedTemporaryFile
from botocore.exceptions import ClientError


class TestS3Uploader(Test):

    default_config = {
        'S3_DEFAULT': {
            'host': 's3.storage.com',
            'port': 443,
            'auth_headers': [('test', 'name')]
        }
    }

    util_config = {
        'BCOSV2_PROD_UTIL_URL': "https://s3.storage.env-util.com",
        'S3_DEFAULT': {
            'host': "s3.storage.env-util.com",
            'port': 443,
            'auth_headers': [('test', 'name')]
        }
    }

    def test_check_valid_type(self):
        with NamedTemporaryFile() as fp:
            fp.write(b'hello world')
            fp.flush()
            check_type(fp.name)

    def test_check_invalid_type(self):
        assert_raises(BadRequest, check_type, 'pybossa/run.py')

    def test_valid_directory(self):
        validate_directory('test_directory')

    def test_invalid_directory(self):
        assert_raises(RuntimeError, validate_directory, 'hello$world')

    @with_context
    @patch('boto3.session.Session.client')
    def test_upload_from_string(self, mock_session_client):
        # Mock S3 client with proper presigned URL return
        mock_client = MagicMock()
        mock_session_client.return_value = mock_client
        mock_client.generate_presigned_url.return_value = 'https://s3.storage.com:443/bucket/test.txt'
        
        with patch.dict(self.flask_app.config, self.default_config):
            url = s3_upload_from_string('bucket', 'hello world', 'test.txt')
            assert url == 'https://s3.storage.com:443/bucket/test.txt', url

    @with_context
    @patch('boto3.session.Session.client')
    def test_upload_from_string_util(self, mock_session_client):
        # Mock S3 client with proper presigned URL return that will be processed by host_suffix logic
        mock_client = MagicMock()
        mock_session_client.return_value = mock_client
        mock_client.generate_presigned_url.return_value = 'https://s3.storage.env-util.com:443/bucket/test.txt'
        
        with patch.dict(self.flask_app.config, self.util_config):
            """Test -util keyword dropped from meta url returned from s3 upload."""
            url = s3_upload_from_string('bucket', 'hello world', 'test.txt')
            assert url == 'https://s3.storage.env.com:443/bucket/test.txt', url

    @with_context
    @patch('pybossa.cloud_store_api.s3.io.open')
    def test_upload_from_string_exception(self, open):
        open.side_effect = IOError
        assert_raises(IOError, s3_upload_from_string,
                      'bucket', 'hellow world', 'test.txt')

    @with_context
    @patch('boto3.session.Session.client')
    def test_upload_from_string_return_key(self, mock_session_client):
        # Mock S3 client
        mock_client = MagicMock()
        mock_session_client.return_value = mock_client
        
        with patch.dict(self.flask_app.config, self.default_config):
            key = s3_upload_from_string('bucket', 'hello world', 'test.txt',
                                        return_key_only=True)
            assert key == 'test.txt', key

    @with_context
    @patch('boto3.session.Session.client')
    def test_upload_from_storage(self, mock_session_client):
        # Mock S3 client with proper presigned URL return
        mock_client = MagicMock()
        mock_session_client.return_value = mock_client
        mock_client.generate_presigned_url.return_value = 'https://s3.storage.com:443/bucket/test.txt'
        
        with patch.dict(self.flask_app.config, self.default_config):
            stream = BytesIO(b'Hello world!')
            fstore = FileStorage(stream=stream,
                                 filename='test.txt',
                                 name='fieldname')
            url = s3_upload_file_storage('bucket', fstore)
            assert url == 'https://s3.storage.com:443/bucket/test.txt', url

    @with_context
    @patch('boto3.session.Session.client')
    def test_upload_remove_query_params(self, mock_session_client):
        # Mock S3 client and generate_presigned_url response
        mock_client = MagicMock()
        mock_session_client.return_value = mock_client
        mock_client.generate_presigned_url.return_value = 'https://s3.storage.com/bucket/key?query_1=aaaa&query_2=bbbb'
        
        with patch.dict(self.flask_app.config, self.default_config):
            url = s3_upload_file('bucket', 'a_file', 'a_file', {}, 'dev')
            assert url == 'https://s3.storage.com/bucket/key'

    @with_context
    @patch('boto3.session.Session.client')
    def test_delete_file_from_s3(self, mock_session_client):
        # Mock S3 client
        mock_client = MagicMock()
        mock_session_client.return_value = mock_client
        
        with patch.dict(self.flask_app.config, self.default_config):
            delete_file_from_s3('test_bucket', '/the/key')
            mock_client.delete_object.assert_called_once()

    @with_context
    @patch('boto3.session.Session.client')
    @patch('pybossa.cloud_store_api.s3.app.logger.exception')
    def test_delete_file_from_s3_exception(self, logger, mock_session_client):
        # Mock S3 client with exception
        mock_client = MagicMock()
        mock_session_client.return_value = mock_client
        
        error_response = {
            'Error': {
                'Code': 'ServiceUnavailable',
                'Message': 'Service unavailable'
            },
            'ResponseMetadata': {
                'HTTPStatusCode': 503
            }
        }
        mock_client.delete_object.side_effect = ClientError(error_response, 'DeleteObject')
        
        with patch.dict(self.flask_app.config, self.default_config):
            delete_file_from_s3('test_bucket', '/the/key')
            logger.assert_called()

    @with_context
    @patch('boto3.session.Session.client')
    def test_get_file_from_s3(self, mock_session_client):
        # Mock S3 client and get_object response
        mock_client = MagicMock()
        mock_session_client.return_value = mock_client
        mock_client.get_object.return_value = {'Body': MagicMock(read=MagicMock(return_value=b'abcd'))}
        
        with patch.dict(self.flask_app.config, self.default_config):
            get_file_from_s3('test_bucket', '/the/key')
            # get_object is called twice: once for bucket.get_key() and once for key.get_contents_as_string()
            assert mock_client.get_object.call_count == 2

    @with_context
    @patch('boto3.session.Session.client')
    def test_decrypts_file_from_s3(self, mock_session_client):
        # Mock S3 client and get_object response
        mock_client = MagicMock()
        mock_session_client.return_value = mock_client
        
        config = self.default_config.copy()
        config['FILE_ENCRYPTION_KEY'] = 'abcd'
        config['ENABLE_ENCRYPTION'] = True
        cipher = AESWithGCM('abcd')
        encrypted_data = cipher.encrypt('hello world')
        mock_client.get_object.return_value = {'Body': MagicMock(read=MagicMock(return_value=encrypted_data))}
        
        with patch.dict(self.flask_app.config, config):
            fp = get_file_from_s3('test_bucket', '/the/key', decrypt=True)
            content = fp.read()
            assert content == b'hello world'
