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


    @with_context
    def test_project_details_only_allows_admin_subadmin(self):
        """ Test API project details authorization"""

        admin = UserFactory.create(admin=True)
        subadmin = UserFactory.create(subadmin=True)
        user = UserFactory.create(admin=False, subadmin=False)

        project = ProjectFactory.create(
            updated='2015-01-01T14:37:30.642119',
            short_name='test-app',
            info={
                'total': 150,
                'task_presenter': 'foo',
                'data_classification': dict(input_data="L4 - public", output_data="L4 - public"),
                'product' : 'test_product',
                'subproduct': 'test_subproduct1'
        })

        project_id = str(project.id)

        # endpoint should return 401 if the user is not logged in
        res = self.app.get('/api/project/details/' + project_id)
        err = json.loads(res.data)
        assert res.status_code == 401, err
        assert err['status'] == 'failed', err
        assert err['target'] == 'project', err
        assert err['exception_cls'] == 'Unauthorized', err
        assert err['action'] == 'GET', err

        # endpoint should return 401 if user is worker
        res = self.app.get('/api/project/details?id=' + project_id + '&api_key=' + user.api_key + '&all=1')
        err = json.loads(res.data)
        assert res.status_code == 401, err
        assert err['status'] == 'failed', err
        assert err['target'] == 'project', err
        assert err['exception_cls'] == 'Unauthorized', err
        assert err['action'] == 'GET', err

        # endpoint should work if user is subadmin
        res = self.app.get('/api/project/details?id=' + project_id + '&api_key=' + subadmin.api_key + '&all=1')
        data = json.loads(res.data)
        assert res.status_code == 200, data
        assert data[0]['product'] == 'test_product', data
        assert data[0]['short_name'] == 'test-app', data

        # endpoint should work if user is admin
        res = self.app.get('/api/project/details?id=' + project_id + '&api_key=' + admin.api_key + '&all=1')
        data = json.loads(res.data)
        assert res.status_code == 200, res
        assert data[0]['product'] == 'test_product', data
        assert data[0]['short_name'] == 'test-app', data

    @with_context
    def test_project_details_success(self):
        """ Test API project query when result exists"""
        admin = UserFactory.create(admin=True)
        project1 = ProjectFactory.create(
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

        # Test get by id
        res = self.app.get('/api/project/details?id=' + str(project1.id) + '&api_key=' + admin.api_key + '&all=1')
        data = json.loads(res.data)
        assert res.status_code == 200, data
        assert len(data) == 1, data
        assert data[0]['product'] == 'test_product', data
        assert data[0]['short_name'] == 'test-app1', data

        # Test get by product
        res = self.app.get('/api/project/details?info=product::' + project1.info['product'] + '&api_key=' + admin.api_key + '&all=1')
        data = json.loads(res.data)
        assert res.status_code == 200, data
        assert len(data) == 6, data
        assert data[0]['product'] == 'test_product', data
        assert data[1]['product'] == 'test_product', data

        # Test get by subproduct
        res = self.app.get('/api/project/details?info=subproduct::' + project1.info['subproduct'] + '&api_key=' + admin.api_key + '&all=1')
        data = json.loads(res.data)
        assert res.status_code == 200, data
        assert len(data) == 1, data
        assert data[0]['product'] == 'test_product', data
        assert data[0]['short_name'] == 'test-app1', data


    @with_context
    def test_project_details_invalid_params(self):
        """ Test API project query when result DNE or input is bad"""
        admin = UserFactory.create(admin=True)
        project1 = ProjectFactory.create(
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

        # Test no params
        res = self.app.get('/api/project/details?api_key=' + admin.api_key)
        data = json.loads(res.data)
        assert res.status_code == 200, data
        assert len(data) == 0, data

        # Test value DNE
        res = self.app.get('/api/project/details?id=' + '9999' + '&api_key=' + admin.api_key + '&all=1')
        data = json.loads(res.data)
        assert res.status_code == 200, data
        assert len(data) == 0, data

        # Test bad param
        res = self.app.get('/api/project/details?fakeparam=product::' + project1.info['product'] + '&api_key=' + admin.api_key + '&all=1')
        err = json.loads(res.data)
        assert res.status_code == 415, data
        assert err['status'] == 'failed', err
        assert err['target'] == 'project', err
        assert err['exception_cls'] == 'AttributeError', err
        assert err['action'] == 'GET', err

    @with_context
    def test_project_details_multiple_params(self):
        """ Test API project query when result exists"""
        admin = UserFactory.create(admin=True)
        project1 = ProjectFactory.create(
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

        # Test get by product and subproduct
        res = self.app.get('/api/project/details?info=product::' + project1.info['product']  + '&info=subproduct::' + project1.info['subproduct'] + '&api_key=' + admin.api_key + '&all=1')
        data = json.loads(res.data)
        assert res.status_code == 200, data
        assert data[0]['product'] == 'test_product', data
        assert data[0]['subproduct'] == 'test_subproduct1', data

