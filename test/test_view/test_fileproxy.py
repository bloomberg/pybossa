# -*- coding: utf8 -*-
# This file is part of PYBOSSA.
#
# Copyright (C) 2015 Scifabric LTD.
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


import os
from test import with_context
from nose.tools import assert_raises
import json
from test.helper import web
from unittest.mock import patch, MagicMock
from test.factories import ProjectFactory, TaskFactory, UserFactory
from pybossa.core import signer
from pybossa.encryption import AESWithGCM
from pybossa.task_creator_helper import get_path, get_secret_from_env


class TestFileproxy(web.Helper):

    def get_key(self, create_connection):
        key = MagicMock()
        key.content_disposition = "inline"
        bucket = MagicMock()
        bucket.get_key.return_value = key
        conn = MagicMock()
        conn.get_bucket.return_value = bucket
        create_connection.return_value = conn
        return key

    @with_context
    def test_proxy_no_signature(self):
        project = ProjectFactory.create()
        owner = project.owner

        url = '/fileproxy/encrypted/s3/test/%s/file.pdf?api_key=%s' \
             % (project.id, owner.api_key)
        res = self.app.get(url, follow_redirects=True)
        assert res.status_code == 403, res.status_code

        url = '/fileproxy/encrypted/s3/test/workflow_request/abcd/%s/file.pdf?api_key=%s' \
             % (project.id, owner.api_key)
        res = self.app.get(url, follow_redirects=True)
        assert res.status_code == 403, res.status_code

    @with_context
    def test_proxy_invalid_signature(self):
        """invalid signature beyond max length (128)"""
        import string
        import random

        project = ProjectFactory.create()
        owner = project.owner

        task_id = 2020127
        signature = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(129))
        url = '/fileproxy/encrypted/s3/test/%s/file.pdf?api_key=%s&task-signature=%s' \
            % (project.id, owner.api_key, signature)
        res = self.app.get(url, follow_redirects=True)
        assert res.status == '403 FORBIDDEN', res.status_code

    @with_context
    def test_proxy_no_task(self):
        project = ProjectFactory.create()
        owner = project.owner

        signature = signer.dumps({'task_id': 100})

        url = '/fileproxy/encrypted/s3/test/%s/file.pdf?api_key=%s&task-signature=%s' \
            % (project.id, owner.api_key, signature)
        res = self.app.get(url, follow_redirects=True)
        assert res.status_code == 400, res.status_code

    @with_context
    @patch('pybossa.cloud_store_api.s3.create_connection')
    def test_proxy_owner(self, create_connection):
        project = ProjectFactory.create()
        url = '/fileproxy/encrypted/s3/test/%s/file.pdf' % project.id
        task = TaskFactory.create(project=project, info={
            'url': url
        })
        owner = project.owner

        signature = signer.dumps({'task_id': task.id})
        req_url = '%s?api_key=%s&task-signature=%s' % (url, owner.api_key, signature)

        encryption_key = 'testkey'
        aes = AESWithGCM(encryption_key)
        key = self.get_key(create_connection)
        key.get_contents_as_string.return_value = aes.encrypt('the content')

        with patch.dict(self.flask_app.config, {
            'FILE_ENCRYPTION_KEY': encryption_key,
            'S3_REQUEST_BUCKET': 'test'
        }):
            res = self.app.get(req_url, follow_redirects=True)
            assert res.status_code == 200, res.status_code
            assert res.data == b'the content', res.data

    @with_context
    @patch('pybossa.cloud_store_api.s3.create_connection')
    def test_proxy_admin(self, create_connection):
        admin, owner = UserFactory.create_batch(2)
        project = ProjectFactory.create(owner=owner)
        url = '/fileproxy/encrypted/s3/test/%s/file.pdf' % project.id
        task = TaskFactory.create(project=project, info={
            'url': url
        })

        signature = signer.dumps({'task_id': task.id})
        req_url = '%s?api_key=%s&task-signature=%s' % (url, admin.api_key, signature)

        encryption_key = 'testkey'
        aes = AESWithGCM(encryption_key)
        key = self.get_key(create_connection)
        key.get_contents_as_string.return_value = aes.encrypt('the content')

        with patch.dict(self.flask_app.config, {
            'FILE_ENCRYPTION_KEY': encryption_key,
            'S3_REQUEST_BUCKET': 'test'
        }):
            res = self.app.get(req_url, follow_redirects=True)
            assert res.status_code == 200, res.status_code
            assert res.data == b'the content', res.data

    @with_context
    @patch('pybossa.cloud_store_api.s3.create_connection')
    def test_file_not_in_task(self, create_connection):
        project = ProjectFactory.create()
        url = '/fileproxy/encrypted/s3/test/%s/file.pdf' % project.id
        task = TaskFactory.create(project=project, info={
            'url': 'not/the/same'
        })
        owner = project.owner

        signature = signer.dumps({'task_id': task.id})
        req_url = '%s?api_key=%s&task-signature=%s' % (url, owner.api_key, signature)

        res = self.app.get(req_url, follow_redirects=True)
        assert res.status_code == 403, res.status_code

    @with_context
    @patch('pybossa.cloud_store_api.s3.create_connection')
    def test_file_user(self, create_connection):
        admin, owner, user = UserFactory.create_batch(3)
        project = ProjectFactory.create()
        url = '/fileproxy/encrypted/s3/test/%s/file.pdf' % project.id
        task = TaskFactory.create(project=project, info={
            'url': url
        })

        signature = signer.dumps({'task_id': task.id})
        req_url = '%s?api_key=%s&task-signature=%s' % (url, user.api_key, signature)

        res = self.app.get(req_url, follow_redirects=True)
        assert res.status_code == 403, res.status_code

    @with_context
    def test_proxy_no_project(self):
        project = ProjectFactory.create()
        owner = project.owner
        task = TaskFactory.create(project=project)
        signature = signer.dumps({'task_id': task.id})
        invalid_project_id = 99999

        url = '/fileproxy/encrypted/s3/test/%s/file.pdf?api_key=%s&task-signature=%s' \
            % (invalid_project_id, owner.api_key, signature)
        res = self.app.get(url, follow_redirects=True)
        assert res.status_code == 400, res.status_code

    @with_context
    @patch('pybossa.cloud_store_api.s3.create_connection')
    @patch('pybossa.view.fileproxy.has_lock')
    def test_file_user(self, has_lock, create_connection):
        has_lock.return_value = True
        admin, owner, user = UserFactory.create_batch(3)
        project = ProjectFactory.create()
        url = '/fileproxy/encrypted/s3/test/%s/file.pdf' % project.id
        task = TaskFactory.create(project=project, info={
            'url': url
        })

        signature = signer.dumps({'task_id': task.id})
        req_url = '%s?api_key=%s&task-signature=%s' % (url, user.api_key, signature)

        encryption_key = 'testkey'
        aes = AESWithGCM(encryption_key)
        key = self.get_key(create_connection)
        key.get_contents_as_string.return_value = aes.encrypt('the content')

        with patch.dict(self.flask_app.config, {
            'FILE_ENCRYPTION_KEY': encryption_key,
            'S3_REQUEST_BUCKET': 'test'
        }):
            res = self.app.get(req_url, follow_redirects=True)
            assert res.status_code == 200, res.status_code
            assert res.data == b'the content', res.data

    @with_context
    @patch('pybossa.cloud_store_api.s3.create_connection')
    @patch('pybossa.view.fileproxy.has_lock')
    @patch('pybossa.task_creator_helper.get_secret_from_env')
    def test_file_user_key_from_env(self, get_secret, has_lock, create_connection):
        has_lock.return_value = True
        admin, owner, user = UserFactory.create_batch(3)
        project = ProjectFactory.create(info={
            'encryption': {
                'key': 'abc'
            }
        })
        url = '/fileproxy/encrypted/s3/anothertest/%s/file.pdf' % project.id
        task = TaskFactory.create(project=project, info={
            'url': url
        })

        signature = signer.dumps({'task_id': task.id})
        req_url = '%s?api_key=%s&task-signature=%s' % (url, user.api_key, signature)

        encryption_key = 'testkey'
        aes = AESWithGCM(encryption_key)
        key = self.get_key(create_connection)
        key.get_contents_as_string.return_value = aes.encrypt('the content')
        get_secret.return_value = encryption_key

        with patch.dict(self.flask_app.config, {
            'FILE_ENCRYPTION_KEY': 'another key',
            'S3_REQUEST_BUCKET': 'test',
            'ENCRYPTION_CONFIG_PATH': ['encryption'],
            'SECRET_CONFIG_ENV': {"secret_id_prefix": "key_id"},
        }):
            res = self.app.get(req_url, follow_redirects=True)
            assert res.status_code == 200, res.status_code
            assert res.data == b'the content', res.data


