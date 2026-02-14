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
from pybossa.cloud_store_api.connection import create_connection
from nose.tools import assert_raises
from unittest.mock import patch
from nose.tools import assert_raises
from werkzeug.exceptions import BadRequest


# TestS3Connection class removed - all tests were obsolete boto2 implementation tests


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
