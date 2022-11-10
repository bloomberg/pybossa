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

from unittest.mock import patch
import time
from nose.tools import assert_raises
from werkzeug.exceptions import BadRequest
from test import with_context
from test.helper import sched
from test.factories import TaskFactory, ProjectFactory, UserFactory, TaskRunFactory
from pybossa.core import project_repo, sentinel
from pybossa.sched import (
    Schedulers,
    reserve_task_sql_filters,
    get_reserve_task_category_info,
    acquire_reserve_task_lock,
    release_reserve_task_lock_by_keys,
    release_reserve_task_lock_by_id,
    get_reserve_task_key,
    get_reserved_categories_cache_keys
)
from pybossa.util import (
    cached_keys_to_reserved_categories,
    reserved_category_to_dataframe_query
)
from pybossa.cache import helpers
from pybossa.core import task_repo
import pandas as pd


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
        task_info = dict(name1="value1", name2="value2")
        expected_sql_filter = " AND ((task.info->>'name1' = 'value1' AND task.info->>'name2' = 'value2')) "
        reserve_task_keys = ["reserve_task:project:{}:category:name1:value1:name2:value2:user:1008:task:454".format(project_id)]
        filters, category_keys = reserve_task_sql_filters(project_id, reserve_task_keys, exclude)
        assert filters == expected_sql_filter and \
            category_keys == reserve_task_keys, "filters, category must be non empty"

        # test exlude=True, multiple task category keys
        # negated sql filter with "NOT IN" clause
        # list of category_keys associated with sql filter
        project_id, exclude = "202", True
        task_info_2 = dict(x=1, y=2, z=3)
        expected_key = ":".join(["{}:{}".format(field, task_info[field]) for field in sorted(task_info)])
        expected_key_2 = ":".join(["{}:{}".format(field, task_info_2[field]) for field in sorted(task_info_2)])
        reserve_task_keys = [
            "reserve_task:project:{}:category:{}:user:1008:task:454".format(project_id, expected_key),
            "reserve_task:project:{}:category:{}:user:1008:task:454".format(project_id, expected_key_2)
        ]
        filters, category_keys = reserve_task_sql_filters(project_id, reserve_task_keys, exclude)
        expected_sql_filter_1 = ["task.info->>'{}' = '{}'".format(field, task_info[field]) for field in sorted(task_info)]
        expected_sql_filter_2 = ["task.info->>'{}' = '{}'".format(field, task_info_2[field]) for field in sorted(task_info_2)]
        expected_sql_filter = " AND (({}) OR ({})) IS NOT TRUE ".format(" AND ".join(expected_sql_filter_1), " AND ".join(expected_sql_filter_2))
        assert filters == expected_sql_filter and \
            category_keys == [
                "reserve_task:project:202:category:name1:value1:name2:value2:user:1008:task:454",
                "reserve_task:project:202:category:x:1:y:2:z:3:user:1008:task:454"
            ], "filters, category must be as per keys passed and include negate, NOT IN clause"


    @with_context
    @patch('pybossa.redis_lock.LockManager.get_task_category_lock')
    def test_get_reserve_task_category_info(self, mock_get_task_category_lock):
        mock_get_task_category_lock.return_value = [], [], []

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
        task_info = dict(name1="value1", name2="value2")
        task_info_2 = dict(x=1, y=2, z=3)
        expected_key = ":".join(["{}:{}".format(field, task_info[field]) for field in sorted(task_info)])
        expected_key_2 = ":".join(["{}:{}".format(field, task_info_2[field]) for field in sorted(task_info_2)])
        expected_category_keys = [
            "reserve_task:project:{}:category:{}:user:1008:task:454".format(project.id, expected_key),
            "reserve_task:project:{}:category:{}:user:1008:task:2344".format(project.id, expected_key_2)
        ]
        mock_get_task_category_lock.return_value = [], [], expected_category_keys
        sql_filters, category_keys = get_reserve_task_category_info(reserve_task_config, project.id, timeout, owner.id)
        expected_sql_filter_1 = ["task.info->>'{}' = '{}'".format(field, task_info[field]) for field in sorted(task_info)]
        expected_sql_filter_2 = ["task.info->>'{}' = '{}'".format(field, task_info_2[field]) for field in sorted(task_info_2)]
        expected_sql_filter = " AND (({}) OR ({})) ".format(" AND ".join(expected_sql_filter_1), " AND ".join(expected_sql_filter_2))
        assert sql_filters == expected_sql_filter and \
            category_keys == expected_category_keys, "sql_filters, category_keys must be non empty"

        # reserve task disabled for private instance,
        with patch.dict(self.flask_app.config, {'PRIVATE_INSTANCE': True}):
            sql_filters, category_keys = get_reserve_task_category_info(reserve_task_config, project.id, timeout, owner.id)
            assert not sql_filters, "sql_filters must be empty for private instance"
            assert not category_keys, "sql_filters must be empty for private instance"


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

        assert not acquire_reserve_task_lock(project.id, task.id, user.id, timeout), "reserve task cannot be acquired due to missing required config"
        project.info['reserve_tasks'] = {
            "category": ["some_field"]
        }
        project_repo.save(project)
        assert not acquire_reserve_task_lock(project.id, task.id, user.id, timeout), "task not having reserve tasks config fields"

        project.info['reserve_tasks'] = {
            "category": category_fields
        }
        project_repo.save(project)
        acquire_reserve_task_lock(project.id, task.id, user.id, timeout)
        category_key = ":".join(["{}:{}".format(field, task.info[field]) for field in category_fields])
        expected_reserve_task_key = "reserve_task:project:{}:category:{}:user:{}:task:{}".format(
            project.id, category_key, user.id, task.id
        )
        assert expected_reserve_task_key.encode() in sentinel.master.keys(), "reserve task key must exist in redis cache"

        # release reserve task lock
        expiry = 1
        release_reserve_task_lock_by_keys([expected_reserve_task_key], timeout, expiry=expiry)
        time.sleep(expiry + 0.1)  # add a little time to make sure the ttl expires
        assert expected_reserve_task_key.encode() not in sentinel.master.keys(), "reserve task key should not exist in redis cache"


    @with_context
    def test_reserve_task_category_lock_raises_exceptions(self):
        # missing project_id raises exception
        with assert_raises(BadRequest):
            get_reserve_task_category_info(["x", "y"], None, 1, 1)

        # missing user id and passing exclude user raises exception
        with assert_raises(BadRequest):
            get_reserve_task_category_info(["x", "y"], 1, 1, user_id=None, exclude_user=True)

        _, category_keys = get_reserve_task_category_info(["x", "y"], 1, 1, 1)
        assert not category_keys, "reserve task category keys should not be present"

        user = UserFactory.create()
        project = ProjectFactory.create(
            owner=user,
            info=dict(
                sched="task_queue_scheduler",
                reserve_tasks=dict(
                    category=["field_1", "field_2"]
                )
            )
        )
        task = TaskFactory.create_batch(
            1, project=project, n_answers=1,
            info=dict(field_1="abc", field_2=123)
        )[0]
        with assert_raises(BadRequest):
            acquire_reserve_task_lock(project.id, task.id, None, 1)


    @with_context
    def test_reserve_task_category_lock_exclude_user(self):
        # with exclude_user = True, exclude user category key for user id = ``
        reserve_task_config = ["field_1", "field_2"]
        user = UserFactory.create()
        project = ProjectFactory.create(
            owner=user,
            info=dict(
                sched="task_queue_scheduler",
                reserve_tasks=dict(
                    category=reserve_task_config
                )
            )
        )
        tasks = TaskFactory.create_batch(
            2, project=project, n_answers=1,
            info=dict(field_1="abc", field_2=123)
        )

        non_excluded_user_id = 2
        acquire_reserve_task_lock(project.id, tasks[0].id, user.id, 1)
        acquire_reserve_task_lock(project.id, tasks[1].id, non_excluded_user_id, 1)
        expected_category_keys = [
            "reserve_task:project:{}:category:field_1:abc:field_2:123:user:{}:task:{}".format(
                project.id, non_excluded_user_id, tasks[1].id
            )]
        _, category_keys = get_reserve_task_category_info(reserve_task_config, 1, 1, user.id, exclude_user=True)
        assert category_keys == expected_category_keys, "reserve task category keys should exclude user {} reserve category key".format(user.id)
        # cleanup; release reserve task lock
        expiry = 1
        release_reserve_task_lock_by_id(project.id, tasks[0].id, user.id, 1, expiry=expiry)
        release_reserve_task_lock_by_id(project.id, tasks[1].id, non_excluded_user_id, 1, expiry=expiry)


    @with_context
    def test_release_reserve_task_lock_by_id(self):
        timeout = 100
        category_fields = ["field_1", "field_2"]
        user = UserFactory.create()
        # project w/o reserve_tasks configured don't acquire lock
        project = ProjectFactory.create(
            owner=user,
            info=dict(
                sched="task_queue_scheduler",
                reserve_tasks=dict(
                    category=category_fields
                )
            )
        )
        task = TaskFactory.create_batch(
            1, project=project, n_answers=1,
            info=dict(field_1="abc", field_2=123)
        )[0]
        acquire_reserve_task_lock(project.id, task.id, user.id, timeout)
        category_key = ":".join(["{}:{}".format(field, task.info[field]) for field in category_fields])
        expected_reserve_task_key = "reserve_task:project:{}:category:{}:user:{}:task:{}".format(
            project.id, category_key, user.id, task.id
        )
        assert expected_reserve_task_key.encode() in sentinel.master.keys(), "reserve task key must exist in redis cache"

        # release reserve task lock
        expiry = 1
        release_reserve_task_lock_by_id(project.id, task.id, user.id, timeout, expiry=expiry)
        time.sleep(expiry)
        assert expected_reserve_task_key.encode() not in sentinel.master.keys(), "reserve task key should not exist in redis cache"

        # test releasing multiple locks
        batch_number = 10
        tasks = TaskFactory.create_batch(
            batch_number, project=project, n_answers=1,
            info=dict(field_1="abc", field_2=123)
        )
        for task in tasks:
            acquire_reserve_task_lock(project.id, task.id, user.id, timeout)
            category_key = ":".join([f"{field}:{task.info[field]}" for field in category_fields])
            expected_reserve_task_key = f"reserve_task:project:{project.id}:category:{category_key}:user:{user.id}:task:{task.id}"
            assert expected_reserve_task_key.encode() in sentinel.master.keys(), "reserve task key must exist in redis cache"

        release_reserve_task_lock_by_id(project.id, tasks[0].id, user.id, timeout,
                                        expiry=expiry, release_all_task=True)
        time.sleep(expiry)
        for task in tasks:
            category_key = ":".join([f"{field}:{task.info[field]}" for field in category_fields])
            expected_reserve_task_key = f"reserve_task:project:{project.id}:category:{category_key}:user:{user.id}:task:{task.id}"
            assert expected_reserve_task_key.encode() not in sentinel.master.keys(), "reserve task key should not exist in redis cache"

    @with_context
    def test_get_reserve_task_key(self):
        category_fields = ["field_1", "field_2"]
        task_info = dict(field_1="abc", field_2=123)
        expected_key = ":".join(["{}:{}".format(field, task_info[field]) for field in sorted(category_fields)])
        user = UserFactory.create()
        # project w/o reserve_tasks configured don't acquire lock
        project = ProjectFactory.create(
            owner=user,
            info=dict(
                sched="task_queue_scheduler",
                reserve_tasks=dict(
                    category=category_fields
                )
            )
        )
        task = TaskFactory.create_batch(
            1, project=project, n_answers=1,
            info=task_info
        )[0]
        reserve_key = get_reserve_task_key(task.id)
        assert reserve_key == expected_key, "reserve key expected to be {}".format(expected_key)

    @with_context
    @patch("pybossa.redis_lock.LockManager.get_task_category_lock")
    def test_get_reserved_categories_cache_keys(self, mock_get_task_category_lock):
        """Test get_reserved_categories_cache_keys returns reserved categories from cache"""
        from flask import current_app

        reserved_task_config = ["name1", "name2"]
        project_id = 1
        timeout = 30
        user_id = 1

        # ensure reserved task category disabled for private instance
        current_app.config["PRIVATE_INSTANCE"] = True
        user_category_keys, other_user_category_keys, all_user_category_keys = get_reserved_categories_cache_keys(
            reserved_task_config, project_id, timeout, user_id)
        assert not (user_category_keys or other_user_category_keys or all_user_category_keys)

        current_app.config["PRIVATE_INSTANCE"] = False
        category = "name1:*:name2:*"
        mock_get_task_category_lock.return_value = [], [], []
        user_category_keys, other_user_category_keys, all_user_category_keys = get_reserved_categories_cache_keys(
            reserved_task_config, project_id, timeout, user_id)
        mock_get_task_category_lock.assert_called_once_with(project_id, user_id, category)



    @with_context
    def test_cached_keys_to_reserved_categories(self):
        """Test cached_keys_to_reserved_categories returns correct reserved categories from cached keys"""
        # default behavior; returns null filters, category_keys for no category_keys passed
        project_id, reserve_task_keys, reserved_categories = "", "", []
        with assert_raises(BadRequest):
            reserved_categories = cached_keys_to_reserved_categories(project_id, reserve_task_keys)
        assert not reserved_categories, "reserved_categories expected to be []"

        # passing garbage category returns null filters, category_keys
        project_id, reserve_task_keys = "202", ["bad-category-key"]
        reserved_categories = cached_keys_to_reserved_categories(project_id, reserve_task_keys)
        assert not reserved_categories, "reserved_categories expected to be [] with key not part of cache"

        # task category key exists, returns list of associated reserved categories in key,value pair
        project_id = "202"
        expected_reserved_categories = [{"name1": "value1", "name2": "value2"}, {"abc": "123", "def": "456"}]
        reserve_task_keys = [
            "reserve_task:project:202:category:name1:value1:name2:value2:user:1008:task:111",
            "reserve_task:project:202:category:abc:123:def:456:user:1008:task:222"
        ]
        reserved_categories = cached_keys_to_reserved_categories(project_id, reserve_task_keys)
        assert reserved_categories == expected_reserved_categories

        # duplicate task category key exists under different task ids,
        # returns list of associated unique reserved categories in key,value pair
        expected_reserved_categories = [{"name1": "value1", "name2": "value2"}, {"name1": "123", "name2": "456"}]
        reserve_task_keys = [
            "reserve_task:project:202:category:name1:value1:name2:value2:user:1008:task:111",
            "reserve_task:project:202:category:name1:123:name2:456:user:1008:task:222",
            "reserve_task:project:202:category:name1:value1:name2:value2:user:1008:task:333",   # different task with same reserved category
        ]
        reserved_categories = cached_keys_to_reserved_categories(project_id, reserve_task_keys)
        assert len(reserved_categories) == 2, "only two unique reserved categories should be returned"
        assert reserved_categories == expected_reserved_categories

    @with_context
    def test_reserved_category_to_dataframe_query(self):
        """Test dataframe queries are generated correctly from categories"""
        reserved_categories = ["subject", "score"]
        categories = [{"subject": "physics", "score": 62}, {"subject": "math", "score": 47}]

        expected_query = "(subject == 'physics' & score == 62) | (subject == 'math' & score == 47)"
        df_query = reserved_category_to_dataframe_query(reserved_categories, categories)
        assert df_query == expected_query, df_query

        negate_query = True
        expected_negate_query = "~(subject == 'physics' & score == 62) & ~(subject == 'math' & score == 47)"
        df_query = reserved_category_to_dataframe_query(reserved_categories, categories, negate_query)
        assert df_query == expected_negate_query, df_query

    @with_context
    def test_filtered_data_with_reserved_category_to_dataframe_query(self):
        """Test dataframe data is filtered correctly using dataframe queries"""
        # create a dataFrame
        data = {
            "subject": ["physics", "math", "literature", "calculus", "physics", "math", "literature", "math"],
            "score":[62, 47, 55, 74, 31, 77, 85, 47]
        }
        df = pd.DataFrame(data, columns=['subject','score'])
        # All records
		# subject	score
		# 0	semester1	62
		# 1	semester2	47
		# 2	semester3	55
		# 3	semester4	74
		# 4	semester1	31
		# 5	semester2	77
		# 6	semester3	85
		# 7	semester2	47

        reserved_categories = ["subject", "score"]
        categories = [{"subject": "physics", "score": 62}, {"subject": "math", "score": 47}]

        # expected data
        #    subject  score
        # 0  physics     62
        # 1     math     47
        # 7     math     47
        df_query = reserved_category_to_dataframe_query(reserved_categories, categories)
        filtered_data = df.query(df_query)
        assert filtered_data.shape == (3, 2), "Only 3 filtered rows to be present"
        assert filtered_data.iloc[0][0] == "physics" and filtered_data.iloc[0][1] == 62, filtered_data.iloc[0]
        assert filtered_data.iloc[1][0] == "math" and filtered_data.iloc[1][1] == 47, filtered_data.iloc[1]
        assert filtered_data.iloc[2][0] == "math" and filtered_data.iloc[2][1] == 47, filtered_data.iloc[2]

    @with_context
    def test_filtered_data_with_reserved_category_to_dataframe_negate_query(self):
        """Test dataframe data is filtered correctly using dataframe queries"""
        # create a dataFrame
        data = {
            "subject": ["physics", "math", "literature", "calculus", "physics", "math", "literature", "math"],
            "score":[62, 47, 55, 74, 31, 77, 85, 47]
        }
        df = pd.DataFrame(data, columns=['subject','score'])
        # All records
        #       subject  score
        # 0     physics     62
        # 1        math     47
        # 2  literature     55
        # 3    calculus     74
        # 4     physics     31
        # 5        math     77
        # 6  literature     85
        # 7        math     47

        reserved_categories = ["subject", "score"]
        categories = [{"subject": "physics", "score": 31}, {"subject": "math", "score": 47}]

        # exclude data for (subject == 'physics' & score == 31) & (subject == 'math' & score == 47)
        # expected data
        #   subject	    score
        # 0	physics	    62
        # 2	literature	55
        # 3	calculus	74
        # 5	math	    77
        # 6	literature	85
        df_query = reserved_category_to_dataframe_query(reserved_categories, categories, negate_query=True)
        filtered_data = df.query(df_query)
        assert filtered_data.shape == (5, 2), "Only 5 filtered rows to be present"
        assert filtered_data.iloc[0][0] == "physics" and filtered_data.iloc[0][1] == 62, filtered_data.iloc[0]
        assert filtered_data.iloc[1][0] == "literature" and filtered_data.iloc[1][1] == 55, filtered_data.iloc[1]
        assert filtered_data.iloc[2][0] == "calculus" and filtered_data.iloc[2][1] == 74, filtered_data.iloc[2]
        assert filtered_data.iloc[3][0] == "math" and filtered_data.iloc[3][1] == 77, filtered_data.iloc[3]
        assert filtered_data.iloc[4][0] == "literature" and filtered_data.iloc[4][1] == 85, filtered_data.iloc[4]

    @with_context
    @patch("pybossa.cache.helpers.get_reserved_categories_cache_keys")
    def test_n_available_tasks_reserved_category(self, mock_reserved_cache_keys):
        """Test n_available_tasks_for_user with reserved categories"""

        project_info = {
            "reserve_tasks": {
                "category": ["subject", "score"]
            },
            "sched": Schedulers.task_queue
        }
        project = ProjectFactory.create(info=project_info)
        # mock reserved cache keys so that n_available_for_tasks gives correct values
        # based on different reserved cache keys in the cache.
        # first time, return cache key so that 2 tasks for the category are reserved out of 8
        # second time, return cache so that 5 tasks for different categories are reserved out of 8
        other_user_reserved_categories_keys = [
            f"reserve_task:project:{project.id}:category:subject:math:score:47:user:1008:task:111",
        ]
        expected_available_tasks_first_call = 6

        other_user_reserved_categories_keys_2 = [
            f"reserve_task:project:{project.id}:category:subject:physics:score:62:user:1008:task:111",
            f"reserve_task:project:{project.id}:category:subject:math:score:47:user:1008:task:222",
            f"reserve_task:project:{project.id}:category:subject:literature:score:55:user:1008:task:333",
            f"reserve_task:project:{project.id}:category:subject:calculus:score:74:user:1008:task:444",
        ]
        mock_reserved_cache_keys.side_effect = [
            (None, other_user_reserved_categories_keys, None),
            (None, other_user_reserved_categories_keys_2, None)
        ]
        expected_available_tasks_second_call = 3

        TaskFactory.create(project=project, info=dict(subject="physics", score=62), worker_filter={})
        TaskFactory.create(project=project, info=dict(subject="math", score=47), worker_filter={})
        TaskFactory.create(project=project, info=dict(subject="literature", score=55), worker_filter={})
        TaskFactory.create(project=project, info=dict(subject="calculus", score=74), worker_filter={})
        TaskFactory.create(project=project, info=dict(subject="physics", score=31), worker_filter={})
        TaskFactory.create(project=project, info=dict(subject="math", score=77), worker_filter={})
        TaskFactory.create(project=project, info=dict(subject="literature", score=85), worker_filter={})
        TaskFactory.create(project=project, info=dict(subject="math", score=47), worker_filter={})
        user = UserFactory.create()

        # two tasks out of total 8 tasks expected to be excluded as they're reserved by other user
        n_available_tasks = helpers.n_available_tasks_for_user(project, user_id=user.id)
        assert n_available_tasks == expected_available_tasks_first_call, n_available_tasks


        n_available_tasks = helpers.n_available_tasks_for_user(project, user_id=user.id)
        assert n_available_tasks == expected_available_tasks_second_call, n_available_tasks
