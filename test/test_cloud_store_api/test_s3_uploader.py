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

from StringIO import StringIO
from mock import patch, Mock, MagicMock
import boto
from default import Test, with_context
from pybossa.cloud_store_api.s3 import *
from nose.tools import assert_raises
from werkzeug.exceptions import BadRequest
from werkzeug.datastructures import FileStorage
from tempfile import NamedTemporaryFile


class TestS3Uploader(Test):

    def test_check_valid_type(self):
        with NamedTemporaryFile() as fp:
            fp.write('hello world')
            fp.flush()
            check_type(fp.name)

    def test_check_invalid_type(self):
        assert_raises(BadRequest, check_type, 'run.py')

    def test_valid_directory(self):
        validate_directory('test_directory')

    def test_invalid_directory(self):
        assert_raises(RuntimeError, validate_directory, 'hello$world')

    @with_context
    @patch('pybossa.cloud_store_api.s3.boto.s3.key.Key.set_contents_from_filename')
    def test_upload_from_string(self, set_contents):
        with patch.dict(self.flask_app.config, {
            'S3_CONN_KWARGS': {'host': 's3.storage.com'},
            'S3_CUSTOM_HANDLER_HOSTS': ['s3.storage.com']
        }):
            url = s3_upload_from_string('bucket', u'hello world', 'test.txt')
            assert url == 'https://s3.storage.com/bucket/test.txt', url

    @with_context
    @patch('pybossa.cloud_store_api.s3.boto.s3.key.Key.set_contents_from_filename')
    def test_upload_from_string_with_jwt(self, set_contents):
        with patch.dict(self.flask_app.config, {
            'S3_CONN_KWARGS': {'host': 's3.storage.com'},
            'S3_CUSTOM_HANDLER_HOSTS': ['s3.storage.com'],
            'JWT_CONFIG': [
                ('test', 'value', (1,))
            ],
            'JWT_SECRET': 'aa'
        }):
            s3_upload_from_string('bucket', u'hello world', 'test.txt')
            args, kwargs = set_contents.call_args
            assert 'jwt' in kwargs['headers']

    @with_context
    @patch('pybossa.cloud_store_api.s3.io.open')
    def test_upload_from_string_exception(self, open):
        open.side_effect = IOError
        assert_raises(IOError, s3_upload_from_string,
                      'bucket', u'hellow world', 'test.txt')

    @with_context
    @patch('pybossa.cloud_store_api.s3.boto.s3.key.Key.set_contents_from_filename')
    def test_upload_from_string_return_key(self, set_contents):
        with patch.dict(self.flask_app.config, {
            'S3_CONN_KWARGS': {'host': 's3.storage.com'},
            'S3_CUSTOM_HANDLER_HOSTS': ['s3.storage.com']
        }):
            key = s3_upload_from_string('bucket', u'hello world', 'test.txt',
                                        return_key_only=True)
            assert key == 'test.txt', key

    @with_context
    @patch('pybossa.cloud_store_api.s3.boto.s3.key.Key.set_contents_from_filename')
    def test_upload_from_storage(self, set_contents):
        with patch.dict(self.flask_app.config, {
            'S3_CONN_KWARGS': {'host': 's3.storage.com'},
            'S3_CUSTOM_HANDLER_HOSTS': ['s3.storage.com']
        }):
            stream = StringIO('Hello world!')
            fstore = FileStorage(stream=stream,
                                 filename='test.txt',
                                 name='fieldname')
            url = s3_upload_file_storage('bucket', fstore)
            assert url == 'https://s3.storage.com/bucket/test.txt', url

    @with_context
    @patch('pybossa.cloud_store_api.s3.boto.s3.key.Key.set_contents_from_filename')
    @patch('pybossa.cloud_store_api.s3.boto.s3.key.Key.generate_url')
    def test_upload_remove_query_params(self, generate_url, set_content):
        with patch.dict(self.flask_app.config, {
            'S3_CONN_KWARGS': {'host': 's3.storage.com'},
            'S3_CUSTOM_HANDLER_HOSTS': ['s3.storage.com']
        }):
            generate_url.return_value = 'https://s3.storage.com/bucket/key?query_1=aaaa&query_2=bbbb'
            url = s3_upload_file('bucket', 'a_file', 'a_file', {})
            assert url == 'https://s3.storage.com/bucket/key'

    @with_context
    @patch('pybossa.cloud_store_api.s3.boto.s3.bucket.Bucket.delete_key')
    def test_delete_file_from_s3(self, delete_key):
        with patch.dict(self.flask_app.config, {
            'S3_CONN_KWARGS': {'host': 's3.storage.com'},
            'S3_CUSTOM_HANDLER_HOSTS': ['s3.storage.com']
        }):
            delete_file_from_s3('test_bucket', '/the/key')
            delete_key.assert_called_with('/the/key', headers={}, version_id=None)

    @with_context
    @patch('pybossa.cloud_store_api.s3.boto.s3.bucket.Bucket.delete_key')
    def test_delete_file_from_s3_with_jwt(self, delete_key):
        with patch.dict(self.flask_app.config, {
            'S3_CONN_KWARGS': {'host': 's3.storage.com'},
            'S3_CUSTOM_HANDLER_HOSTS': ['s3.storage.com'],
            'JWT_CONFIG': [
                ('test', 'value', (1,))
            ],
            'JWT_SECRET': 'aa'
        }):
            delete_file_from_s3('test_bucket', '/the/key')
            args, kwargs = delete_key.call_args
            assert 'jwt' in kwargs['headers']

    @with_context
    @patch('pybossa.cloud_store_api.s3.boto.s3.bucket.Bucket.delete_key')
    @patch('pybossa.cloud_store_api.s3.app.logger.exception')
    def test_delete_file_from_s3_exception(self, logger, delete_key):
        delete_key.side_effect = boto.exception.S3ResponseError('', '', '')
        with patch.dict(self.flask_app.config, {
            'S3_CONN_KWARGS': {'host': 's3.storage.com'},
            'S3_CUSTOM_HANDLER_HOSTS': ['s3.storage.com']
        }):
            delete_file_from_s3('test_bucket', '/the/key')
            logger.assert_called()

    @with_context
    @patch('pybossa.cloud_store_api.s3.boto.s3.key.Key.get_contents_to_filename')
    def test_get_file_from_s3(self, get_contents):
        with patch.dict(self.flask_app.config, {
            'S3_CONN_KWARGS': {'host': 's3.storage.com'},
            'S3_CUSTOM_HANDLER_HOSTS': ['s3.storage.com']
        }):
            get_file_from_s3('test_bucket', '/the/key')
            get_contents.assert_called()

    @with_context
    @patch('pybossa.cloud_store_api.s3.boto.s3.key.Key.get_contents_to_filename')
    def test_get_file_from_s3_with_jwt(self, get_contents):
        with patch.dict(self.flask_app.config, {
            'S3_CONN_KWARGS': {'host': 's3.storage.com'},
            'S3_CUSTOM_HANDLER_HOSTS': ['s3.storage.com'],
            'JWT_CONFIG': [
                ('test', 'value', (1,))
            ],
            'JWT_SECRET': 'aa'
        }):
            get_file_from_s3('test_bucket', '/the/key')
            args, kwargs = get_contents.call_args
            assert 'jwt' in kwargs['headers']

    @with_context
    def test_no_checksum_key(self):
        response = MagicMock()
        response.status = 200
        key = NoChecksumKey()
        with patch.dict(self.flask_app.config, {
            'CLOUDSTORE_CHECKSUM': False
        }):
            assert key.should_retry(response)

    @with_context
    @patch('pybossa.cloud_store_api.s3.boto.s3.key.Key.should_retry')
    def test_checksum(self, should_retry):
        response = MagicMock()
        response.status = 200
        key = NoChecksumKey()
        key.should_retry(response)
        should_retry.assert_called()


    @with_context
    @patch('pybossa.cloud_store_api.s3.boto.s3.key.Key.should_retry')
    def test_checksum_not_ok(self, should_retry):
        response = MagicMock()
        response.status = 300
        key = NoChecksumKey()
        key.should_retry(response)
        should_retry.assert_called()
        with patch.dict(self.flask_app.config, {
            'CLOUDSTORE_CHECKSUM': False
        }):
            key.should_retry(response)
            should_retry.assert_called()
