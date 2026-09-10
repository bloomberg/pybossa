# -*- coding: utf8 -*-
# This file is part of PYBOSSA.
#
# Copyright (C) 2016 Scifabric LTD.
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
from test import with_context
from test.factories import ProjectFactory
from test.test_api import TestAPI


class TestJwtAPI(TestAPI):

    @with_context
    def test_jwt_existing_project(self):
        """Project-token access stays retired for every project name."""
        project = ProjectFactory.create()
        url = '/api/auth/project/%s/token' % project.short_name
        resp = self.app.get(url)
        assert resp.status_code == 410, resp.data

        url = '/api/auth/project/nonexisting/token'
        resp = self.app.get(url)
        assert resp.status_code == 410, resp.data

    @with_context
    def test_jwt_with_auth_headers(self):
        """A valid legacy project secret no longer mints a token."""
        project = ProjectFactory.create()
        headers = {'Authorization': project.secret_key}
        url = '/api/auth/project/%s/token' % project.short_name
        resp = self.app.get(url, headers=headers)
        assert resp.status_code == 410, resp.data

    @with_context
    def test_jwt_with_auth_headers_nonproject(self):
        """Test JWT with Auth headers but no project."""
        project = ProjectFactory.create()
        headers = {'Authorization': project.secret_key}
        url = '/api/auth/project/nnon/token'
        resp = self.app.get(url, headers=headers)

        assert resp.status_code == 410, resp.data

    @with_context
    def test_jwt_with_auth_headers_wrong_secret(self):
        """Test JWT with Auth headers but wrong project secret."""
        project = ProjectFactory.create()
        headers = {'Authorization': 'foobar'}
        url = '/api/auth/project/%s/token' % project.short_name
        resp = self.app.get(url, headers=headers)
        assert resp.status_code == 410, resp.data
