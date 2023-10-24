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

import jwt
import io
from unittest.mock import patch
from test import Test, with_context
from pybossa.cloud_store_api.connection import create_connection, CustomAuthHandler, CustomProvider
from nose.tools import assert_raises
from boto.auth_handler import NotReadyToAuthenticate
from unittest.mock import patch
from nose.tools import assert_raises
from werkzeug.exceptions import BadRequest


class TestS3Connection(Test):

    auth_headers = [('test', 'name')]

    @with_context
    def test_path(self):
        conn = create_connection(host='s3.store.com', host_suffix='/test',
                                 auth_headers=self.auth_headers)
        path = conn.get_path(path='/')
        assert path == '/test/', path

    @with_context
    def test_path_key(self):
        conn = create_connection(host='s3.store.com', host_suffix='/test',
                                 auth_headers=self.auth_headers)
        path = conn.get_path(path='/bucket/key')
        assert path == '/test/bucket/key', path

    @with_context
    def test_no_verify_context(self):
        conn = create_connection(host='s3.store.com', s3_ssl_no_verify=True,
                                 auth_headers=self.auth_headers)
        assert 'context' in conn.http_connection_kwargs

        conn = create_connection(host='s3.store.com', auth_headers=self.auth_headers)
        assert 'context' not in conn.http_connection_kwargs

    @with_context
    def test_auth_handler_error(self):
        provider = CustomProvider('aws')
        assert_raises(NotReadyToAuthenticate, CustomAuthHandler,
                      's3.store.com', None, provider)

    @with_context
    def test_custom_headers(self):
        header = 'x-custom-access-key'
        host = 's3.store.com'
        access_key = 'test-access-key'

        conn = create_connection(host=host, aws_access_key_id=access_key,
                                 auth_headers=[(header, 'access_key')])
        http = conn.build_base_http_request('GET', '/', None)
        http.authorize(conn)
        assert header in http.headers
        assert http.headers[header] == access_key

    @with_context
    @patch('pybossa.cloud_store_api.connection.S3Connection.make_request')
    def test_proxied_connection(self, make_request):
        params = {
            'host': 's3.test.com',
            'port': 443,
            'object_service': 'tests3',
            'client_secret': 'abcd',
            'client_id': 'test_id',
            'auth_headers': [('test', 'object-service')]
        }
        conn = create_connection(**params)
        conn.make_request('GET', 'test_bucket', 'test_key')

        make_request.assert_called()
        args, kwargs = make_request.call_args
        headers = args[3]
        assert headers['x-objectservice-id'] == 'TESTS3'

        # jwt.decode accepts 'algorithms' arguments, not 'algorithm'
        # Reference: https://pyjwt.readthedocs.io/en/stable/api.html#jwt.decode
        jwt_payload = jwt.decode(headers['jwt'], 'abcd', algorithms=['HS256'])
        assert jwt_payload['path'] == '/test_bucket/test_key'

        bucket = conn.get_bucket('test_bucket', validate=False)
        key = bucket.get_key('test_key', validate=False)
        assert key.generate_url(0).split('?')[0] == 'https://s3.test.com:443/test_bucket/test_key'

    @with_context
    @patch('pybossa.cloud_store_api.connection.S3Connection.make_request')
    def test_proxied_connection_url(self, make_request):
        params = {
            'host': 's3.test.com',
            'port': 443,
            'object_service': 'tests3',
            'client_secret': 'abcd',
            'client_id': 'test_id',
            'host_suffix': '/test',
            'auth_headers': [('test', 'object-service')]
        }
        conn = create_connection(**params)
        conn.make_request('GET', 'test_bucket', 'test_key')

        make_request.assert_called()
        args, kwargs = make_request.call_args
        headers = args[3]
        assert headers['x-objectservice-id'] == 'TESTS3'

        jwt_payload = jwt.decode(headers['jwt'], 'abcd', algorithms=['HS256'])
        assert jwt_payload['path'] == '/test/test_bucket/test_key'

        bucket = conn.get_bucket('test_bucket', validate=False)
        key = bucket.get_key('test_key', validate=False)
        assert key.generate_url(0).split('?')[0] == 'https://s3.test.com:443/test/test_bucket/test_key'


