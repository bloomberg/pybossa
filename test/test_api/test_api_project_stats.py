# -*- coding: utf8 -*-
# This file is part of PYBOSSA.
#
# Copyright (C) 2017 Scifabric LTD.
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
from unittest.mock import patch

from pybossa import data_access
import pybossa.cache.project_stats as stats
from test import with_request_context
from test.factories import ProjectFactory, TaskFactory, TaskRunFactory, UserFactory
from test.test_api import TestAPI


class TestProjectStatsAPI(TestAPI):

    @with_request_context
    def test_query_projectstats(self):
        """Test API query for project stats endpoint works"""
        admin = UserFactory.create(admin=True)
        project_stats = []
        projects = ProjectFactory.create_batch(3)
        for project in projects:
            for task in TaskFactory.create_batch(4, project=project, n_answers=3):
                TaskRunFactory.create(task=task)
            stats.update_stats(project.id)
            ps = stats.get_stats(project.id, full=True)
            project_stats.append(ps)

        extra_stat_types = ['hours_stats', 'dates_stats', 'users_stats']

        url = '/api/projectstats?api_key={}'.format(admin.api_key)
        res = self.app_get_json(url)
        data = json.loads(res.data)
        assert len(data) == 3, data

        # Limits
        res = self.app.get(url + "&limit=1")
        data = json.loads(res.data)
        assert len(data) == 1, data

        # Keyset pagination
        res = self.app.get(url + '&limit=1&last_id=' + str(projects[1].id))
        data = json.loads(res.data)
        assert len(data) == 1, len(data)
        assert data[0]['id'] == project.id

        # Errors
        res = self.app.get(url + "&something")
        err = json.loads(res.data)
        err_msg = "AttributeError exception should be raised"
        res.status_code == 415, err_msg
        assert res.status_code == 415, err_msg
        assert err['action'] == 'GET', err_msg
        assert err['status'] == 'failed', err_msg
        assert err['exception_cls'] == 'AttributeError', err_msg

        # Desc filter
        res = self.app.get(url + "&orderby=wrongattribute")
        data = json.loads(res.data)
        err_msg = "It should be 415."
        assert data['status'] == 'failed', data
        assert data['status_code'] == 415, data
        assert 'has no attribute' in data['exception_msg'], data

        # Order by
        res = self.app.get(url + "&orderby=id")
        data = json.loads(res.data)
        err_msg = "It should get the last item first."
        ps_by_id = sorted(project_stats, key=lambda x: x.id, reverse=False)
        for i in range(len(project_stats)):
            assert ps_by_id[i].id == data[i]['id']

        # Desc filter
        res = self.app.get(url + "&orderby=id&desc=true")
        data = json.loads(res.data)
        err_msg = "It should get the last item first."
        ps_by_id = sorted(project_stats, key=lambda x: x.id, reverse=True)
        for i in range(len(project_stats)):
            assert ps_by_id[i].id == data[i]['id']

        # Without full filter
        res = self.app.get(url)
        data = json.loads(res.data)
        err_msg = "It should not return the full stats."
        extra = [row['info'].get(_type) for _type in extra_stat_types
                 for row in data if row['info'].get(_type)]
        assert not extra

        # With full filter
        res = self.app.get(url + "&full=1")
        data = json.loads(res.data)
        err_msg = "It should return full stats."
        for i, row in enumerate(data):
            for _type in extra_stat_types:
                assert row['info'][_type] == project_stats[i].info[_type]

    @with_request_context
    def test_projectstats_follow_project_read_authorization(self):
        owner = UserFactory.create()
        member = UserFactory.create()
        outsider = UserFactory.create()
        allowed_project = ProjectFactory.create(
            owner=owner, info={'project_users': [member.id]})
        blocked_project = ProjectFactory.create(
            owner=owner, info={'project_users': []})
        stats.update_stats(allowed_project.id)
        stats.update_stats(blocked_project.id)
        allowed_stats = stats.get_stats(allowed_project.id, full=True)

        with patch.object(data_access, 'data_access_levels', {'enabled': True}):
            response = self.app.get('/api/projectstats/{}'.format(
                allowed_stats.id))
            assert response.status_code == 401, response.status_code

            response = self.app.get(
                '/api/projectstats/{}?api_key={}'.format(
                    allowed_stats.id, outsider.api_key))
            assert response.status_code == 403, response.status_code

            response = self.app.get('/api/projectstats?api_key={}'.format(
                member.api_key))
            data = json.loads(response.data)
            assert response.status_code == 200, response.status_code
            assert [item['project_id'] for item in data] == [allowed_project.id]

            response = self.app.get(
                '/api/projectstats/{}?api_key={}'.format(
                    allowed_stats.id, member.api_key))
            assert response.status_code == 200, response.status_code
