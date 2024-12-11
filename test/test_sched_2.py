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

from test.helper import sched
from test import with_context, with_request_context
import json
import time
from unittest.mock import patch
from test.factories import TaskFactory, ProjectFactory, UserFactory
from pybossa.redis_lock import get_active_user_count, register_active_user, unregister_active_user, EXPIRE_LOCK_DELAY
from pybossa.core import sentinel


class TestSched(sched.Helper):
    def setUp(self):
        super(TestSched, self).setUp()
        self.endpoints = ['project', 'task', 'taskrun']

    @with_context
    def test_get_active_users_lock(self):
        """ Test number of locked tasks"""
        user = UserFactory.create(id=500)
        project = ProjectFactory.create(owner=user,info={'sched':'default'})
        TaskFactory.create_batch(2, project=project, n_answers=2)

        # Register the active user as a locked task.
        register_active_user(project.id, user.id, sentinel.master)
        # Verify the count of locked tasks for this project equals 1.
        count = get_active_user_count(project.id, sentinel.master)
        assert count == 1

        # Unregister the active user as a locked task.
        unregister_active_user(project.id, user.id, sentinel.master)
        # Verify the count of locked tasks for this project equals 1.
        # There is a delay before the lock is released.
        count = get_active_user_count(project.id, sentinel.master)
        assert count == 1

        # Confirm lock released after a delay.
        time.sleep(EXPIRE_LOCK_DELAY + 1)
        count = get_active_user_count(project.id, sentinel.master)
        assert not count