class TestCustomConnectionV2(Test):

    default_config = {
        "S3_CONN_TYPE": "storev1",
        "S3_CONN_TYPE_V2": "storev2"
        }
    access_key, secret_key = "test-access-key", "test-secret-key"

    @with_context
    @patch("pybossa.cloud_store_api.connection.Session")
    def test_boto3_session_called(self, mock_boto3_session):
        with patch.dict(self.flask_app.config, self.default_config):
            conn = create_connection(aws_access_key_id=self.access_key,
                                     aws_secret_access_key=self.secret_key,
                                     endpoint="s3.store.com",
                                     store="storev2")
            assert mock_boto3_session.called

    @with_context
    def test_boto3_session_not_called(self):
        with assert_raises(BadRequest):
            create_connection(aws_access_key_id=self.access_key,
                                    aws_secret_access_key=self.secret_key,
                                    endpoint="s3.store.com",
                                    store="storev2")

    @with_context
    @patch("pybossa.cloud_store_api.connection.CustomConnection")
    @patch("pybossa.cloud_store_api.connection.Session")
    def test_custom_conn_called(self, mock_boto3_session, mock_conn):
        with patch.dict(self.flask_app.config, self.default_config):
            conn = create_connection(aws_access_key_id=self.access_key,
                                     aws_secret_access_key=self.secret_key,
                                     store="storev1")
            assert mock_conn.called
            assert mock_boto3_session.called is False

    @with_context
    @patch("pybossa.cloud_store_api.connection.Session.client")
    def test_get_key_success(self, mock_client):
        with patch.dict(self.flask_app.config, self.default_config):
            conn = create_connection(aws_access_key_id=self.access_key,
                                     aws_secret_access_key=self.secret_key,
                                     store="storev2")
            bucket_name = "testv2"
            path = "path/to/key"
            bucket = conn.get_bucket(bucket_name=bucket_name)
            key = bucket.get_key(path)
            assert mock_client.return_value.get_object.called
            mock_client.return_value.get_object.assert_called_with(Bucket=bucket_name, Key=path)

    @with_context
    @patch("pybossa.cloud_store_api.connection.Session.client")
    def test_get_delete_key_success(self, mock_client):
        with patch.dict(self.flask_app.config, self.default_config):
            conn = create_connection(aws_access_key_id=self.access_key,
                                    aws_secret_access_key=self.secret_key,
                                    store="storev2")
            bucket_name = "testv2"
            path = "path/to/key"
            bucket = conn.get_bucket(bucket_name=bucket_name)
            key = bucket.get_key(path)
            key.delete()
            assert mock_client.return_value.delete_object.called
            mock_client.return_value.delete_object.assert_called_with(Bucket=bucket_name, Key=path)

    @with_context
    @patch("pybossa.cloud_store_api.connection.Session.client")
    def test_get_contents_as_string(self, mock_client):
        with patch.dict(self.flask_app.config, self.default_config):
            conn = create_connection(aws_access_key_id=self.access_key,
                                     aws_secret_access_key=self.secret_key,
                                     store="storev2")
            bucket_name = "testv2"
            path = "path/to/key"
            bucket = conn.get_bucket(bucket_name=bucket_name)
            key = bucket.get_key(path)
            content = key.get_contents_as_string()
            assert mock_client.return_value.get_object.return_value["Body"].read.called

    @with_context
    @patch("pybossa.cloud_store_api.connection.Session.client")
    def test_set_contents(self, mock_client):
        with patch.dict(self.flask_app.config, self.default_config):
            conn = create_connection(aws_access_key_id=self.access_key,
                                     aws_secret_access_key=self.secret_key,
                                     store="storev2")
            bucket_name = "testv2"
            path = "path/to/key"
            bucket = conn.get_bucket(bucket_name=bucket_name)
            key = bucket.get_key(path)
            content = "test data"
            key.set_contents_from_string(content)
            assert mock_client.return_value.upload_fileobj.called

            source = io.BytesIO(content.encode())
            key.set_contents_from_file(source)
            assert mock_client.return_value.upload_fileobj.called

    @with_context
    @patch("pybossa.cloud_store_api.connection.Session.client")
    def test_key_updates(self, mock_client):
        with patch.dict(self.flask_app.config, self.default_config):
            conn = create_connection(aws_access_key_id=self.access_key,
                                     aws_secret_access_key=self.secret_key,
                                     store="storev2")
            bucket_name = "testv2"
            path, new_path = "path/to/key", "newpath/to/key"
            bucket = conn.get_bucket(bucket_name=bucket_name)
            key = bucket.new_key(path)
            assert mock_client.return_value.put_object.called

            new_key = bucket.get_key(new_path)
            bucket.copy_key(key, new_key)
            assert mock_client.return_value.copy.called


    @with_context
    @patch("pybossa.cloud_store_api.connection.Session.client")
    def test_key_generate_url_and_head(self, mock_client):
        with patch.dict(self.flask_app.config, self.default_config):
            conn = create_connection(aws_access_key_id=self.access_key,
                                    aws_secret_access_key=self.secret_key,
                                    store="storev2")
            bucket_name = "testv2"
            path = "path/to/key"
            bucket = conn.get_bucket(bucket_name=bucket_name)
            key = bucket.new_key(path)
            key.generate_url()
            assert mock_client.return_value.generate_presigned_url.called
            key.get_object_head()
            assert mock_client.return_value.head_object.called
