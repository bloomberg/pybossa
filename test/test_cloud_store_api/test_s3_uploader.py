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
    def test_upload_from_string(self, set_contents):
        with patch.dict(self.flask_app.config, self.default_config):
            url = s3_upload_from_string('bucket', 'hello world', 'test.txt')
            assert url == 'https://s3.storage.com:443/bucket/test.txt', url

    @with_context
    def test_upload_from_string_util(self, set_contents):
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
    def test_upload_from_string_return_key(self, set_contents):
        with patch.dict(self.flask_app.config, self.default_config):
            key = s3_upload_from_string('bucket', 'hello world', 'test.txt',
                                        return_key_only=True)
            assert key == 'test.txt', key

    @with_context
    def test_upload_from_storage(self, set_contents):
        with patch.dict(self.flask_app.config, self.default_config):
            stream = BytesIO(b'Hello world!')
            fstore = FileStorage(stream=stream,
                                 filename='test.txt',
                                 name='fieldname')
            url = s3_upload_file_storage('bucket', fstore)
            assert url == 'https://s3.storage.com:443/bucket/test.txt', url

    @with_context
    def test_upload_remove_query_params(self, generate_url, set_content):
        with patch.dict(self.flask_app.config, self.default_config):
            generate_url.return_value = 'https://s3.storage.com/bucket/key?query_1=aaaa&query_2=bbbb'
            url = s3_upload_file('bucket', 'a_file', 'a_file', {}, 'dev')
            assert url == 'https://s3.storage.com/bucket/key'

    @with_context
    def test_delete_file_from_s3(self, delete_key):
        with patch.dict(self.flask_app.config, self.default_config):
            delete_file_from_s3('test_bucket', '/the/key')
            delete_key.assert_called_with('/the/key', headers={}, version_id=None)

    @with_context
    def test_get_file_from_s3(self, get_contents):
        get_contents.return_value = 'abcd'
        with patch.dict(self.flask_app.config, self.default_config):
            get_file_from_s3('test_bucket', '/the/key')
            get_contents.assert_called()

    @with_context
    def test_decrypts_file_from_s3(self, get_contents):
        config = self.default_config.copy()
        config['FILE_ENCRYPTION_KEY'] = 'abcd'
        config['ENABLE_ENCRYPTION'] = True
        cipher = AESWithGCM('abcd')
        get_contents.return_value = cipher.encrypt('hello world')
        with patch.dict(self.flask_app.config, config):
            fp = get_file_from_s3('test_bucket', '/the/key', decrypt=True)
            content = fp.read()
            assert content == b'hello world'
