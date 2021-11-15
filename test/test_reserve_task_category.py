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
from pybossa.core import project_repo
from pybossa.sched import (
    Schedulers,
    task_category_to_sql_filter,
    get_task_category_info
)

class TestReserveTaskCategory(sched.Helper):

    @with_context
    def test_task_category_to_sql_filter(self):
        # default behavior; returns null filters, category_keys for no category_keys passed
        project_id, task_category_key, exclude = "", "", False
        filters, category_keys = task_category_to_sql_filter(project_id, task_category_key, exclude)
        assert filters == "" and category_keys == [], "filters, category_keys must be []"

        # passing garbage category returns null filters, category_keys
        project_id, task_category_keys, exclude = "202", ["bad-category-key"], False
        filters, category_keys = task_category_to_sql_filter(project_id, task_category_keys, exclude)
        assert filters == "" and category_keys == [], "filters, category must be '', []"

        # task category key exists, returns sql filter and its associated category_keys
        project_id, exclude = "202", False
        task_category_keys = ["reserve_task_category:project:{}:category:name1:value1:name2:value2:user:1008:task:454".format(project_id)]
        filters, category_keys = task_category_to_sql_filter(project_id, task_category_keys, exclude)
        assert filters == "(task.info->>'name2' IN ('value2') AND task.info->>'name1' IN ('value1')) " and \
            category_keys == ["reserve_task_category:project:202:category:name1:value1:name2:value2:user:1008:task:454"], "filters, category must be []"

        # test exlude=True, multiple task category keys
        # negated sql filter with "NOT IN" clause
        # list of category_keys associated with sql filter
        project_id, exclude = "202", True
        task_category_keys = [
            "reserve_task_category:project:{}:category:name1:value1:name2:value2:user:1008:task:454".format(project_id),
            "reserve_task_category:project:{}:category:x:1:y:2:z:3:user:1008:task:454".format(project_id)
        ]
        filters, category_keys = task_category_to_sql_filter(project_id, task_category_keys, exclude)
        assert filters == "(task.info->>'y' IN ('2') AND task.info->>'x' IN ('1') AND task.info->>'z' IN ('3') AND task.info->>'name2' IN ('value2') AND task.info->>'name1' IN ('value1')) IS NOT TRUE" and \
            category_keys == [
                "reserve_task_category:project:202:category:name1:value1:name2:value2:user:1008:task:454",
                "reserve_task_category:project:202:category:x:1:y:2:z:3:user:1008:task:454"
            ], "filters, category must be as per keys passed and include negate clause"


    @with_context
    @patch('pybossa.redis_lock.LockManager.get_task_category_lock')
    def test_get_task_category_info(self, get_task_category_lock):
        owner = UserFactory.create(id=500)
        project = ProjectFactory.create(owner=owner)

        # test bad project id, user id returns empty sql_filters, category_keys
        project_id, user_id = -52, 9999
        sql_filters, category_keys = get_task_category_info(project_id, user_id)
        assert sql_filters == "" and category_keys == [], "sql_filters, category_keys must be '', []"

        # empty sql_filters, category_keys for projects with scheduler other than task_queue
        project.info['sched'] = Schedulers.locked
        project_repo.save(project)
        sql_filters, category_keys = get_task_category_info(project.id, owner.id)
        assert sql_filters == "" and category_keys == [], "sql_filters, category_keys must be '', []"

        # with no categories configured under project config
        # empty sql_filters, category_keys for projects with task queue scheduler
        project.info['sched'] = Schedulers.task_queue
        project_repo.save(project)
        sql_filters, category_keys = get_task_category_info(project.id, owner.id)
        assert sql_filters == "" and category_keys == [], "sql_filters, category_keys must be '', []"


        # with categories configured under project config
        # empty sql_filters, category_keys for projects with task queue scheduler
        # when there's no category lock present in redis cache
        project.info['sched'] = Schedulers.task_queue
        project.info['reserve_tasks'] = {
            "category": ["field_a", "field_b"]
        }
        project_repo.save(project)
        get_task_category_lock.return_value = []
        sql_filters, category_keys = get_task_category_info(project.id, owner.id)
        assert sql_filters == "" and category_keys == [], "sql_filters, category_keys must be '', []"

        # with categories configured under project config
        # sql_filters, category_keys for projects with task queue scheduler
        # to be built as per category lock present in redis cache
        project.info['sched'] = Schedulers.task_queue
        project.info['reserve_tasks'] = {
            "category": ["field_a", "field_b"]
        }
        project_repo.save(project)
        expected_category_keys = [
            "reserve_task_category:project:{}:category:name1:value1:name2:value2:user:1008:task:454".format(project.id),
            "reserve_task_category:project:{}:category:x:1:y:2:z:3:user:1008:task:2344".format(project.id)
        ]
        get_task_category_lock.return_value = expected_category_keys
        sql_filters, category_keys = get_task_category_info(project.id, owner.id)
        assert sql_filters == "(task.info->>'y' IN ('2') AND task.info->>'x' IN ('1') AND task.info->>'z' IN ('3') AND task.info->>'name2' IN ('value2') AND task.info->>'name1' IN ('value1')) " and \
            category_keys == expected_category_keys, "sql_filters, category_keys must be non empty"
