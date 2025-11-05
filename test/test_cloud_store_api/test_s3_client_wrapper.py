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

import ssl
from io import BytesIO
from unittest.mock import patch, MagicMock, Mock
from test import Test, with_context
from pybossa.cloud_store_api.s3_client_wrapper import S3ClientWrapper, MockHTTPRequest
from botocore.exceptions import ClientError
from nose.tools import assert_raises


class TestS3ClientWrapper(Test):

    def setUp(self):
        super(TestS3ClientWrapper, self).setUp()
        self.aws_access_key_id = 'test_access_key'
        self.aws_secret_access_key = 'test_secret_key'
        self.endpoint_url = 'https://s3.test.com'
        self.bucket_name = 'test-bucket'
        self.test_key = 'test/file.txt'

    @patch('boto3.session.Session')
    def test_init_basic(self, mock_session):
        """Test basic initialization of S3ClientWrapper."""
        mock_client = MagicMock()
        mock_session.return_value.client.return_value = mock_client

        wrapper = S3ClientWrapper(
            aws_access_key_id=self.aws_access_key_id,
            aws_secret_access_key=self.aws_secret_access_key,
            endpoint_url=self.endpoint_url
        )

        assert wrapper.aws_access_key_id == self.aws_access_key_id
        assert wrapper.aws_secret_access_key == self.aws_secret_access_key
        assert wrapper.auth_headers == {}
        assert wrapper.host_suffix == ""
        assert wrapper.client == mock_client

    @patch('boto3.session.Session')
    def test_init_with_auth_headers_list(self, mock_session):
        """Test initialization with auth_headers as list of tuples."""
        mock_client = MagicMock()
        mock_session.return_value.client.return_value = mock_client

        auth_headers = [('x-auth-token', 'token123'), ('x-custom', 'value')]

        wrapper = S3ClientWrapper(
            aws_access_key_id=self.aws_access_key_id,
            aws_secret_access_key=self.aws_secret_access_key,
            auth_headers=auth_headers
        )

        expected_headers = {'x-auth-token': 'token123', 'x-custom': 'value'}
        assert wrapper.auth_headers == expected_headers

    @patch('boto3.session.Session')
    def test_init_with_auth_headers_dict(self, mock_session):
        """Test initialization with auth_headers as dictionary."""
        mock_client = MagicMock()
        mock_session.return_value.client.return_value = mock_client

        auth_headers = {'x-auth-token': 'token123', 'x-custom': 'value'}

        wrapper = S3ClientWrapper(
            aws_access_key_id=self.aws_access_key_id,
            aws_secret_access_key=self.aws_secret_access_key,
            auth_headers=auth_headers
        )

        assert wrapper.auth_headers == auth_headers

    @patch('boto3.session.Session')
    def test_init_with_ssl_no_verify(self, mock_session):
        """Test initialization with SSL verification disabled."""
        mock_client = MagicMock()
        mock_session.return_value.client.return_value = mock_client

        wrapper = S3ClientWrapper(
            aws_access_key_id=self.aws_access_key_id,
            aws_secret_access_key=self.aws_secret_access_key,
            s3_ssl_no_verify=True
        )

        # Should have SSL context in http_connection_kwargs
        assert 'context' in wrapper.http_connection_kwargs
        assert isinstance(wrapper.http_connection_kwargs['context'], ssl.SSLContext)

        # Verify client was created with verify=False
        mock_session.return_value.client.assert_called_once()
        call_kwargs = mock_session.return_value.client.call_args[1]
        assert call_kwargs['verify'] is False

    @patch('boto3.session.Session')
    def test_init_with_host_suffix(self, mock_session):
        """Test initialization with host_suffix."""
        mock_client = MagicMock()
        mock_session.return_value.client.return_value = mock_client

        host_suffix = "/proxy"

        wrapper = S3ClientWrapper(
            aws_access_key_id=self.aws_access_key_id,
            aws_secret_access_key=self.aws_secret_access_key,
            host_suffix=host_suffix
        )

        assert wrapper.host_suffix == host_suffix

    @patch('boto3.session.Session')
    def test_init_with_profile(self, mock_session):
        """Test initialization with AWS profile."""
        mock_client = MagicMock()
        mock_session.return_value.client.return_value = mock_client

        profile_name = 'test-profile'

        wrapper = S3ClientWrapper(
            profile_name=profile_name
        )

        # Should create session with profile
        mock_session.assert_called_once_with(profile_name=profile_name)

    @patch('boto3.session.Session')
    def test_before_sign_hook_auth_headers(self, mock_session):
        """Test _before_sign_hook with auth headers."""
        mock_client = MagicMock()
        mock_session.return_value.client.return_value = mock_client

        auth_headers = {'x-auth-token': 'token123', 'x-custom': 'value'}

        wrapper = S3ClientWrapper(
            aws_access_key_id=self.aws_access_key_id,
            aws_secret_access_key=self.aws_secret_access_key,
            auth_headers=auth_headers
        )

        # Create a mock request
        mock_request = MagicMock()
        mock_request.headers = {}
        mock_request.url = 'https://s3.test.com/bucket/key'

        # Call the hook
        wrapper._before_sign_hook(mock_request)

        # Check headers were added
        assert mock_request.headers['x-auth-token'] == 'token123'
        assert mock_request.headers['x-custom'] == 'value'

    @patch('boto3.session.Session')
    def test_before_sign_hook_host_suffix(self, mock_session):
        """Test _before_sign_hook with host_suffix."""
        mock_client = MagicMock()
        mock_session.return_value.client.return_value = mock_client

        host_suffix = "/proxy"

        wrapper = S3ClientWrapper(
            aws_access_key_id=self.aws_access_key_id,
            aws_secret_access_key=self.aws_secret_access_key,
            host_suffix=host_suffix
        )

        # Create a mock request
        mock_request = MagicMock()
        mock_request.headers = {}
        mock_request.url = 'https://s3.test.com/bucket/key'

        # Call the hook
        wrapper._before_sign_hook(mock_request)

        # Check URL was modified
        assert mock_request.url == 'https://s3.test.com/proxy/bucket/key'

    @patch('boto3.session.Session')
    def test_before_sign_hook_host_suffix_no_double_slash(self, mock_session):
        """Test _before_sign_hook prevents double slashes in URL."""
        mock_client = MagicMock()
        mock_session.return_value.client.return_value = mock_client

        host_suffix = "/proxy/"

        wrapper = S3ClientWrapper(
            aws_access_key_id=self.aws_access_key_id,
            aws_secret_access_key=self.aws_secret_access_key,
            host_suffix=host_suffix
        )

        # Create a mock request
        mock_request = MagicMock()
        mock_request.headers = {}
        mock_request.url = 'https://s3.test.com/bucket/key'

        # Call the hook
        wrapper._before_sign_hook(mock_request)

        # Check URL doesn't have double slashes
        assert mock_request.url == 'https://s3.test.com/proxy/bucket/key'

    @patch('boto3.session.Session')
    def test_delete_key_success(self, mock_session):
        """Test successful delete_key operation."""
        mock_client = MagicMock()
        mock_session.return_value.client.return_value = mock_client

        # Mock successful delete response
        mock_client.delete_object.return_value = {
            'ResponseMetadata': {'HTTPStatusCode': 204}
        }

        wrapper = S3ClientWrapper(
            aws_access_key_id=self.aws_access_key_id,
            aws_secret_access_key=self.aws_secret_access_key
        )

        result = wrapper.delete_key(self.bucket_name, self.test_key)

        assert result is True
        mock_client.delete_object.assert_called_once_with(
            Bucket=self.bucket_name, Key=self.test_key
        )

    @patch('boto3.session.Session')
    def test_delete_key_status_200(self, mock_session):
        """Test delete_key with 200 status code."""
        mock_client = MagicMock()
        mock_session.return_value.client.return_value = mock_client

        # Mock delete response with 200 status
        mock_client.delete_object.return_value = {
            'ResponseMetadata': {'HTTPStatusCode': 200}
        }

        wrapper = S3ClientWrapper(
            aws_access_key_id=self.aws_access_key_id,
            aws_secret_access_key=self.aws_secret_access_key
        )

        result = wrapper.delete_key(self.bucket_name, self.test_key)

        assert result is True

    @patch('boto3.session.Session')
    def test_delete_key_unexpected_status(self, mock_session):
        """Test delete_key with unexpected status code."""
        mock_client = MagicMock()
        mock_session.return_value.client.return_value = mock_client

        # Mock delete response with unexpected status
        mock_client.delete_object.return_value = {
            'ResponseMetadata': {'HTTPStatusCode': 500}
        }

        wrapper = S3ClientWrapper(
            aws_access_key_id=self.aws_access_key_id,
            aws_secret_access_key=self.aws_secret_access_key
        )

        with assert_raises(ClientError):
            wrapper.delete_key(self.bucket_name, self.test_key)

    @patch('boto3.session.Session')
    def test_delete_key_client_error(self, mock_session):
        """Test delete_key when client raises ClientError."""
        mock_client = MagicMock()
        mock_session.return_value.client.return_value = mock_client

        # Mock client error
        mock_client.delete_object.side_effect = ClientError(
            {'Error': {'Code': 'NoSuchKey', 'Message': 'Key not found'}},
            'DeleteObject'
        )

        wrapper = S3ClientWrapper(
            aws_access_key_id=self.aws_access_key_id,
            aws_secret_access_key=self.aws_secret_access_key
        )

        with assert_raises(ClientError):
            wrapper.delete_key(self.bucket_name, self.test_key)

    @patch('boto3.session.Session')
    def test_get_object(self, mock_session):
        """Test get_object method."""
        mock_client = MagicMock()
        mock_session.return_value.client.return_value = mock_client

        expected_response = {'Body': BytesIO(b'test content')}
        mock_client.get_object.return_value = expected_response

        wrapper = S3ClientWrapper(
            aws_access_key_id=self.aws_access_key_id,
            aws_secret_access_key=self.aws_secret_access_key
        )

        result = wrapper.get_object(self.bucket_name, self.test_key)

        assert result == expected_response
        mock_client.get_object.assert_called_once_with(
            Bucket=self.bucket_name, Key=self.test_key
        )

    @patch('boto3.session.Session')
    def test_get_object_with_kwargs(self, mock_session):
        """Test get_object method with additional kwargs."""
        mock_client = MagicMock()
        mock_session.return_value.client.return_value = mock_client

        expected_response = {'Body': BytesIO(b'test content')}
        mock_client.get_object.return_value = expected_response

        wrapper = S3ClientWrapper(
            aws_access_key_id=self.aws_access_key_id,
            aws_secret_access_key=self.aws_secret_access_key
        )

        result = wrapper.get_object(
            self.bucket_name,
            self.test_key,
            Range='bytes=0-100',
            VersionId='version123'
        )

        assert result == expected_response
        mock_client.get_object.assert_called_once_with(
            Bucket=self.bucket_name,
            Key=self.test_key,
            Range='bytes=0-100',
            VersionId='version123'
        )

    @patch('boto3.session.Session')
    def test_put_object(self, mock_session):
        """Test put_object method."""
        mock_client = MagicMock()
        mock_session.return_value.client.return_value = mock_client

        expected_response = {'ETag': '"abc123"'}
        mock_client.put_object.return_value = expected_response

        wrapper = S3ClientWrapper(
            aws_access_key_id=self.aws_access_key_id,
            aws_secret_access_key=self.aws_secret_access_key
        )

        body = b'test content'
        result = wrapper.put_object(self.bucket_name, self.test_key, body)

        assert result == expected_response
        mock_client.put_object.assert_called_once_with(
            Bucket=self.bucket_name, Key=self.test_key, Body=body
        )

    @patch('boto3.session.Session')
    def test_put_object_with_kwargs(self, mock_session):
        """Test put_object method with additional kwargs."""
        mock_client = MagicMock()
        mock_session.return_value.client.return_value = mock_client

        expected_response = {'ETag': '"abc123"'}
        mock_client.put_object.return_value = expected_response

        wrapper = S3ClientWrapper(
            aws_access_key_id=self.aws_access_key_id,
            aws_secret_access_key=self.aws_secret_access_key
        )

        body = b'test content'
        result = wrapper.put_object(
            self.bucket_name,
            self.test_key,
            body,
            ContentType='text/plain',
            Metadata={'key': 'value'}
        )

        assert result == expected_response
        mock_client.put_object.assert_called_once_with(
            Bucket=self.bucket_name,
            Key=self.test_key,
            Body=body,
            ContentType='text/plain',
            Metadata={'key': 'value'}
        )

    @patch('boto3.session.Session')
    def test_build_base_http_request(self, mock_session):
        """Test build_base_http_request method."""
        mock_client = MagicMock()
        mock_session.return_value.client.return_value = mock_client

        wrapper = S3ClientWrapper(
            aws_access_key_id=self.aws_access_key_id,
            aws_secret_access_key=self.aws_secret_access_key
        )

        method = 'GET'
        path = '/bucket/key'
        auth_path = '/bucket/key'
        headers = {'Content-Type': 'application/json'}

        result = wrapper.build_base_http_request(method, path, auth_path, headers)

        assert isinstance(result, MockHTTPRequest)
        assert result.method == method
        assert result.path == path
        assert result.auth_path == auth_path
        assert result.headers == headers

    @patch('boto3.session.Session')
    def test_raw_client_access(self, mock_session):
        """Test accessing the raw boto3 client."""
        mock_client = MagicMock()
        mock_session.return_value.client.return_value = mock_client

        wrapper = S3ClientWrapper(
            aws_access_key_id=self.aws_access_key_id,
            aws_secret_access_key=self.aws_secret_access_key
        )

        assert wrapper.client == mock_client

    @patch('boto3.session.Session')
    def test_list_objects(self, mock_session):
        """Test list_objects method."""
        mock_client = MagicMock()
        mock_session.return_value.client.return_value = mock_client

        expected_response = {
            'Contents': [
                {'Key': 'file1.txt', 'Size': 100},
                {'Key': 'file2.txt', 'Size': 200}
            ]
        }
        mock_client.list_objects_v2.return_value = expected_response

        wrapper = S3ClientWrapper(
            aws_access_key_id=self.aws_access_key_id,
            aws_secret_access_key=self.aws_secret_access_key
        )

        result = wrapper.list_objects(self.bucket_name, prefix='test/')

        assert result == expected_response
        mock_client.list_objects_v2.assert_called_once_with(
            Bucket=self.bucket_name, Prefix='test/'
        )

    @patch('boto3.session.Session')
    def test_list_objects_with_kwargs(self, mock_session):
        """Test list_objects method with additional kwargs."""
        mock_client = MagicMock()
        mock_session.return_value.client.return_value = mock_client

        expected_response = {'Contents': []}
        mock_client.list_objects_v2.return_value = expected_response

        wrapper = S3ClientWrapper(
            aws_access_key_id=self.aws_access_key_id,
            aws_secret_access_key=self.aws_secret_access_key
        )

        result = wrapper.list_objects(
            self.bucket_name,
            prefix='test/',
            MaxKeys=10,
            StartAfter='file1.txt'
        )

        assert result == expected_response
        mock_client.list_objects_v2.assert_called_once_with(
            Bucket=self.bucket_name,
            Prefix='test/',
            MaxKeys=10,
            StartAfter='file1.txt'
        )

    @patch('boto3.session.Session')
    def test_raw_method(self, mock_session):
        """Test raw method returns the boto3 client."""
        mock_client = MagicMock()
        mock_session.return_value.client.return_value = mock_client

        wrapper = S3ClientWrapper(
            aws_access_key_id=self.aws_access_key_id,
            aws_secret_access_key=self.aws_secret_access_key
        )

        assert wrapper.raw() == mock_client

    @patch('boto3.session.Session')
    def test_inherited_get_key(self, mock_session):
        """Test inherited get_key method from BaseConnection."""
        mock_client = MagicMock()
        mock_session.return_value.client.return_value = mock_client

        expected_response = {'Body': BytesIO(b'test content')}
        mock_client.get_object.return_value = expected_response

        wrapper = S3ClientWrapper(
            aws_access_key_id=self.aws_access_key_id,
            aws_secret_access_key=self.aws_secret_access_key
        )

        result = wrapper.get_key(self.bucket_name, self.test_key)

        assert result == expected_response
        mock_client.get_object.assert_called_once_with(
            Bucket=self.bucket_name, Key=self.test_key
        )

    @patch('boto3.session.Session')
    def test_inherited_get_key_client_error(self, mock_session):
        """Test inherited get_key method when client raises ClientError."""
        mock_client = MagicMock()
        mock_session.return_value.client.return_value = mock_client

        # Mock client error
        client_error = ClientError(
            {
                'Error': {'Code': 'NoSuchKey', 'Message': 'Key not found', 'Key': self.test_key},
                'ResponseMetadata': {'HTTPStatusCode': 404}
            },
            'GetObject'
        )
        mock_client.get_object.side_effect = client_error

        wrapper = S3ClientWrapper(
            aws_access_key_id=self.aws_access_key_id,
            aws_secret_access_key=self.aws_secret_access_key
        )

        with assert_raises(ClientError):
            wrapper.get_key(self.bucket_name, self.test_key)

    @patch('boto3.session.Session')
    def test_inherited_get_head(self, mock_session):
        """Test inherited get_head method from BaseConnection."""
        mock_client = MagicMock()
        mock_session.return_value.client.return_value = mock_client

        expected_response = {
            'ContentLength': 1024,
            'ContentType': 'text/plain',
            'ETag': '"abc123"'
        }
        mock_client.head_object.return_value = expected_response

        wrapper = S3ClientWrapper(
            aws_access_key_id=self.aws_access_key_id,
            aws_secret_access_key=self.aws_secret_access_key
        )

        result = wrapper.get_head(self.bucket_name, self.test_key)

        assert result == expected_response
        mock_client.head_object.assert_called_once_with(
            Bucket=self.bucket_name, Key=self.test_key
        )


