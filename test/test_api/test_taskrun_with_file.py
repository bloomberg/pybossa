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
from io import BytesIO
from test import with_context
from test.test_api import TestAPI
from unittest.mock import patch
from test.factories import ProjectFactory, TaskFactory
from pybossa.core import db
from pybossa.model.task_run import TaskRun
from pybossa.cloud_store_api.s3 import s3_upload_from_string, s3_upload_file
from pybossa.encryption import AESWithGCM


class TestTaskrunWithFile(TestAPI):

    host = 's3.storage.com'
    port = 443  # adding a port to be deterministic
    bucket = 'test_bucket'
    patch_config = {
        'S3_TASKRUN': {
            'host': host,
            'port': port,
            'auth_headers': [('a', 'b')]
        },
        'S3_BUCKET': 'test_bucket'
    }

    def setUp(self):
        super(TestTaskrunWithFile, self).setUp()
        db.session.query(TaskRun).delete()

    @with_context
    def test_taskrun_empty_info(self):
        with patch.dict(self.flask_app.config, self.patch_config):
            project = ProjectFactory.create()
            task = TaskFactory.create(project=project)
            self.app.get('/api/project/%s/newtask?api_key=%s' % (project.id, project.owner.api_key))

            data = dict(
                project_id=project.id,
                task_id=task.id,
                info=None
            )
            datajson = json.dumps(data)
            url = '/api/taskrun?api_key=%s' % project.owner.api_key

            success = self.app.post(url, data=datajson)
            assert success.status_code == 200, success.data

    @with_context
    @patch('pybossa.cloud_store_api.s3.create_connection')
    def test_taskrun_with_upload(self, mock_connection):
        with patch.dict(self.flask_app.config, self.patch_config):
            project = ProjectFactory.create()
            task = TaskFactory.create(project=project)
            
            # Set up mock connection for S3 operations
            from unittest.mock import MagicMock
            
            # Create a mock key that will have its name set dynamically
            mock_key = MagicMock()
            mock_key.set_contents_from_file = MagicMock()
            
            # Mock the generate_url to return the expected URL format
            def mock_generate_url(*args, **kwargs):
                # The URL should be: https://host:port/bucket/key_name
                return f'https://{self.host}:{self.port}/{self.bucket}/{mock_key.name}'
            mock_key.generate_url = mock_generate_url
            
            # Mock the bucket to set the key name when new_key is called
            mock_bucket = MagicMock()
            def mock_new_key(key_name):
                # Store the key name so generate_url can use it
                mock_key.name = key_name  
                return mock_key
            mock_bucket.new_key = mock_new_key
            
            # Mock the connection
            mock_conn = MagicMock()
            mock_conn.get_bucket.return_value = mock_bucket
            mock_connection.return_value = mock_conn

            self.app.get('/api/project/%s/newtask?api_key=%s' % (project.id, project.owner.api_key))

            data = dict(
                project_id=project.id,
                task_id=task.id,
                info={
                    'test__upload_url': {
                        'filename': 'hello.txt',
                        'content': 'abc'
                    }
                })
            datajson = json.dumps(data)
            url = '/api/taskrun?api_key=%s' % project.owner.api_key

            success = self.app.post(url, data=datajson)

            assert success.status_code == 200, success.data
            res = json.loads(success.data)
            url = res['info']['test__upload_url']
            args = {
                'host': self.host,
                'port': self.port,
                'bucket': self.bucket,
                'project_id': project.id,
                'task_id': task.id,
                'user_id': project.owner.id,
                'filename': 'hello.txt'
            }
            expected = 'https://{host}:{port}/{bucket}/{project_id}/{task_id}/{user_id}/{filename}'.format(**args)
            assert url == expected, url

    @with_context
    @patch('pybossa.cloud_store_api.s3.create_connection')
    def test_taskrun_with_no_upload(self, mock_connection):
        with patch.dict(self.flask_app.config, self.patch_config):
            project = ProjectFactory.create()
            task = TaskFactory.create(project=project)
            self.app.get('/api/project/%s/newtask?api_key=%s' % (project.id, project.owner.api_key))

            data = dict(
                project_id=project.id,
                task_id=task.id,
                info={
                    'test__upload_url': {
                        'test': 'not a file'
                    }
                })
            datajson = json.dumps(data)
            url = '/api/taskrun?api_key=%s' % project.owner.api_key

            success = self.app.post(url, data=datajson)

            assert success.status_code == 200, success.data
            res = json.loads(success.data)
            assert res['info']['test__upload_url']['test'] == 'not a file'

    @with_context
    @patch('pybossa.cloud_store_api.s3.create_connection')
    def test_taskrun_multipart(self, mock_connection):
        with patch.dict(self.flask_app.config, self.patch_config):
            # Set up mock connection for S3 operations
            from unittest.mock import MagicMock
            
            # Create a mock key that will have its name set dynamically
            mock_key = MagicMock()
            mock_key.set_contents_from_file = MagicMock()
            
            # Mock the generate_url to return the expected URL format
            def mock_generate_url(*args, **kwargs):
                return f'https://{self.host}:{self.port}/{self.bucket}/{mock_key.name}'
            mock_key.generate_url = mock_generate_url
            
            # Mock the bucket to set the key name when new_key is called
            mock_bucket = MagicMock()
            def mock_new_key(key_name):
                mock_key.name = key_name  
                return mock_key
            mock_bucket.new_key = mock_new_key
            
            mock_conn = MagicMock()
            mock_conn.get_bucket.return_value = mock_bucket
            mock_connection.return_value = mock_conn

            project = ProjectFactory.create()
            task = TaskFactory.create(project=project)
            self.app.get('/api/project/%s/newtask?api_key=%s' % (project.id, project.owner.api_key))
            data = dict(
                project_id=project.id,
                task_id=task.id,
                info={'field': 'value'}
            )
            datajson = json.dumps(data)

            # 'test__upload_url' requires bytes
            form = {
                'request_json': datajson,
                'test__upload_url': (BytesIO(b'Hi there'), 'hello.txt')
            }

            url = '/api/taskrun?api_key=%s' % project.owner.api_key
            success = self.app.post(url, content_type='multipart/form-data',
                                    data=form)

            assert success.status_code == 200, success.data
            res = json.loads(success.data)
            url = res['info']['test__upload_url']
            args = {
                'host': self.host,
                'port': self.port,
                'bucket': self.bucket,
                'project_id': project.id,
                'task_id': task.id,
                'user_id': project.owner.id,
                'filename': 'hello.txt'
            }
            expected = 'https://{host}:{port}/{bucket}/{project_id}/{task_id}/{user_id}/{filename}'.format(**args)
            assert url == expected, url

    @with_context
    @patch('pybossa.cloud_store_api.s3.create_connection')
    def test_taskrun_multipart_error(self, mock_connection):
        with patch.dict(self.flask_app.config, self.patch_config):
            project = ProjectFactory.create()
            task = TaskFactory.create(project=project)
            self.app.get('/api/project/%s/newtask?api_key=%s' % (project.id, project.owner.api_key))

            data = dict(
                project_id=project.id,
                task_id=task.id,
                info={'field': 'value'}
            )
            datajson = json.dumps(data)

            form = {
                'request_json': datajson,
                'test': (BytesIO(b'Hi there'), 'hello.txt')
            }

            url = '/api/taskrun?api_key=%s' % project.owner.api_key
            success = self.app.post(url, content_type='multipart/form-data',
                                    data=form)

            assert success.status_code == 400, success.data


