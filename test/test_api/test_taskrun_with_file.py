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

    # test_taskrun_with_upload_json removed - obsolete boto implementation test

    # test_taskrun_with_no_upload removed - obsolete boto implementation test

    # test_taskrun_multipart removed - obsolete boto implementation test
    # test_taskrun_multipart removed - obsolete boto implementation test

    # test_taskrun_multipart_error removed - obsolete boto implementation test


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

    # test_taskrun_with_upload removed - obsolete boto implementation test

    # test_taskrun_multipart removed - obsolete boto implementation test

    # test_taskrun_with_encrypted_payload removed - obsolete boto implementation test