class TestEncryptedPayload(web.Helper):

    app_config = {
        'SECRET_CONFIG_ENV': {"secret_id_prefix": "key_id"},
        'ENCRYPTION_CONFIG_PATH': ['ext_config', 'encryption']
    }

    @with_context
    def test_proxy_no_signature(self):
        project = ProjectFactory.create()
        owner = project.owner

        task_id = 2020127
        url = '/fileproxy/encrypted/taskpayload/%s/%s?api_key=%s' \
             % (project.id, task_id, owner.api_key)
        res = self.app.get(url, follow_redirects=True)
        assert res.status_code == 403, res.status_code

    @with_context
    def test_proxy_invalid_signature(self):
        """invalid signature beyond max length (128)"""
        import string
        import random

        project = ProjectFactory.create()
        owner = project.owner

        task_id = 2020127
        signature = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(129))
        url = '/fileproxy/encrypted/taskpayload/%s/%s?api_key=%s&task-signature=%s' \
             % (project.id, task_id, owner.api_key, signature)
        res = self.app.get(url, follow_redirects=True)
        assert res.status == '403 FORBIDDEN', res.status_code

    @with_context
    def test_proxy_no_task(self):
        project = ProjectFactory.create()
        owner = project.owner

        task_id = 2020127
        signature = signer.dumps({'task_id': task_id})

        url = '/fileproxy/encrypted/taskpayload/%s/%s?api_key=%s&task-signature=%s' \
            % (project.id, task_id, owner.api_key, signature)
        with patch.dict(self.flask_app.config, self.app_config):
            res = self.app.get(url, follow_redirects=True)
            assert res.status_code == 400, res.status_code

    @with_context
    @patch('pybossa.view.fileproxy.requests.get')
    def test_proxy_owner(self, http_get):
        res = MagicMock()
        res.json.return_value = {'key': 'testkey'}
        http_get.return_value = res

        project = ProjectFactory.create(info={
            'ext_config': {
                'encryption': {'key_id': 123}
            }
        })

        encryption_key = 'testkey'
        aes = AESWithGCM(encryption_key)
        content = json.dumps(dict(a=1,b="2"))
        encrypted_content = aes.encrypt(content)
        task = TaskFactory.create(project=project, info={
            'private_json__encrypted_payload': encrypted_content
        })
        owner = project.owner

        signature = signer.dumps({'task_id': task.id})
        url = '/fileproxy/encrypted/taskpayload/%s/%s?api_key=%s&task-signature=%s' \
            % (project.id, task.id, owner.api_key, signature)

        with patch.dict(self.flask_app.config, self.app_config):
            os.environ['key_id_123'] = encryption_key
            res = self.app.get(url, follow_redirects=True)
            assert res.status_code == 200, res.status_code
            assert res.data == content.encode(), res.data

    @with_context
    @patch('pybossa.view.fileproxy.requests.get')
    def test_proxy_admin(self, http_get):
        res = MagicMock()
        res.json.return_value = {'key': 'testkey'}
        http_get.return_value = res

        admin, owner = UserFactory.create_batch(2)
        project = ProjectFactory.create(owner=owner, info={
            'ext_config': {
                'encryption': {'key_id': 123}
            }
        })

        encryption_key = 'testkey'
        aes = AESWithGCM(encryption_key)
        content = json.dumps(dict(a=1,b="2"))
        encrypted_content = aes.encrypt(content)
        task = TaskFactory.create(project=project, info={
            'private_json__encrypted_payload': encrypted_content
        })

        signature = signer.dumps({'task_id': task.id})
        url = '/fileproxy/encrypted/taskpayload/%s/%s?api_key=%s&task-signature=%s' \
            % (project.id, task.id, admin.api_key, signature)

        with patch.dict(self.flask_app.config, self.app_config):
            os.environ['key_id_123'] = encryption_key
            res = self.app.get(url, follow_redirects=True)
            assert res.status_code == 200, res.status_code
            assert res.data == content.encode(), res.data

    @with_context
    def test_empty_response(self):
        """Returns empty response with task payload not containing encrypted data."""

        project = ProjectFactory.create(info={
            'ext_config': {
                'encryption': {'key_id': 123}
            }
        })
        encryption_key = 'testkey'
        task = TaskFactory.create(project=project, info={}) # missing private_json__encrypted_payload
        owner = project.owner

        signature = signer.dumps({'task_id': task.id})
        url = '/fileproxy/encrypted/taskpayload/%s/%s?api_key=%s&task-signature=%s' \
            % (project.id, task.id, owner.api_key, signature)

        with patch.dict(self.flask_app.config, self.app_config):
            os.environ['key_id_123'] = encryption_key
            res = self.app.get(url, follow_redirects=True)
            assert res.status_code == 200, res.status_code
            assert res.data == b'', res.data

    @with_context
    @patch('pybossa.task_creator_helper.get_secret_from_env')
    def test_proxy_key_err(self, get_secret):
        """
        Test error cases for encrypted payload proxy:
        1. Simulate an error when retrieving the encryption key (should return 500).
        2. Simulate a bad project id (should return 400).
        """

        admin, owner = UserFactory.create_batch(2)
        project = ProjectFactory.create(owner=owner, info={
            'ext_config': {
                'encryption': {'key_id': 123}
            }
        })
        encryption_key = 'testkey'
        aes = AESWithGCM(encryption_key)
        content = json.dumps(dict(a=1,b="2"))
        encrypted_content = aes.encrypt(content)
        task = TaskFactory.create(project=project, info={
            'private_json__encrypted_payload': encrypted_content
        })

        signature = signer.dumps({'task_id': task.id})
        url = '/fileproxy/encrypted/taskpayload/%s/%s?api_key=%s&task-signature=%s' \
            % (project.id, task.id, admin.api_key, signature)

        # Patch get_secret to raise an Exception to simulate key retrieval error
        get_secret.side_effect = Exception("Key retrieval failed")

        with patch.dict(self.flask_app.config, self.app_config):
            res = self.app.get(url, follow_redirects=True)
            assert res.status_code == 500, res.status_code

        bad_project_id = 9999
        url = '/fileproxy/encrypted/taskpayload/%s/%s?api_key=%s&task-signature=%s' \
            % (bad_project_id, task.id, admin.api_key, signature)

        with patch.dict(self.flask_app.config, self.app_config):
            res = self.app.get(url, follow_redirects=True)
            assert res.status_code == 400, res.status_code


    @with_context
    @patch('pybossa.view.fileproxy.requests.get')
    def test_proxy_regular_user_has_lock(self, http_get):
        res = MagicMock()
        res.json.return_value = {'key': 'testkey'}
        http_get.return_value = res

        admin, owner, user = UserFactory.create_batch(3)
        project = ProjectFactory.create(owner=owner, info={
            'ext_config': {
                'encryption': {'key_id': 123}
            }
        })

        encryption_key = 'testkey'
        aes = AESWithGCM(encryption_key)
        content = json.dumps(dict(a=1,b="2"))
        encrypted_content = aes.encrypt(content)
        task = TaskFactory.create(project=project, info={
            'private_json__encrypted_payload': encrypted_content
        })

        signature = signer.dumps({'task_id': task.id})
        url = '/fileproxy/encrypted/taskpayload/%s/%s?api_key=%s&task-signature=%s' \
            % (project.id, task.id, user.api_key, signature)

        with patch('pybossa.view.fileproxy.has_lock') as has_lock:
            has_lock.return_value = True
            with patch.dict(self.flask_app.config, self.app_config):
                os.environ['key_id_123'] = encryption_key
                res = self.app.get(url, follow_redirects=True)
                assert res.status_code == 200, res.status_code
                assert res.data == content.encode(), res.data

        with patch('pybossa.view.fileproxy.has_lock') as has_lock:
            has_lock.return_value = False
            with patch.dict(self.flask_app.config, self.app_config):
                res = self.app.get(url, follow_redirects=True)
                assert res.status_code == 403, res.status_code

        # coowner can access the task
        project.owners_ids.append(user.id)
        with patch('pybossa.view.fileproxy.has_lock') as has_lock:
            has_lock.return_value = False
            with patch.dict(self.flask_app.config, self.app_config):
                res = self.app.get(url, follow_redirects=True)
                assert res.status_code == 200, res.status_code

    @with_context
    def test_proj_encr_key_from_env(self):
        """Test project encryption key can be retrieved from env."""
        admin, owner, user = UserFactory.create_batch(3)

        # project with encryption key in ext_config
        # and key_id in env variable
        project = ProjectFactory.create(owner=owner, info={
            'ext_config': {
                'encryption': {'key_id': 123}
            }
        })

        encryption_key = 'testkey'
        aes = AESWithGCM(encryption_key)
        content = json.dumps(dict(a=1,b="2"))
        encrypted_content = aes.encrypt(content)
        task = TaskFactory.create(project=project, info={
            'private_json__encrypted_payload': encrypted_content
        })

        signature = signer.dumps({'task_id': task.id})
        url = '/fileproxy/encrypted/taskpayload/%s/%s?api_key=%s&task-signature=%s' \
            % (project.id, task.id, user.api_key, signature)

        app_config = {
            'SECRET_CONFIG_ENV': {"secret_id_prefix": "key_id"},
            'ENCRYPTION_CONFIG_PATH': ['ext_config', 'encryption']
        }

        with patch('pybossa.view.fileproxy.has_lock') as has_lock:
            os.environ['key_id_123'] = encryption_key
            has_lock.return_value = True
            with patch.dict(self.flask_app.config, app_config):
                res = self.app.get(url, follow_redirects=True)
                assert res.status_code == 200, res.status_code
                assert res.data == content.encode(), res.data

        # project without encryption key in ext_config doesn't require encrypt/decrypt
        content = dict(a=1, b="2")
        project = ProjectFactory.create(owner=owner, info={})
        task = TaskFactory.create(project=project, info=content)
        signature = signer.dumps({'task_id': task.id})
        url = '/fileproxy/encrypted/taskpayload/%s/%s?api_key=%s&task-signature=%s' \
            % (project.id, task.id, user.api_key, signature)
        with patch('pybossa.view.fileproxy.has_lock') as has_lock:
            has_lock.return_value = True
            with patch.dict(self.flask_app.config, app_config):
                res = self.app.get(url, follow_redirects=True)
                assert res.status_code == 200, res.status_code

    @with_context
    def test_missing_config_SECRET_CONFIG_ENV_raises_exception(self):
        """Test that missing SECRET_CONFIG_ENV raises an exception."""
        admin, owner, user = UserFactory.create_batch(3)

        project = ProjectFactory.create(owner=owner, info={
            'ext_config': {
                'encryption': {'key_id': 123}
            }
        })

        encryption_key = 'testkey'
        aes = AESWithGCM(encryption_key)
        content = json.dumps(dict(a=1,b="2"))
        encrypted_content = aes.encrypt(content)
        task = TaskFactory.create(project=project, info={
            'private_json__encrypted_payload': encrypted_content
        })

        signature = signer.dumps({'task_id': task.id})
        url = '/fileproxy/encrypted/taskpayload/%s/%s?api_key=%s&task-signature=%s' \
            % (project.id, task.id, owner.api_key, signature)

        app_config = {
            'ENCRYPTION_CONFIG_PATH': ['ext_config', 'encryption']
        }

        with patch.dict(self.flask_app.config, app_config):
            resp = self.app.get(url, follow_redirects=True)
            assert resp.status == '500 INTERNAL SERVER ERROR', resp.status_code
            assert 'SECRET_CONFIG_ENV' not in self.flask_app.config

    def test_empty_path_returns_dict(self):
        d = {'a': 1}
        assert get_path(d, []) ==  d

    def test_single_level_path(self):
        d = {'a': 1, 'b': 2}
        assert get_path(d, ['a']) == 1
        assert get_path(d, ['b']) == 2

    def test_multi_level_path(self):
        d = {'a': {'b': {'c': 42}}}
        assert get_path(d, ['a', 'b', 'c']) == 42

    def test_path_not_found_raises(self):
        d = {'a': {'b': 2}}
        with assert_raises(KeyError):
            get_path(d, ['a', 'c'])

    def test_non_dict_in_path_raises(self):
        d = {'a': 1}
        with assert_raises(TypeError):
            get_path(d, ['a', 'b'])

    @with_context
    def test_get_secret_from_env_success(self):
        app_config = {
            'SECRET_CONFIG_ENV': {'secret_id_prefix': 'key_id'}
        }
        with patch.dict(self.flask_app.config, app_config):
            project_encryption = {'key_id': '123'}
            env_key = 'key_id_123'
            os.environ[env_key] = 'supersecret'
            assert get_secret_from_env(project_encryption) == 'supersecret'
            del os.environ[env_key]

    @with_context
    def test_get_secret_from_env_invalid_config_type(self):
        app_config = {
            'SECRET_CONFIG_ENV': 'not_a_dict'
        }
        with patch.dict(self.flask_app.config, app_config):
            project_encryption = {'key_id': '123'}
            with assert_raises(RuntimeError):
                get_secret_from_env(project_encryption)

    @with_context
    def test_get_secret_from_env_missing_secret_id_prefix(self):
        app_config = {
            'SECRET_CONFIG_ENV': {}
        }
        with patch.dict(self.flask_app.config, app_config):
            project_encryption = {'key_id': '123'}
            with assert_raises(RuntimeError):
                get_secret_from_env(project_encryption)

    @with_context
    def test_get_secret_from_env_env_key_missing(self):
        app_config = {
            'SECRET_CONFIG_ENV': {'secret_id_prefix': 'key_id'}
        }
        with patch.dict(self.flask_app.config, app_config):
            project_encryption = {'key_id': 'not_in_env'}
            env_key = 'key_id_not_in_env'
            if env_key in os.environ:
                del os.environ[env_key]
            with assert_raises(RuntimeError):
                get_secret_from_env(project_encryption)
