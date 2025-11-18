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
    @patch('pybossa.cloud_store_api.s3.io.open')
    def test_upload_from_string_exception(self, open):
        open.side_effect = IOError
        assert_raises(IOError, s3_upload_from_string,
                      'bucket', 'hellow world', 'test.txt')

    @with_context
    @patch('pybossa.cloud_store_api.s3.get_s3_bucket_key')
    @patch('pybossa.cloud_store_api.s3.app.logger.exception')
    def test_delete_file_from_s3_exception(self, logger, get_s3_bucket_key):
        get_s3_bucket_key.side_effect = ClientError(
            error_response={
                'Error': {
                    'Code': 'NoSuchKey',
                    'Message': 'The specified key does not exist'
                }
            },
            operation_name='DeleteObject'
        )
        with patch.dict(self.flask_app.config, self.default_config):
            delete_file_from_s3('test_bucket', '/the/key')
            logger.assert_called()
