# -*- coding: utf8 -*-
# This file is part of PYBOSSA.
#
# Copyright (C) 2021 Scifabric LTD.
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

from mock import patch
from default import with_context
from helper import sched
from factories import TaskFactory, ProjectFactory, UserFactory
from pybossa.core import project_repo, sentinel
from pybossa.sched import (
    Schedulers,
    reserve_task_sql_filters,
    get_reserve_task_category_info,
    acquire_reserve_task_lock,
    release_reserve_task_lock_by_keys
)
import time

class TestReserveTaskCategory(sched.Helper):

    @with_context
    def test_task_category_to_sql_filter(self):
        # default behavior; returns null filters, category_keys for no category_keys passed
        project_id, task_category_key, exclude = "", "", False
        filters, category_keys = reserve_task_sql_filters(project_id, task_category_key, exclude)
        assert filters == "" and category_keys == [], "filters, category_keys must be []"

        # passing garbage category returns null filters, category_keys
        project_id, reserve_task_keys, exclude = "202", ["bad-category-key"], False
        filters, category_keys = reserve_task_sql_filters(project_id, reserve_task_keys, exclude)
        assert filters == "" and category_keys == [], "filters, category must be '', []"

        # task category key exists, returns sql filter and its associated category_keys
        project_id, exclude = "202", False
        reserve_task_keys = ["reserve_task:project:{}:category:name1:value1:name2:value2:user:1008:task:454".format(project_id)]
        filters, category_keys = reserve_task_sql_filters(project_id, reserve_task_keys, exclude)
        assert filters == " AND (task.info->>'name2' IN ('value2') AND task.info->>'name1' IN ('value1')) " and \
            category_keys == ["reserve_task:project:202:category:name1:value1:name2:value2:user:1008:task:454"], "filters, category must be []"

        # test exlude=True, multiple task category keys
        # negated sql filter with "NOT IN" clause
        # list of category_keys associated with sql filter
        project_id, exclude = "202", True
        reserve_task_keys = [
            "reserve_task:project:{}:category:name1:value1:name2:value2:user:1008:task:454".format(project_id),
            "reserve_task:project:{}:category:x:1:y:2:z:3:user:1008:task:454".format(project_id)
        ]
        filters, category_keys = reserve_task_sql_filters(project_id, reserve_task_keys, exclude)
        assert filters == " AND (task.info->>'y' IN ('2') AND task.info->>'x' IN ('1') AND task.info->>'z' IN ('3') AND task.info->>'name2' IN ('value2') AND task.info->>'name1' IN ('value1')) IS NOT TRUE" and \
            category_keys == [
                "reserve_task:project:202:category:name1:value1:name2:value2:user:1008:task:454",
                "reserve_task:project:202:category:x:1:y:2:z:3:user:1008:task:454"
            ], "filters, category must be as per keys passed and include negate clause"


    @with_context
    @patch('pybossa.redis_lock.LockManager.get_task_category_lock')
    def test_get_reserve_task_category_info(self, get_task_category_lock):
        owner = UserFactory.create(id=500)
        project = ProjectFactory.create(owner=owner)
        reserve_task_config = ["field_a", "field_b"]
        timeout = 60 * 60

        # test bad project id, user id returns empty sql_filters, category_keys
        project_id, user_id = -52, 9999
        sql_filters, category_keys = get_reserve_task_category_info(reserve_task_config, project_id, timeout, user_id)
        assert sql_filters == "" and category_keys == [], "sql_filters, category_keys must be '', []"

        # empty sql_filters, category_keys for projects with scheduler other than task_queue
        project.info['sched'] = Schedulers.locked
        project_repo.save(project)
        sql_filters, category_keys = get_reserve_task_category_info(reserve_task_config, project.id, timeout, owner.id)
        assert sql_filters == "" and category_keys == [], "sql_filters, category_keys must be '', []"

        # with no categories configured under project config
        # empty sql_filters, category_keys for projects with task queue scheduler
        project.info['sched'] = Schedulers.task_queue
        project_repo.save(project)
        sql_filters, category_keys = get_reserve_task_category_info(reserve_task_config, project.id, timeout, owner.id)
        assert sql_filters == "" and category_keys == [], "sql_filters, category_keys must be '', []"


        # with categories configured under project config
        # empty sql_filters, category_keys for projects with task queue scheduler
        # when there's no category lock present in redis cache
        project.info['sched'] = Schedulers.task_queue
        project.info['reserve_tasks'] = {
            "category": reserve_task_config
        }
        project_repo.save(project)
        get_task_category_lock.return_value = []
        sql_filters, category_keys = get_reserve_task_category_info(reserve_task_config, project.id, timeout, owner.id)
        assert sql_filters == "" and category_keys == [], "sql_filters, category_keys must be '', []"

        # with categories configured under project config
        # sql_filters, category_keys for projects with task queue scheduler
        # to be built as per category lock present in redis cache
        project.info['sched'] = Schedulers.task_queue
        project.info['reserve_tasks'] = {
            "category": reserve_task_config
        }
        project_repo.save(project)
        expected_category_keys = [
            "reserve_task:project:{}:category:name1:value1:name2:value2:user:1008:task:454".format(project.id),
            "reserve_task:project:{}:category:x:1:y:2:z:3:user:1008:task:2344".format(project.id)
        ]
        get_task_category_lock.return_value = expected_category_keys
        sql_filters, category_keys = get_reserve_task_category_info(reserve_task_config, project.id, timeout, owner.id)
        assert sql_filters == " AND (task.info->>'y' IN ('2') AND task.info->>'x' IN ('1') AND task.info->>'z' IN ('3') AND task.info->>'name2' IN ('value2') AND task.info->>'name1' IN ('value1')) " and \
            category_keys == expected_category_keys, "sql_filters, category_keys must be non empty"

    @with_context
    def test_acquire_and_release_reserve_task_lock(self):
        user = UserFactory.create()
        # project w/o reserve_tasks configured don't acquire lock
        project_info = dict(sched="task_queue_scheduler")
        task_info = dict(field_1="abc", field_2=123)
        category_fields = ["field_1", "field_2"]
        project = ProjectFactory.create(owner=user, info=project_info)
        task = TaskFactory.create_batch(1, project=project, n_answers=1, info=task_info)[0]
        timeout = 100

        assert acquire_reserve_task_lock(project.id, task.id, user.id, timeout) == False, "reserve task cannot be acquired due to missing required config"
        project.info['reserve_tasks'] = {
            "category": ["some_field"]
        }
        project_repo.save(project)
        assert acquire_reserve_task_lock(project.id, task.id, user.id, timeout) == False, "task not having reserve tasks config fields"

        project.info['reserve_tasks'] = {
            "category": category_fields
        }
        project_repo.save(project)
        acquire_reserve_task_lock(project.id, task.id, user.id, timeout)
        category_key = ":".join(["{}:{}".format(field, task.info[field]) for field in category_fields])
        expected_reserve_task_key = "reserve_task:project:{}:category:{}:user:{}:task:{}".format(
            project.id, category_key, user.id, task.id
        )
        assert expected_reserve_task_key in sentinel.master.keys(), "reserve task key must exist in redis cache"

        # release reserve task lock
        expiry = 1
        release_reserve_task_lock_by_keys([expected_reserve_task_key], timeout, expiry=expiry)
        time.sleep(expiry)
        assert expected_reserve_task_key not in sentinel.master.keys(), "reserve task key should not exist in redis cache"