class TestTaskrunWithSensitiveFile(TestAPI):

    host = 's3.storage.com'
    port = 443
    bucket = 'test_bucket'
    patch_config = {
        'S3_TASKRUN': {
            'host': host,
            'port': port,
            'auth_headers': [('a', 'b')]
        },
        'ENABLE_ENCRYPTION': True,
        'S3_BUCKET': 'test_bucket',
        'FILE_ENCRYPTION_KEY': 'testkey'
    }

    def setUp(self):
        super(TestTaskrunWithSensitiveFile, self).setUp()
        db.session.query(TaskRun).delete()

    @with_context
    @patch('pybossa.cloud_store_api.s3.create_connection')
    @patch('pybossa.cloud_store_api.s3.s3_upload_file', wraps=s3_upload_file)
    def test_taskrun_with_upload(self, s3_upload_file_mock, mock_connection):
        with patch.dict(self.flask_app.config, self.patch_config):
            project = ProjectFactory.create()
            task = TaskFactory.create(project=project)
            
            # Set up mock connection for S3 operations
            from unittest.mock import MagicMock
            
            # Create a mock key that will have its name set dynamically
            mock_key = MagicMock()
            mock_key.set_contents_from_file = MagicMock()
            
            # Mock the generate_url to return the expected URL format
            def mock_generate_url(*args, **kwargs):
                # The URL should be: https://host:port/bucket/key_name
                return f'https://{self.host}:{self.port}/{self.bucket}/{mock_key.name}'
            mock_key.generate_url = mock_generate_url
            
            # Mock the bucket to set the key name when new_key is called
            mock_bucket = MagicMock()
            def mock_new_key(key_name):
                # Store the key name so generate_url can use it
                mock_key.name = key_name  
                return mock_key
            mock_bucket.new_key = mock_new_key
            
            # Mock the connection
            mock_conn = MagicMock()
            mock_conn.get_bucket.return_value = mock_bucket
            mock_connection.return_value = mock_conn

            self.app.get('/api/project/%s/newtask?api_key=%s' % (project.id, project.owner.api_key))

            data = dict(
                project_id=project.id,
                task_id=task.id,
                info={
                    'test__upload_url': {
                        'filename': 'hello.txt',
                        'content': 'abc'
                    },
                    'another_field': 42
                })
            datajson = json.dumps(data)
            url = '/api/taskrun?api_key=%s' % project.owner.api_key

            success = self.app.post(url, data=datajson)

            assert success.status_code == 200, success.data
            res = json.loads(success.data)
            assert len(res['info']) == 1
            url = res['info']['pyb_answer_url']
            args = {
                'host': self.host,
                'port': self.port,
                'bucket': self.bucket,
                'project_id': project.id,
                'task_id': task.id,
                'user_id': project.owner.id,
                'filename': 'pyb_answer.json'
            }
            expected = 'https://{host}:{port}/{bucket}/{project_id}/{task_id}/{user_id}/{filename}'.format(**args)
            assert url == expected, url

            aes = AESWithGCM('testkey')
            # first call
            first_call = s3_upload_file_mock.call_args_list[0]
            args, kwargs = first_call
            # args[1] is the source_file (BytesIO) passed to s3_upload_file
            source_file = args[1]
            encrypted = source_file.read()
            source_file.seek(0)  # Reset file pointer for subsequent reads
            content = aes.decrypt(encrypted)
            assert encrypted != content
            assert content == 'abc'

            s3_upload_file_mock.assert_called()
            args, kwargs = s3_upload_file_mock.call_args
            # args[1] is the source_file (BytesIO) passed to s3_upload_file
            source_file = args[1]
            encrypted_content = source_file.read()
            source_file.seek(0)  # Reset file pointer
            content = aes.decrypt(encrypted_content)
            actual_content = json.loads(content)

            args = {
                'host': self.host,
                'port': self.port,
                'bucket': self.bucket,
                'project_id': project.id,
                'task_id': task.id,
                'user_id': project.owner.id,
                'filename': 'hello.txt'
            }
            expected = 'https://{host}:{port}/{bucket}/{project_id}/{task_id}/{user_id}/{filename}'.format(**args)
            assert actual_content['test__upload_url'] == expected
            assert actual_content['another_field'] == 42

    @with_context
    @patch('pybossa.cloud_store_api.s3.create_connection')
    def test_taskrun_multipart(self, mock_connection):
        with patch.dict(self.flask_app.config, self.patch_config):
            # Set up mock connection for S3 operations
            from unittest.mock import MagicMock
            
            # Create a mock key that will have its name set dynamically
            mock_key = MagicMock()
            mock_key.set_contents_from_file = MagicMock()
            
            # Mock the generate_url to return the expected URL format
            def mock_generate_url(*args, **kwargs):
                return f'https://{self.host}:{self.port}/{self.bucket}/{mock_key.name}'
            mock_key.generate_url = mock_generate_url
            
            # Mock the bucket to set the key name when new_key is called
            mock_bucket = MagicMock()
            def mock_new_key(key_name):
                mock_key.name = key_name  
                return mock_key
            mock_bucket.new_key = mock_new_key
            
            mock_conn = MagicMock()
            mock_conn.get_bucket.return_value = mock_bucket
            mock_connection.return_value = mock_conn

            project = ProjectFactory.create()
            task = TaskFactory.create(project=project)
            self.app.get('/api/project/%s/newtask?api_key=%s' % (project.id, project.owner.api_key))

            data = dict(
                project_id=project.id,
                task_id=task.id,
                info={'field': 'value'}
            )
            datajson = json.dumps(data)

            form = {
                'request_json': datajson,
                'test__upload_url': (BytesIO(b'Hi there'), 'hello.txt')
            }

            url = '/api/taskrun?api_key=%s' % project.owner.api_key
            success = self.app.post(url, content_type='multipart/form-data',
                                    data=form)

            assert success.status_code == 200, success.data
            res = json.loads(success.data)
            url = res['info']['pyb_answer_url']
            args = {
                'host': self.host,
                'port': self.port,
                'bucket': self.bucket,
                'project_id': project.id,
                'task_id': task.id,
                'user_id': project.owner.id,
                'filename': 'pyb_answer.json'
            }
            expected = 'https://{host}:{port}/{bucket}/{project_id}/{task_id}/{user_id}/{filename}'.format(**args)
            assert url == expected, url

    @with_context
    @patch('pybossa.cloud_store_api.s3.create_connection')
    @patch('pybossa.cloud_store_api.s3.s3_upload_file', wraps=s3_upload_file)
    @patch('pybossa.view.fileproxy.get_encryption_key')
    def test_taskrun_with_encrypted_payload(self, encr_key, s3_upload_file_mock, mock_connection):
        with patch.dict(self.flask_app.config, self.patch_config):
            # Set up mock connection for S3 operations
            from unittest.mock import MagicMock
            
            # Create a mock key that will have its name set dynamically
            mock_key = MagicMock()
            mock_key.set_contents_from_file = MagicMock()
            
            # Mock the generate_url to return the expected URL format
            def mock_generate_url(*args, **kwargs):
                return f'https://{self.host}:{self.port}/{self.bucket}/{mock_key.name}'
            mock_key.generate_url = mock_generate_url
            
            # Mock the bucket to set the key name when new_key is called
            mock_bucket = MagicMock()
            def mock_new_key(key_name):
                mock_key.name = key_name  
                return mock_key
            mock_bucket.new_key = mock_new_key
            
            mock_conn = MagicMock()
            mock_conn.get_bucket.return_value = mock_bucket
            mock_connection.return_value = mock_conn

            project = ProjectFactory.create()
            encryption_key = 'testkey'
            encr_key.return_value = encryption_key
            aes = AESWithGCM(encryption_key)
            content = 'some data'
            encrypted_content = aes.encrypt(content)
            task = TaskFactory.create(project=project, info={
                'private_json__encrypted_payload': encrypted_content
            })
            self.app.get('/api/project/%s/newtask?api_key=%s' % (project.id, project.owner.api_key))

            taskrun_data = {
                'another_field': 42
            }
            data = dict(
                project_id=project.id,
                task_id=task.id,
                info=taskrun_data)
            datajson = json.dumps(data)
            url = '/api/taskrun?api_key=%s' % project.owner.api_key

            success = self.app.post(url, data=datajson)

            assert success.status_code == 200, success.data
            res = json.loads(success.data)
            assert len(res['info']) == 2
            encrypted_response = res['info']['private_json__encrypted_response']
            decrypted_content = aes.decrypt(encrypted_response)
            assert decrypted_content == json.dumps(taskrun_data), "private_json__encrypted_response decrypted data mismatch"
            url = res['info']['pyb_answer_url']
            args = {
                'host': self.host,
                'port': self.port,
                'bucket': self.bucket,
                'project_id': project.id,
                'task_id': task.id,
                'user_id': project.owner.id,
                'filename': 'pyb_answer.json'
            }
            expected = 'https://{host}:{port}/{bucket}/{project_id}/{task_id}/{user_id}/{filename}'.format(**args)
            assert url == expected, url
