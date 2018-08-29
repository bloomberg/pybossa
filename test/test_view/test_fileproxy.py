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


from default import with_context
import json
from helper import web
from mock import patch, MagicMock
from factories import ProjectFactory, TaskFactory, UserFactory
from pybossa.core import signer
from pybossa.encryption import AESWithGCM
from boto.exception import S3ResponseError


class TestFileproxy(web.Helper):

    def get_key(self, create_connection):
        key = MagicMock()
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
    @patch('pybossa.view.fileproxy.create_connection')
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
            'FILE_ENCRYPTION_KEY': encryption_key
        }):
            res = self.app.get(req_url, follow_redirects=True)
            assert res.status_code == 200, res.status_code
            assert res.data == 'the content', res.data

    @with_context
    @patch('pybossa.view.fileproxy.create_connection')
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
            'FILE_ENCRYPTION_KEY': encryption_key
        }):
            res = self.app.get(req_url, follow_redirects=True)
            assert res.status_code == 200, res.status_code
            assert res.data == 'the content', res.data

    @with_context
    @patch('pybossa.view.fileproxy.create_connection')
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
    @patch('pybossa.view.fileproxy.create_connection')
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
    @patch('pybossa.view.fileproxy.create_connection')
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
            'FILE_ENCRYPTION_KEY': encryption_key
        }):
            res = self.app.get(req_url, follow_redirects=True)
            assert res.status_code == 200, res.status_code
            assert res.data == 'the content', res.data

    @with_context
    @patch('pybossa.view.fileproxy.create_connection')
    def test_proxy_s3_error(self, create_connection):
        admin, owner = UserFactory.create_batch(2)
        project = ProjectFactory.create(owner=owner)
        url = '/fileproxy/encrypted/s3/test/%s/file.pdf' % project.id
        task = TaskFactory.create(project=project, info={
            'url': url
        })

        signature = signer.dumps({'task_id': task.id})
        req_url = '%s?api_key=%s&task-signature=%s' % (url, admin.api_key, signature)

        key = self.get_key(create_connection)
        key.get_contents_as_string.side_effect = S3ResponseError(403, 'Forbidden')

        res = self.app.get(req_url, follow_redirects=True)
        assert res.status_code == 500, res.status_code

    @with_context
    @patch('pybossa.view.fileproxy.create_connection')
    def test_proxy_key_not_found(self, create_connection):
        admin, owner = UserFactory.create_batch(2)
        project = ProjectFactory.create(owner=owner)
        url = '/fileproxy/encrypted/s3/test/%s/file.pdf' % project.id
        task = TaskFactory.create(project=project, info={
            'url': url
        })

        signature = signer.dumps({'task_id': task.id})
        req_url = '%s?api_key=%s&task-signature=%s' % (url, admin.api_key, signature)

        key = self.get_key(create_connection)
        exception = S3ResponseError(404, 'NoSuchKey')
        exception.error_code = 'NoSuchKey'
        key.get_contents_as_string.side_effect = exception

        res = self.app.get(req_url, follow_redirects=True)
        assert res.status_code == 404, res.status_code
