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
import json
from unittest.mock import patch, call

from nose.tools import assert_equal

from pybossa.model.project import Project
from test import db, with_context
from test.factories import (ProjectFactory, UserFactory)
from test.test_api import TestAPI



class TestProjectAPI(TestAPI):

    def setUp(self):
        super(TestProjectAPI, self).setUp()
        db.session.query(Project).delete()

    def setupProjects(self):
        project = ProjectFactory.create(
            updated='2015-01-01T14:37:30.642119',
            short_name='test-app1',
            info={
                'total': 150,
                'task_presenter': 'foo',
                'data_classification': dict(input_data="L4 - public", output_data="L4 - public"),
                'product' : 'test_product',
                'subproduct': 'test_subproduct1'
        })

        projects = ProjectFactory.create_batch(5,
            info={
                'total': 150,
                'task_presenter': 'foo',
                'data_classification': dict(input_data="L4 - public", output_data="L4 - public"),
                'product' : 'test_product',
                'subproduct': 'test_subproduct2'
        })
        return project

    @with_context
    def test_project_locks_user_not_logged_in(self):
        """ Test should return 401 if the user is not logged in"""
        project = self.setupProjects()
        project_id = str(project.id)

        res = self.app.get('/api/locks/' + project_id)
        err = json.loads(res.data)
        assert res.status_code == 401, err
        assert err['status'] == 'failed', err
        assert err['target'] == 'project', err
        assert err['exception_cls'] == 'Unauthorized', err
        assert err['action'] == 'GET', err

    @with_context
    def test_project_locks_user_worker(self):
        """ Test API should return 401 if user is worker"""
        admin = UserFactory.create(admin=True)
        worker = UserFactory.create(admin=False, subadmin=False)

        project = self.setupProjects()
        project_id = str(project.id)

        res = self.app.get('/api/locks?id=' + project_id + '&api_key=' + worker.api_key + '&all=1')
        err = json.loads(res.data)
        assert res.status_code == 401, err
        assert err['status'] == 'failed', err
        assert err['target'] == 'project', err
        assert err['exception_cls'] == 'Unauthorized', err
        assert err['action'] == 'GET', err

    @with_context
    def test_project_locks_user_subadmin(self):
        """ Test API should work if user is subadmin"""
        admin = UserFactory.create(admin=True)
        subadmin = UserFactory.create(admin=False, subadmin=True)

        project = self.setupProjects()
        project_id = str(project.id)

        res = self.app.get('/api/locks?id=' + project_id + '&api_key=' + subadmin.api_key + '&all=1')
        data = json.loads(res.data)
        assert res.status_code == 200, data
        assert data[0]['product'] == 'test_product', data
        assert data[0]['short_name'] == 'test-app1', data

    @with_context
    def test_project_locks_user_admin(self):
        """ Test API should work if user is admin"""
        admin = UserFactory.create(admin=True)

        project = self.setupProjects()
        project_id = str(project.id)

        res = self.app.get('/api/locks?id=' + project_id + '&api_key=' + admin.api_key + '&all=1')
        data = json.loads(res.data)
        assert res.status_code == 200, data
        assert data[0]['product'] == 'test_product', data
        assert data[0]['short_name'] == 'test-app1', data

    @with_context
    def test_project_locks_get_by_id(self):
        """ Test get locks by project id when project id exists"""
        admin = UserFactory.create(admin=True)
        project1 = self.setupProjects()

        # Test get by id
        res = self.app.get('/api/locks?id=' + str(project1.id) + '&api_key=' + admin.api_key + '&all=1')
        data = json.loads(res.data)
        assert res.status_code == 200, data
        assert len(data) == 1, data
        assert data[0]['short_name'] == 'test-app1', data
        assert data[0]['locks'] == [], data

    @with_context
    def test_project_locks_no_params(self):
        """ Test API project query when no search params"""
        admin = UserFactory.create(admin=True)
        project1 = self.setupProjects()

        # Test no params
        res = self.app.get('/api/locks?api_key=' + admin.api_key)
        data = json.loads(res.data)
        assert res.status_code == 200, data
        assert len(data) == 0, data

    @with_context
    def test_project_locks_value_does_not_match(self):
        """ Test API project query when search value does not match"""
        admin = UserFactory.create(admin=True)
        project1 = self.setupProjects()

        # Test value DNE
        res = self.app.get('/api/locks?id=' + '9999' + '&api_key=' + admin.api_key + '&all=1')
        data = json.loads(res.data)
        assert res.status_code == 200, data
        assert len(data) == 0, data


    @with_context
    def test_project_locks_param_does_not_exist(self):
        """ Test API project query when search value does not match"""
        admin = UserFactory.create(admin=True)
        project1 = self.setupProjects()

        # Test bad param
        res = self.app.get('/api/locks?fakeparam=product::' + project1.info['product'] + '&api_key=' + admin.api_key + '&all=1')
        err = json.loads(res.data)
        assert res.status_code == 415, data
        assert err['status'] == 'failed', err
        assert err['target'] == 'project', err
        assert err['exception_cls'] == 'AttributeError', err
        assert err['action'] == 'GET', err

