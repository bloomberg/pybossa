# -*- coding: utf8 -*-
# This file is part of PYBOSSA.
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
from unittest.mock import patch, MagicMock

from test import with_context, Test
from test.factories import UserFactory


class TestUserTaskPreferenceAPI(Test):

    @with_context
    def test_user_get_preferences_valid_user(self):
        admin = UserFactory.create()
        user = UserFactory.create()

        url = 'api/preferences/%s' % user.name

        res = self.app.get(url + '?api_key=%s' % admin.api_key)
        data = json.loads(res.data)

        assert res.status_code == 200, res.status_code
        assert data == {}, "Expected {}"

    @with_context
    @patch('pybossa.api.get_user_pref_metadata', return_value={"test": 1})
    def test_user_get_preferences_valid_user_data(self, get_user_pref_metadata):
        admin = UserFactory.create()
        user = UserFactory.create()

        url = 'api/preferences/%s' % user.name

        res = self.app.get(url + '?api_key=%s' % admin.api_key)
        assert res.status_code == 200, res.status_code

        data = json.loads(res.data)
        assert data == {"test": 1}, "Expected {\"test\": 1}"

    @with_context
    def test_user_get_preferences_invalid_user(self):
        admin = UserFactory.create()
        user = UserFactory.create()

        url = 'api/preferences/none'

        res = self.app.get(url + '?api_key=%s' % admin.api_key)
        assert res.status_code == 404, res.status_code

    @with_context
    def test_user_get_preferences_missing_user(self):
        admin = UserFactory.create()
        user = UserFactory.create()

        url = 'api/preferences/'

        res = self.app.get(url + '?api_key=%s' % admin.api_key)
        assert res.status_code == 404, res.status_code

    @with_context
    @patch('pybossa.api.get_user_pref_metadata', return_value=None)
    def test_user_get_preferences_missing_metadata(self, get_user_pref_metadata):
        admin = UserFactory.create()
        user = UserFactory.create()

        url = 'api/preferences/%s' % user.name

        res = self.app.get(url + '?api_key=%s' % admin.api_key)
        assert res.status_code == 500, res.status_code

    @with_context
    def test_user_get_preferences_anonymous_user(self):
        admin = UserFactory.create()
        restricted = UserFactory.create(restrict=True)

        url = 'api/preferences/%s' % restricted.name

        res = self.app.get(url)
        assert res.status_code == 404, res.status_code

    @with_context
    def test_user_set_preferences_anonymous_user(self):
        admin = UserFactory.create()
        restricted = UserFactory.create(restrict=True)

        url = 'api/preferences/%s' % restricted.name

        res = self.app.post(url)
        assert res.status_code == 404, res.status_code

    @with_context
    def test_user_set_preferences_missing_user(self):
        admin = UserFactory.create()
        user = UserFactory.create()

        url = 'api/preferences/'

        res = self.app.post(url + '?api_key=%s' % admin.api_key)
        assert res.status_code == 404, res.status_code

    @with_context
    def test_user_set_preferences_missing_payload(self):
        admin = UserFactory.create()
        user = UserFactory.create()

        url = 'api/preferences/%s' % user.name

        res = self.app.post(url + '?api_key=%s' % admin.api_key)
        assert res.status_code == 400, res.status_code

    @with_context
    def test_user_set_preferences_cannot_update_user(self):
        admin = UserFactory.create()
        user = UserFactory.create()
        user2 = UserFactory.create()

        # Attempt to update another user without permission.
        url = 'api/preferences/%s' % user2.name

        res = self.app.post(url + '?api_key=%s' % user.api_key, data=json.dumps({"test": 1}), content_type='application/json')

        assert res.status_code == 403, res.status_code
        assert res.mimetype == 'application/json', res

    @with_context
    def test_user_set_preferences_invalid_user(self):
        admin = UserFactory.create()
        user = UserFactory.create()

        url = 'api/preferences/none'

        res = self.app.post(url + '?api_key=%s' % admin.api_key)
        assert res.status_code == 404, res.status_code

    @with_context
    def test_user_set_preferences_update_user(self):
        admin = UserFactory.create()
        user = UserFactory.create()

        url = 'api/preferences/%s' % user.name
        payload = json.dumps({"test": 1})

        res = self.app.post(url + '?api_key=%s' % admin.api_key, data=payload, content_type='application/json')

        assert res.status_code == 200, res.status_code
        assert res.mimetype == 'application/json', res

        data = json.loads(res.data)
        assert data['profile'] == payload, "Invalid json response returned.";

    @with_context
    def test_user_set_preferences_update_user_empty(self):
        admin = UserFactory.create()
        user = UserFactory.create()

        url = 'api/preferences/%s' % user.name
        payload = json.dumps({})

        res = self.app.post(url + '?api_key=%s' % admin.api_key, data=payload, content_type='application/json')

        assert res.status_code == 200, res.status_code
        assert res.mimetype == 'application/json', res

        data = json.loads(res.data)
        assert data['profile'] == payload, "Invalid json response returned.";
