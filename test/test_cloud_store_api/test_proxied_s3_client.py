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

import time
import jwt
import logging
from io import BytesIO
from unittest.mock import patch, MagicMock, Mock
from test import Test, with_context
from pybossa.cloud_store_api.proxied_s3_client import (
    ProxiedS3Client,
    ProxiedBucketAdapter,
    ProxiedKeyAdapter
)
from botocore.exceptions import ClientError
from nose.tools import assert_raises


class TestProxiedS3Client(Test):

    def setUp(self):
        super(TestProxiedS3Client, self).setUp()
        self.client_id = 'test_client_id'
        self.client_secret = 'test_client_secret'
        self.object_service = 'test_service'
        self.endpoint_url = 'https://s3.test.com'
        self.bucket_name = 'test-bucket'
        self.test_key = 'test/file.txt'
        self.region_claim = 'us-east-1'

    @patch('boto3.session.Session')
    def test_init_basic(self, mock_session):
        """Test basic initialization of ProxiedS3Client."""
        mock_client = MagicMock()
        mock_session.return_value.client.return_value = mock_client

        client = ProxiedS3Client(
            client_id=self.client_id,
            client_secret=self.client_secret,
            object_service=self.object_service
        )

        assert client.client_id == self.client_id
        assert client.client_secret == self.client_secret
        assert client.object_service == self.object_service
        assert client.region_claim == "ny"  # default value
        assert client.host_suffix == ""
        assert client.extra_headers == {}
        assert client.logger is None
        assert client.client == mock_client

    @patch('boto3.session.Session')
    def test_init_with_all_parameters(self, mock_session):
        """Test initialization with all parameters."""
        mock_client = MagicMock()
        mock_session.return_value.client.return_value = mock_client

        extra_headers = {'x-custom': 'value'}
        logger = logging.getLogger('test')
        host_suffix = '/proxy'

        client = ProxiedS3Client(
            client_id=self.client_id,
            client_secret=self.client_secret,
            object_service=self.object_service,
            region_claim=self.region_claim,
            host_suffix=host_suffix,
            extra_headers=extra_headers,
            endpoint_url=self.endpoint_url,
            region_name='us-west-2',
            profile_name='test-profile',
            aws_access_key_id='test-access-key',
            aws_secret_access_key='test-secret-key',
            aws_session_token='test-token',
            s3_ssl_no_verify=True,
            logger=logger
        )

        assert client.region_claim == self.region_claim
        assert client.host_suffix == host_suffix
        assert client.extra_headers == extra_headers
        assert client.logger == logger

    @patch('boto3.session.Session')
    def test_init_with_profile(self, mock_session):
        """Test initialization with AWS profile."""
        mock_client = MagicMock()
        mock_session.return_value.client.return_value = mock_client

        profile_name = 'test-profile'

        client = ProxiedS3Client(
            client_id=self.client_id,
            client_secret=self.client_secret,
            object_service=self.object_service,
            profile_name=profile_name
        )

        # Should create session with profile
        mock_session.assert_called_once_with(profile_name=profile_name)

    @patch('boto3.session.Session')
    def test_init_with_ssl_no_verify(self, mock_session):
        """Test initialization with SSL verification disabled."""
        mock_client = MagicMock()
        mock_session.return_value.client.return_value = mock_client

        client = ProxiedS3Client(
            client_id=self.client_id,
            client_secret=self.client_secret,
            object_service=self.object_service,
            s3_ssl_no_verify=True
        )

        # Verify client was created with verify=False
        mock_session.return_value.client.assert_called_once()
        call_kwargs = mock_session.return_value.client.call_args[1]
        assert call_kwargs['verify'] is False

    @patch('boto3.session.Session')
    def test_create_jwt(self, mock_session):
        """Test JWT creation."""
        mock_client = MagicMock()
        mock_session.return_value.client.return_value = mock_client

        client = ProxiedS3Client(
            client_id=self.client_id,
            client_secret=self.client_secret,
            object_service=self.object_service,
            region_claim=self.region_claim
        )

        method = 'GET'
        host = 's3.test.com'
        path = '/bucket/key'

        # Mock time.time() for predictable JWT
        with patch('time.time', return_value=1234567890):
            token = client._create_jwt(method, host, path)

        # Decode and verify JWT
        decoded = jwt.decode(token, self.client_secret, algorithms=['HS256'])

        assert decoded['iat'] == 1234567890
        assert decoded['nbf'] == 1234567890
        assert decoded['exp'] == 1234567890 + 300
        assert decoded['method'] == method
        assert decoded['iss'] == self.client_id
        assert decoded['host'] == host
        assert decoded['path'] == path
        assert decoded['region'] == self.region_claim

    @patch('boto3.session.Session')
    def test_before_sign_hook_basic(self, mock_session):
        """Test _before_sign_hook basic functionality."""
        mock_client = MagicMock()
        mock_session.return_value.client.return_value = mock_client

        extra_headers = {'x-custom': 'test-value'}
        logger = MagicMock()

        client = ProxiedS3Client(
            client_id=self.client_id,
            client_secret=self.client_secret,
            object_service=self.object_service,
            extra_headers=extra_headers,
            logger=logger
        )

        # Create mock request
        mock_request = MagicMock()
        mock_request.url = 'https://s3.test.com/bucket/key'
        mock_request.method = 'GET'
        mock_request.headers = {}

        # Call the hook
        with patch.object(client, '_create_jwt', return_value='test-jwt-token'):
            client._before_sign_hook(mock_request, 'GetObject')

        # Verify headers were added
        assert mock_request.headers['x-objectservice-id'] == self.object_service.upper()
        assert mock_request.headers['x-custom'] == 'test-value'
        assert mock_request.headers['jwt'] == 'test-jwt-token'

        # Verify logger was called
        logger.info.assert_called_once()

    @patch('boto3.session.Session')
    def test_before_sign_hook_with_host_suffix(self, mock_session):
        """Test _before_sign_hook with host_suffix."""
        mock_client = MagicMock()
        mock_session.return_value.client.return_value = mock_client

        host_suffix = '/proxy'

        client = ProxiedS3Client(
            client_id=self.client_id,
            client_secret=self.client_secret,
            object_service=self.object_service,
            host_suffix=host_suffix
        )

        # Create mock request
        mock_request = MagicMock()
        mock_request.url = 'https://s3.test.com/bucket/key'
        mock_request.method = 'GET'
        mock_request.headers = {}

        # Call the hook
        with patch.object(client, '_create_jwt', return_value='test-jwt-token'):
            client._before_sign_hook(mock_request, 'GetObject')

        # Verify URL was modified
        assert mock_request.url == 'https://s3.test.com/proxy/bucket/key'

    @patch('boto3.session.Session')
    def test_before_sign_hook_no_double_slash(self, mock_session):
        """Test _before_sign_hook prevents double slashes."""
        mock_client = MagicMock()
        mock_session.return_value.client.return_value = mock_client

        host_suffix = '/proxy/'

        client = ProxiedS3Client(
            client_id=self.client_id,
            client_secret=self.client_secret,
            object_service=self.object_service,
            host_suffix=host_suffix
        )

        # Create mock request
        mock_request = MagicMock()
        mock_request.url = 'https://s3.test.com/bucket/key'
        mock_request.method = 'GET'
        mock_request.headers = {}

        # Call the hook
        with patch.object(client, '_create_jwt', return_value='test-jwt-token'):
            client._before_sign_hook(mock_request, 'GetObject')

        # Verify URL doesn't have double slashes
        assert mock_request.url == 'https://s3.test.com/proxy/bucket/key'

    @patch('boto3.session.Session')
    def test_delete_key_success(self, mock_session):
        """Test successful delete_key operation."""
        mock_client = MagicMock()
        mock_session.return_value.client.return_value = mock_client

        # Mock successful delete response with 204
        mock_client.delete_object.return_value = {
            'ResponseMetadata': {'HTTPStatusCode': 204}
        }

        client = ProxiedS3Client(
            client_id=self.client_id,
            client_secret=self.client_secret,
            object_service=self.object_service
        )

        result = client.delete_key(self.bucket_name, self.test_key)

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

        client = ProxiedS3Client(
            client_id=self.client_id,
            client_secret=self.client_secret,
            object_service=self.object_service
        )

        result = client.delete_key(self.bucket_name, self.test_key)

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

        client = ProxiedS3Client(
            client_id=self.client_id,
            client_secret=self.client_secret,
            object_service=self.object_service
        )

        with assert_raises(ClientError):
            client.delete_key(self.bucket_name, self.test_key)

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

        client = ProxiedS3Client(
            client_id=self.client_id,
            client_secret=self.client_secret,
            object_service=self.object_service
        )

        with assert_raises(ClientError):
            client.delete_key(self.bucket_name, self.test_key)

    @patch('boto3.session.Session')
    def test_get_object(self, mock_session):
        """Test get_object method."""
        mock_client = MagicMock()
        mock_session.return_value.client.return_value = mock_client

        expected_response = {'Body': BytesIO(b'test content')}
        mock_client.get_object.return_value = expected_response

        client = ProxiedS3Client(
            client_id=self.client_id,
            client_secret=self.client_secret,
            object_service=self.object_service
        )

        result = client.get_object(self.bucket_name, self.test_key)

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

        client = ProxiedS3Client(
            client_id=self.client_id,
            client_secret=self.client_secret,
            object_service=self.object_service
        )

        result = client.get_object(
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

        client = ProxiedS3Client(
            client_id=self.client_id,
            client_secret=self.client_secret,
            object_service=self.object_service
        )

        body = b'test content'
        result = client.put_object(self.bucket_name, self.test_key, body)

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

        client = ProxiedS3Client(
            client_id=self.client_id,
            client_secret=self.client_secret,
            object_service=self.object_service
        )

        body = b'test content'
        result = client.put_object(
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

        client = ProxiedS3Client(
            client_id=self.client_id,
            client_secret=self.client_secret,
            object_service=self.object_service
        )

        result = client.list_objects(self.bucket_name, prefix='test/')

        assert result == expected_response
        mock_client.list_objects_v2.assert_called_once_with(
            Bucket=self.bucket_name, Prefix='test/'
        )

    @patch('boto3.session.Session')
    def test_upload_file(self, mock_session):
        """Test upload_file method."""
        mock_client = MagicMock()
        mock_session.return_value.client.return_value = mock_client

        expected_response = None  # upload_file typically returns None
        mock_client.upload_file.return_value = expected_response

        client = ProxiedS3Client(
            client_id=self.client_id,
            client_secret=self.client_secret,
            object_service=self.object_service
        )

        filename = '/path/to/file.txt'
        result = client.upload_file(filename, self.bucket_name, self.test_key)

        assert result == expected_response
        mock_client.upload_file.assert_called_once_with(
            filename, self.bucket_name, self.test_key, ExtraArgs={}
        )

    @patch('boto3.session.Session')
    def test_upload_file_with_kwargs(self, mock_session):
        """Test upload_file method with additional kwargs."""
        mock_client = MagicMock()
        mock_session.return_value.client.return_value = mock_client

        client = ProxiedS3Client(
            client_id=self.client_id,
            client_secret=self.client_secret,
            object_service=self.object_service
        )

        filename = '/path/to/file.txt'
        extra_args = {'ContentType': 'text/plain', 'ACL': 'public-read'}

        client.upload_file(filename, self.bucket_name, self.test_key, **extra_args)

        mock_client.upload_file.assert_called_once_with(
            filename, self.bucket_name, self.test_key, ExtraArgs=extra_args
        )

    @patch('boto3.session.Session')
    def test_raw_method(self, mock_session):
        """Test raw method returns the boto3 client."""
        mock_client = MagicMock()
        mock_session.return_value.client.return_value = mock_client

        client = ProxiedS3Client(
            client_id=self.client_id,
            client_secret=self.client_secret,
            object_service=self.object_service
        )

        assert client.raw() == mock_client

    @patch('boto3.session.Session')
    def test_get_bucket(self, mock_session):
        """Test get_bucket method returns ProxiedBucketAdapter."""
        mock_client = MagicMock()
        mock_session.return_value.client.return_value = mock_client

        client = ProxiedS3Client(
            client_id=self.client_id,
            client_secret=self.client_secret,
            object_service=self.object_service
        )

        bucket_adapter = client.get_bucket(self.bucket_name)

        assert isinstance(bucket_adapter, ProxiedBucketAdapter)
        assert bucket_adapter.client == client
        assert bucket_adapter.name == self.bucket_name


class TestProxiedBucketAdapter(Test):

    def setUp(self):
        super(TestProxiedBucketAdapter, self).setUp()
        self.mock_client = MagicMock()
        self.bucket_name = 'test-bucket'
        self.key_name = 'test/file.txt'

    def test_init(self):
        """Test ProxiedBucketAdapter initialization."""
        adapter = ProxiedBucketAdapter(self.mock_client, self.bucket_name)

        assert adapter.client == self.mock_client
        assert adapter.name == self.bucket_name

    def test_get_key(self):
        """Test get_key method returns ProxiedKeyAdapter."""
        adapter = ProxiedBucketAdapter(self.mock_client, self.bucket_name)

        key_adapter = adapter.get_key(self.key_name)

        assert isinstance(key_adapter, ProxiedKeyAdapter)
        assert key_adapter.client == self.mock_client
        assert key_adapter.bucket == self.bucket_name
        assert key_adapter.name == self.key_name

    def test_get_key_with_kwargs(self):
        """Test get_key method with additional kwargs (ignored for compatibility)."""
        adapter = ProxiedBucketAdapter(self.mock_client, self.bucket_name)

        key_adapter = adapter.get_key(self.key_name, validate=True, timeout=30)

        assert isinstance(key_adapter, ProxiedKeyAdapter)
        assert key_adapter.client == self.mock_client
        assert key_adapter.bucket == self.bucket_name
        assert key_adapter.name == self.key_name


class TestProxiedKeyAdapter(Test):

    def setUp(self):
        super(TestProxiedKeyAdapter, self).setUp()
        self.mock_client = MagicMock()
        self.bucket_name = 'test-bucket'
        self.key_name = 'test/file.txt'
        self.endpoint_url = 'https://s3.test.com'

    def test_init(self):
        """Test ProxiedKeyAdapter initialization."""
        adapter = ProxiedKeyAdapter(self.mock_client, self.bucket_name, self.key_name)

        assert adapter.client == self.mock_client
        assert adapter.bucket == self.bucket_name
        assert adapter.name == self.key_name

    def test_generate_url_no_host_suffix(self):
        """Test generate_url method without host_suffix."""
        # Mock the client's endpoint_url
        self.mock_client.client.meta.endpoint_url = self.endpoint_url
        self.mock_client.host_suffix = ''

        adapter = ProxiedKeyAdapter(self.mock_client, self.bucket_name, self.key_name)

        url = adapter.generate_url()

        expected_url = f"{self.endpoint_url}/{self.bucket_name}/{self.key_name}"
        assert url == expected_url

    def test_generate_url_with_host_suffix(self):
        """Test generate_url method with host_suffix."""
        host_suffix = '/proxy'

        # Mock the client's endpoint_url and host_suffix
        self.mock_client.client.meta.endpoint_url = self.endpoint_url
        self.mock_client.host_suffix = host_suffix

        adapter = ProxiedKeyAdapter(self.mock_client, self.bucket_name, self.key_name)

        url = adapter.generate_url()

        expected_url = f"{self.endpoint_url}{host_suffix}/{self.bucket_name}/{self.key_name}"
        assert url == expected_url

    def test_generate_url_with_parameters(self):
        """Test generate_url method with parameters (currently ignored for compatibility)."""
        self.mock_client.client.meta.endpoint_url = self.endpoint_url
        self.mock_client.host_suffix = ''

        adapter = ProxiedKeyAdapter(self.mock_client, self.bucket_name, self.key_name)

        # Parameters are currently ignored but method should still work
        url = adapter.generate_url(expire=3600, query_auth=False)

        expected_url = f"{self.endpoint_url}/{self.bucket_name}/{self.key_name}"
        assert url == expected_url


class TestProxiedS3ClientIntegration(Test):
    """Integration tests for ProxiedS3Client with adapter classes."""

    def setUp(self):
        super(TestProxiedS3ClientIntegration, self).setUp()
        self.client_id = 'integration_client_id'
        self.client_secret = 'integration_client_secret'
        self.object_service = 'integration_service'
        self.bucket_name = 'integration-bucket'
        self.key_name = 'integration/file.txt'

    @patch('boto3.session.Session')
    def test_full_bucket_key_workflow(self, mock_session):
        """Test full workflow using bucket and key adapters."""
        mock_boto_client = MagicMock()
        mock_session.return_value.client.return_value = mock_boto_client
        mock_boto_client.meta.endpoint_url = 'https://s3.integration.com'

        # Create client
        client = ProxiedS3Client(
            client_id=self.client_id,
            client_secret=self.client_secret,
            object_service=self.object_service,
            host_suffix='/integration'
        )

        # Get bucket adapter
        bucket = client.get_bucket(self.bucket_name)
        assert isinstance(bucket, ProxiedBucketAdapter)
        assert bucket.name == self.bucket_name

        # Get key adapter
        key = bucket.get_key(self.key_name)
        assert isinstance(key, ProxiedKeyAdapter)
        assert key.name == self.key_name
        assert key.bucket == self.bucket_name

        # Generate URL
        url = key.generate_url()
        expected_url = f"https://s3.integration.com/integration/{self.bucket_name}/{self.key_name}"
        assert url == expected_url

    @patch('boto3.session.Session')
    def test_event_registration(self, mock_session):
        """Test that event hook is properly registered."""
        mock_boto_client = MagicMock()
        mock_session.return_value.client.return_value = mock_boto_client

        client = ProxiedS3Client(
            client_id=self.client_id,
            client_secret=self.client_secret,
            object_service=self.object_service
        )

        # Verify that register was called with the before-sign event
        mock_boto_client.meta.events.register.assert_called_once_with(
            "before-sign.s3", client._before_sign_hook
        )

    @patch('boto3.session.Session')
    @patch('time.time')
    def test_jwt_token_expiration(self, mock_time, mock_session):
        """Test JWT token has correct expiration time."""
        mock_client = MagicMock()
        mock_session.return_value.client.return_value = mock_client

        # Mock time to return a specific timestamp
        test_time = 1234567890
        mock_time.return_value = test_time

        client = ProxiedS3Client(
            client_id=self.client_id,
            client_secret=self.client_secret,
            object_service=self.object_service
        )

        token = client._create_jwt('GET', 'test.com', '/path')

        # Decode and check expiration
        decoded = jwt.decode(token, self.client_secret, algorithms=['HS256'])
        assert decoded['exp'] == test_time + 300  # 5 minutes
        assert decoded['iat'] == test_time
        assert decoded['nbf'] == test_time