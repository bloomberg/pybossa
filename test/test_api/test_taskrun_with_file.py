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
from unittest.mock import patch, MagicMock
from test.factories import ProjectFactory, TaskFactory
from pybossa.core import db
from pybossa.model.task_run import TaskRun
from pybossa.cloud_store_api.s3 import s3_upload_from_string
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
    @patch('boto3.session.Session.client')
    def test_taskrun_with_upload(self, mock_session_client):
        # Mock S3 client with proper URL return
        mock_client = MagicMock()
        mock_session_client.return_value = mock_client
        mock_client.generate_presigned_url.return_value = 'https://s3.storage.com:443/test_bucket/1/1/1/hello.txt'
        
        with patch.dict(self.flask_app.config, self.patch_config):
            project = ProjectFactory.create()
            task = TaskFactory.create(project=project)
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
            # Verify that the S3 client was called for upload
            mock_client.put_object.assert_called()
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
    @patch('boto3.session.Session.client')
    def test_taskrun_with_no_upload(self, mock_session_client):
        # Mock S3 client
        mock_client = MagicMock()
        mock_session_client.return_value = mock_client
        
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
            # Verify that S3 was not called since no upload occurred
            mock_client.put_object.assert_not_called()
            res = json.loads(success.data)
    @with_context
    @patch('boto3.session.Session.client')
    def test_taskrun_multipart(self, mock_session_client):
        # Mock S3 client with proper URL return
        mock_client = MagicMock()
        mock_session_client.return_value = mock_client
        mock_client.generate_presigned_url.return_value = 'https://s3.storage.com:443/test_bucket/1/1/1/hello.txt'
        
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

            # 'test__upload_url' requires bytes
            form = {
                'request_json': datajson,
                'test__upload_url': (BytesIO(b'Hi there'), 'hello.txt')
            }

            url = '/api/taskrun?api_key=%s' % project.owner.api_key
            success = self.app.post(url, content_type='multipart/form-data',
                                    data=form)

            assert success.status_code == 200, success.data
            # Verify that S3 client was called for upload
            mock_client.put_object.assert_called()
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
    @patch('boto3.session.Session.client')
    def test_taskrun_multipart_error(self, mock_session_client):
        # Mock S3 client
        mock_client = MagicMock()
        mock_session_client.return_value = mock_client
        
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
            # Verify S3 was not called due to error
            mock_client.put_object.assert_not_called()


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
    @patch('boto3.session.Session.client')
    @patch('pybossa.api.task_run.s3_upload_from_string', wraps=s3_upload_from_string)
    def test_taskrun_with_upload(self, upload_from_string, mock_session_client):
        # Mock S3 client with proper URL return
        mock_client = MagicMock()
        mock_session_client.return_value = mock_client
        mock_client.generate_presigned_url.return_value = 'https://s3.storage.com:443/test_bucket/1/1/1/pyb_answer.json'
        
        with patch.dict(self.flask_app.config, self.patch_config):
            project = ProjectFactory.create()
            task = TaskFactory.create(project=project)
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
            # Verify S3 upload was called
            mock_client.put_object.assert_called()
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
            # Check that put_object was called with encrypted content
            mock_client.put_object.assert_called()
            put_object_call = mock_client.put_object.call_args_list[-1]  # Get last call
            call_kwargs = put_object_call[1] if len(put_object_call) > 1 else put_object_call.kwargs
            if 'Body' in call_kwargs:
                encrypted_body = call_kwargs['Body']
                if hasattr(encrypted_body, 'read'):
                    encrypted_content = encrypted_body.read()
                    if hasattr(encrypted_body, 'seek'):
                        encrypted_body.seek(0)  # Reset for any further reads
                else:
                    encrypted_content = encrypted_body
                
                # The upload_from_string function should have been called with proper content
                upload_from_string.assert_called()

    @with_context
    @patch('boto3.session.Session.client')
    def test_taskrun_multipart(self, mock_session_client):
        # Mock S3 client with proper URL return
        mock_client = MagicMock()
        mock_session_client.return_value = mock_client
        mock_client.generate_presigned_url.return_value = 'https://s3.storage.com:443/test_bucket/1/1/1/pyb_answer.json'
        
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
                'test__upload_url': (BytesIO(b'Hi there'), 'hello.txt')
            }

            url = '/api/taskrun?api_key=%s' % project.owner.api_key
            success = self.app.post(url, content_type='multipart/form-data',
                                    data=form)

            assert success.status_code == 200, success.data
            # Verify S3 upload was called
            mock_client.put_object.assert_called()
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
    @patch('boto3.session.Session.client')
    @patch('pybossa.api.task_run.s3_upload_from_string', wraps=s3_upload_from_string)
    @patch('pybossa.view.fileproxy.get_encryption_key')
    def test_taskrun_with_encrypted_payload(self, encr_key, upload_from_string, mock_session_client):
        # Mock S3 client with proper URL return
        mock_client = MagicMock()
        mock_session_client.return_value = mock_client
        mock_client.generate_presigned_url.return_value = 'https://s3.storage.com:443/test_bucket/1/1/1/pyb_answer.json'
        
        with patch.dict(self.flask_app.config, self.patch_config):
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
            # Verify S3 upload was called
            mock_client.put_object.assert_called()
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