class TestMockHTTPRequest(Test):

    def test_init(self):
        """Test MockHTTPRequest initialization."""
        method = 'POST'
        path = '/bucket/key'
        auth_path = '/bucket/key'
        headers = {'Content-Type': 'application/json', 'Authorization': 'Bearer token'}

        request = MockHTTPRequest(method, path, auth_path, headers)

        assert request.method == method
        assert request.path == path
        assert request.auth_path == auth_path
        assert request.headers == headers
        # Ensure headers are copied, not referenced
        assert request.headers is not headers

    def test_authorize_with_auth_headers(self):
        """Test authorize method with auth_headers."""
        request = MockHTTPRequest('GET', '/path', '/path', {})

        # Mock connection with auth_headers
        connection = MagicMock()
        connection.auth_headers = {
            'x-auth-token': 'token123',
            'x-custom': 'custom-value'
        }

        request.authorize(connection)

        assert request.headers['x-auth-token'] == 'token123'
        assert request.headers['x-custom'] == 'custom-value'

    def test_authorize_with_access_key_replacement(self):
        """Test authorize method with access_key replacement."""
        request = MockHTTPRequest('GET', '/path', '/path', {})

        # Mock connection with access_key placeholder
        connection = MagicMock()
        connection.auth_headers = {
            'x-auth-key': 'access_key',
            'x-other': 'other-value'
        }
        connection.aws_access_key_id = 'actual_access_key_123'

        request.authorize(connection)

        assert request.headers['x-auth-key'] == 'actual_access_key_123'
        assert request.headers['x-other'] == 'other-value'

    def test_authorize_with_access_key_no_replacement_when_none(self):
        """Test authorize method when access_key is None."""
        request = MockHTTPRequest('GET', '/path', '/path', {})

        # Mock connection with access_key placeholder but no actual access key
        connection = MagicMock()
        connection.auth_headers = {'x-auth-key': 'access_key'}
        connection.aws_access_key_id = None

        request.authorize(connection)

        # Should keep the literal 'access_key' value
        assert request.headers['x-auth-key'] == 'access_key'

    def test_authorize_without_auth_headers(self):
        """Test authorize method without auth_headers."""
        request = MockHTTPRequest('GET', '/path', '/path', {'existing': 'header'})

        # Mock connection without auth_headers
        connection = MagicMock()
        # Don't add auth_headers attribute

        request.authorize(connection)

        # Headers should remain unchanged
        assert request.headers == {'existing': 'header'}

    def test_authorize_preserves_existing_headers(self):
        """Test authorize method preserves existing headers."""
        existing_headers = {'existing-header': 'existing-value'}
        request = MockHTTPRequest('GET', '/path', '/path', existing_headers)

        # Mock connection with auth_headers
        connection = MagicMock()
        connection.auth_headers = {'new-header': 'new-value'}

        request.authorize(connection)

        # Both existing and new headers should be present
        assert request.headers['existing-header'] == 'existing-value'
        assert request.headers['new-header'] == 'new-value'