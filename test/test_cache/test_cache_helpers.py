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

from test import Test, with_context, with_request_context
from test.factories import (ProjectFactory, TaskFactory, TaskRunFactory, UserFactory)
from pybossa.cache import helpers
from pybossa.cache.project_stats import update_stats
from pybossa.cache.task_browse_helpers import parse_tasks_browse_order_by_args, user_meet_task_requirement

class TestHelpersCache(Test):

    @with_context
    def test_n_gold_tasks_no_tasks(self):
        """Test n_gold_tasks returns 0 for user if the project
        has no tasks"""
        project = ProjectFactory.create()

        n_gold_tasks = helpers.n_gold_tasks(project.id)

        assert n_gold_tasks == 0, n_gold_tasks

    @with_context
    def test_n_gold_tasks_no_gold_tasks(self):
        """Test n_gold_tasks returns 0 for user if the project
        has no gold tasks"""
        project = ProjectFactory.create()
        task = TaskFactory.create(project=project)

        n_gold_tasks = helpers.n_gold_tasks(project.id)

        assert n_gold_tasks == 0, n_gold_tasks

    @with_context
    def test_n_gold_tasks_gold_tasks(self):
        """Test n_gold_tasks returns 1 for user if the project
        has 1 gold tasks"""
        project = ProjectFactory.create()
        task = TaskFactory.create(project=project, calibration=1)

        n_gold_tasks = helpers.n_gold_tasks(project.id)

        assert n_gold_tasks == 1, n_gold_tasks

    @with_context
    def test_n_available_tasks_no_tasks(self):
        """Test n_available_tasks returns 0 for user if the project
        has no tasks"""
        project = ProjectFactory.create()

        n_available_tasks = helpers.n_available_tasks(project.id)

        assert n_available_tasks == 0, n_available_tasks

    @with_context
    def test_n_available_tasks_no_taskruns(self):
        """Test n_available_tasks returns 1 for authenticated user
        if there are no taskruns"""
        project = ProjectFactory.create()
        task = TaskFactory.create(project=project)

        n_available_tasks = helpers.n_available_tasks(project.id)

        assert n_available_tasks == 1, n_available_tasks

    @with_context
    def test_n_available_tasks_all_tasks_completed(self):
        """Test n_available_tasks returns 0 for user if all the
        tasks are completed"""
        project = ProjectFactory.create()
        task = TaskFactory.create(project=project, state='completed')

        n_available_tasks = helpers.n_available_tasks(project.id)

        assert n_available_tasks == 0, n_available_tasks

    @with_context
    def test_n_available_tasks_all_tasks_answered_by_user(self):
        """Test n_available_tasks returns 0 for user if he has
        submitted taskruns for all the tasks"""
        user = UserFactory.create()
        project = ProjectFactory.create()
        task = TaskFactory.create(project=project, n_answers=2)
        taskrun = TaskRunFactory.create(task=task, user=user)

        n_available_tasks = helpers.n_available_tasks(project.id)

        assert task.state != 'completed', task.state
        assert n_available_tasks == 1, n_available_tasks

    @with_context
    def test_n_available_tasks_include_gold_task(self):
        """Test n_available_tasks returns 0 for user if he has
        submitted taskruns for all the tasks"""
        project = ProjectFactory.create()
        task = TaskFactory.create(project=project, calibration=1)

        n_available_tasks_include_gold = helpers.n_available_tasks(project.id, include_gold_task=True)
        n_available_tasks_exclude_gold = helpers.n_available_tasks(project.id)

        assert task.state != 'completed', task.state
        assert n_available_tasks_include_gold == 1, n_available_tasks_include_gold
        assert n_available_tasks_exclude_gold == 0, n_available_tasks_exclude_gold

    @with_context
    def test_n_available_tasks_for_user_no_tasks(self):
        """Test n_available_tasks_for_user returns 0 if the project has no tasks"""
        project = ProjectFactory.create()

        n_available_tasks = helpers.n_available_tasks_for_user(project, user_id=1)

        assert n_available_tasks == 0, n_available_tasks

    @with_context
    def test_n_available_tasks_for_user_no_taskruns_tasks(self):
        """Test n_available_tasks_for_user returns 1 for user
        if there are no taskruns"""
        project = ProjectFactory.create()
        task = TaskFactory.create(project=project)

        n_available_tasks = helpers.n_available_tasks_for_user(project, user_id=1)

        assert n_available_tasks == 1, n_available_tasks

    @with_context
    def test_n_available_tasks_for_user_completed_tasks(self):
        """Test n_available_tasks_for_user returns 0 for user if all the
        tasks are completed"""
        project = ProjectFactory.create()
        task = TaskFactory.create(project=project, state='completed')

        n_available_tasks = helpers.n_available_tasks_for_user(project, user_id=1)

        assert n_available_tasks == 0, n_available_tasks

    @with_context
    def test_n_available_tasks_for_user_answered_by_you_tasks(self):
        """Test n_available_tasks_for_user returns 0 for user if he has
        submitted taskruns for all the tasks"""
        project = ProjectFactory.create()
        task = TaskFactory.create(project=project, n_answers=2)
        user = UserFactory.create()
        taskrun = TaskRunFactory.create(task=task, user=user)

        n_available_tasks = helpers.n_available_tasks_for_user(project, user_id=user.id)

        assert task.state != 'completed', task.state
        assert n_available_tasks == 0, n_available_tasks

    @with_context
    def test_n_available_tasks_for_user_some_tasks_answered_by_user(self):
        """Test n_available_tasks_for_user returns 1 for user if he has
        submitted taskruns for one of the tasks but there is still another task"""
        project = ProjectFactory.create()
        answered_task = TaskFactory.create(project=project)
        available_task = TaskFactory.create(project=project)
        user = UserFactory.create()
        taskrun = TaskRunFactory.create(task=answered_task, user=user)

        n_available_tasks = helpers.n_available_tasks_for_user(project, user_id=user.id)
        assert n_available_tasks == 1, n_available_tasks

    @with_context
    def test_n_available_tasks_some_task_answered_by_another_user(self):
        """Test n_available_tasks_for_user returns 1 for a user if another
        user has submitted taskruns for the task but he hasn't"""
        project = ProjectFactory.create()
        task = TaskFactory.create(project=project)
        user = UserFactory.create()
        taskrun = TaskRunFactory.create(task=task)

        n_available_tasks = helpers.n_available_tasks_for_user(project, user_id=user.id)
        assert n_available_tasks == 1, n_available_tasks

    @with_context
    def test_n_unexpired_gold_tasks_no_tasks(self):
        project = ProjectFactory.create()
        task = TaskFactory.create(project=project)

        n_gold_tasks = helpers.n_unexpired_gold_tasks(project.id)
        assert n_gold_tasks == 0

    @with_context
    def test_n_unexpired_gold_tasks_has_tasks(self):
        project = ProjectFactory.create()
        task = TaskFactory.create_batch(3, project=project, calibration=1)

        n_gold_tasks = helpers.n_unexpired_gold_tasks(project.id)
        assert n_gold_tasks == 3

    @with_context
    def test_n_unexpired_gold_tasks_expired_tasks(self):
        project = ProjectFactory.create()
        task = TaskFactory.create(project=project,
            calibration=1,
            expiration='2012-01-01T00:00:00')

        n_gold_tasks = helpers.n_unexpired_gold_tasks(project.id)
        assert n_gold_tasks == 0

    @with_context
    def test_n_unexpired_gold_tasks_mixed_tasks(self):
        project = ProjectFactory.create()
        task = TaskFactory.create_batch(2, project=project)
        task = TaskFactory.create_batch(2, project=project, calibration=1)
        task = TaskFactory.create_batch(2, project=project,
            calibration=1,
            expiration='2012-01-01T00:00:00')

        n_gold_tasks = helpers.n_unexpired_gold_tasks(project.id)
        assert n_gold_tasks == 2

    @with_context
    def test_n_unexpired_gold_tasks_unexpired_tasks(self):
        project = ProjectFactory.create()
        task = TaskFactory.create_batch(2, project=project)
        task = TaskFactory.create_batch(2, project=project, calibration=1)
        task = TaskFactory.create_batch(2, project=project,
            calibration=1,
            expiration='2999-01-01T00:00:00')

        n_gold_tasks = helpers.n_unexpired_gold_tasks(project.id)
        assert n_gold_tasks == 4

    @with_request_context
    def test_check_contributing_state_completed(self):
        """Test check_contributing_state returns 'completed' for a project with all
        tasks completed and user that has contributed to it"""
        project = ProjectFactory.create()
        task = TaskFactory.create(project=project, n_answers=1)
        user = UserFactory.create()
        TaskRunFactory.create_batch(1, task=task, user=user)

        update_stats(project.id)
        contributing_state = helpers.check_contributing_state(project=project,
                                                              user_id=user.id)

        assert task.state == 'completed', task.state
        assert contributing_state == 'completed', contributing_state

    @with_request_context
    def test_check_contributing_state_completed_user_not_contributed(self):
        """Test check_contributing_state returns 'completed' for a project with all
        tasks completed even if the user has not contributed to it"""
        project = ProjectFactory.create()
        task = TaskFactory.create(project=project, n_answers=2)
        TaskRunFactory.create_batch(2, task=task)
        user = UserFactory.create()
        update_stats(project.id)
        contributing_state = helpers.check_contributing_state(project=project,
                                                              user_id=user.id)

        assert task.state == 'completed', task.state
        assert contributing_state == 'completed', contributing_state

    @with_context
    def test_check_contributing_state_ongoing_tasks_not_contributed(self):
        """Test check_contributing_state returns 'can_contribute' for a project
        with ongoing tasks a user has not contributed to"""
        project = ProjectFactory.create()
        task = TaskFactory.create(project=project)
        user = UserFactory.create()

        contributing_state = helpers.check_contributing_state(project=project,
                                                              user_id=user.id)

        assert contributing_state == 'can_contribute', contributing_state

    @with_context
    def test_check_contributing_state_ongoing_tasks_contributed(self):
        """Test check_contributing_state returns 'cannot_contribute' for a project
        with ongoing tasks to which the user has already contributed"""
        project = ProjectFactory.create()
        task = TaskFactory.create(project=project, n_answers=3)
        user = UserFactory.create()
        TaskRunFactory.create(task=task, user=user)
        contributing_state = helpers.check_contributing_state(project=project,
                                                              user_id=user.id)

        assert contributing_state == 'cannot_contribute', contributing_state

    @with_context
    def test_check_contributing_state_draft(self):
        """Test check_contributing_state returns 'draft' for a project that has
        ongoing tasks but has no presenter"""
        project = ProjectFactory.create(published=False, info={})
        task = TaskFactory.create(project=project)
        user = UserFactory.create()

        contributing_state = helpers.check_contributing_state(project=project,
                                                              user_id=user.id)

        assert 'task_presenter' not in project.info
        assert contributing_state == 'draft', contributing_state

    @with_context
    def test_check_contributing_state_draft_presenter(self):
        """Test check_contributing_state returns 'draft' for a project that has
        no tasks but has a presenter"""
        project = ProjectFactory.create(published=False)
        user = UserFactory.create()

        contributing_state = helpers.check_contributing_state(project=project,
                                                              user_id=user.id)

        assert 'task_presenter' in project.info
        assert contributing_state == 'draft', contributing_state

    @with_context
    def test_check_contributing_state_publish(self):
        """Test check_contributing_state returns 'publish' for a project that is
        not published but is ready to be validated for publication (i.e. has both
        tasks and a task presenter"""
        project = ProjectFactory.create(published=False)
        task = TaskFactory.create(project=project)
        user = UserFactory.create()

        contributing_state = helpers.check_contributing_state(project=project,
                                                              user_id=user.id)

        assert contributing_state == 'publish', contributing_state

    @with_context
    def test_n_priority_x_tasks_no_tasks(self):
        """Test n_priority_x_tasks returns 0 for user if the project
        has no tasks"""
        project = ProjectFactory.create()

        n_priority_x_tasks = helpers.n_priority_x_tasks(project.id)

        assert n_priority_x_tasks == 0, n_priority_x_tasks

    @with_context
    def test_n_priority_x_tasks_no_taskruns(self):
        """Test n_priority_x_tasks returns 1 for authenticated user
        if there are no taskruns but create task with priority 1.0"""
        project = ProjectFactory.create()
        _ = TaskFactory.create(project=project, priority_0=1.0)

        n_priority_x_tasks = helpers.n_priority_x_tasks(project.id)

        assert n_priority_x_tasks == 1, n_priority_x_tasks

    @with_context
    def test_n_priority_x_tasks_no_taskruns_default_priority(self):
        """Test n_priority_x_tasks returns 0 for authenticated user
        if there are no taskruns but create task with default priority"""
        project = ProjectFactory.create()
        _ = TaskFactory.create(project=project)

        n_priority_x_tasks = helpers.n_priority_x_tasks(project.id)

        assert n_priority_x_tasks == 0, n_priority_x_tasks

    @with_context
    def test_n_priority_x_tasks_all_tasks_completed(self):
        """Test n_priority_x_tasks returns 0 for user if all the
        tasks are completed"""
        project = ProjectFactory.create()
        _ = TaskFactory.create(project=project, state='completed')

        n_priority_x_tasks = helpers.n_priority_x_tasks(project.id)

        assert n_priority_x_tasks == 0, n_priority_x_tasks

    @with_context
    def test_n_priority_x_tasks_all_tasks_answered_by_user(self):
        """Test n_priority_x_tasks returns 1 for user if he has
        submitted taskruns for 1 of the tasks"""
        user = UserFactory.create()
        project = ProjectFactory.create()
        task = TaskFactory.create(project=project, n_answers=2,  priority_0=0.8)
        _ = TaskRunFactory.create(task=task, user=user)

        n_priority_x_tasks = helpers.n_priority_x_tasks(project.id, 0.8)

        assert task.state != 'completed', task.state
        assert n_priority_x_tasks == 1, n_priority_x_tasks

    @with_context
    def test_n_priority_x_tasks_include_gold_task(self):
        """Test n_priority_x_tasks returns 0 for user if he has
        submitted taskruns for all the tasks"""
        project = ProjectFactory.create()
        task = TaskFactory.create(project=project, calibration=1, priority_0=0.3)

        n_priority_x_tasks_include_gold = helpers.n_priority_x_tasks(project.id, priority=0.3, include_gold_task=True)
        n_priority_x_tasks_exclude_gold = helpers.n_priority_x_tasks(project.id, priority=0.3)
        n_priority_x_tasks_include_gold_default_priority = helpers.n_priority_x_tasks(project.id,
                                                                                      include_gold_task=True)

        assert task.state != 'completed', task.state
        assert n_priority_x_tasks_include_gold == 1, n_priority_x_tasks_include_gold
        assert n_priority_x_tasks_exclude_gold == 0, n_priority_x_tasks_exclude_gold
        assert n_priority_x_tasks_include_gold_default_priority == 0, n_priority_x_tasks_include_gold_default_priority

    @with_context
    def test_order_by_args_none(self):
        """Test parse_tasks_browse_order_by_args with empty order_by."""
        order_by_result, order_by_dict = parse_tasks_browse_order_by_args(None, None)

        assert order_by_result == None
        assert order_by_dict == dict()

    @with_context
    def test_order_by_args_asc(self):
        """Test parse_tasks_browse_order_by_args with asc field."""
        order_by_result, order_by_dict = parse_tasks_browse_order_by_args('field asc', ['field'])

        assert order_by_result == "task.info->>'field' asc"
        assert 'field' in order_by_dict

    @with_context
    def test_order_by_args_desc(self):
        """Test parse_tasks_browse_order_by_args with desc field."""
        order_by_result, order_by_dict = parse_tasks_browse_order_by_args('field desc', ['field'])

        assert order_by_result == "task.info->>'field' desc"
        assert 'field' in order_by_dict

    @with_context
    def test_order_by_args_substring1(self):
        """Test parse_tasks_browse_order_by_args with substring match: companyBbid."""
        order_by_result, order_by_dict = parse_tasks_browse_order_by_args('companyBbid desc', ['bi', 'companyBbid'])

        assert order_by_result == "task.info->>'companyBbid' desc"
        assert 'companyBbid' in order_by_dict

    @with_context
    def test_order_by_args_substring2(self):
        """Test parse_tasks_browse_order_by_args with substring match: bi."""
        order_by_result, order_by_dict = parse_tasks_browse_order_by_args('bi desc', ['bi', 'companyBbid'])

        assert order_by_result == "task.info->>'bi' desc"
        assert 'bi' in order_by_dict

    @with_context
    def test_order_by_args_multiple_columns1(self):
        """Test parse_tasks_browse_order_by_args with multiple fields."""
        order_by_result, order_by_dict = parse_tasks_browse_order_by_args('bi desc, companyBbid asc', ['bi', 'companyBbid'])

        assert order_by_result == "task.info->>'bi' desc, task.info->>'companyBbid' asc"
        assert 'bi' in order_by_dict
        assert 'companyBbid' in order_by_dict

    @with_context
    def test_order_by_args_multiple_columns2(self):
        """Test parse_tasks_browse_order_by_args with multiple fields."""
        order_by_result, order_by_dict = parse_tasks_browse_order_by_args('bi desc,companyBbid asc', ['bi', 'companyBbid'])

        assert order_by_result == "task.info->>'bi' desc, task.info->>'companyBbid' asc"
        assert 'bi' in order_by_dict
        assert 'companyBbid' in order_by_dict

    @with_context
    def test_order_by_args_multiple_columns3(self):
        """Test parse_tasks_browse_order_by_args with multiple fields."""
        order_by_result, order_by_dict = parse_tasks_browse_order_by_args('bi desc, companyBbid asc, somethingElse desc', ['bi', 'companyBbid', 'somethingElse'])

        assert order_by_result == "task.info->>'bi' desc, task.info->>'companyBbid' asc, task.info->>'somethingElse' desc"
        assert 'bi' in order_by_dict
        assert 'companyBbid' in order_by_dict
        assert 'somethingElse' in order_by_dict

    @with_context
    def test_order_by_args_multiple_columns4(self):
        """Test parse_tasks_browse_order_by_args with multiple fields."""
        order_by_result, order_by_dict = parse_tasks_browse_order_by_args('bi desc,companyBbid asc,somethingElse desc', ['bi', 'companyBbid', 'somethingElse'])

        assert order_by_result == "task.info->>'bi' desc, task.info->>'companyBbid' asc, task.info->>'somethingElse' desc"
        assert 'bi' in order_by_dict
        assert 'companyBbid' in order_by_dict
        assert 'somethingElse' in order_by_dict

    @with_context
    def test_order_by_args_dict_1(self):
        """Test parse_tasks_browse_order_by_args as dict 1 field."""
        order_by_result, order_by_dict = parse_tasks_browse_order_by_args({'task_id': 'asc'}, ['bi', 'companyBbid', 'somethingElse'])

        assert order_by_result == "id asc"
        assert 'task_id' in order_by_dict

    @with_context
    def test_order_by_args_dict_2(self):
        """Test parse_tasks_browse_order_by_args as dict 2 fields."""
        order_by_result, order_by_dict = parse_tasks_browse_order_by_args({'task_id': 'asc', 'priority': 'desc'}, ['bi', 'companyBbid', 'somethingElse'])

        assert order_by_result == "id asc, priority_0 desc"
        assert 'task_id' in order_by_dict
        assert 'priority' in order_by_dict

    @with_context
    def test_user_meet_task_requirement_no_filters(self):
        """Test user_meet_task_requirement returns True when no filters are provided"""
        task_id = 1
        user_filter = {}
        user_profile = {'age': 25, 'experience': 5}

        result = user_meet_task_requirement(task_id, user_filter, user_profile)

        assert result is True

    @with_context
    def test_user_meet_task_requirement_user_profile_missing_field(self):
        """Test user_meet_task_requirement returns False when user profile missing required field"""
        task_id = 1
        user_filter = {'age': [18, '>=']}
        user_profile = {'experience': 5}  # missing 'age' field

        result = user_meet_task_requirement(task_id, user_filter, user_profile)

        assert result is False

    @with_context
    def test_user_meet_task_requirement_user_profile_field_none(self):
        """Test user_meet_task_requirement returns False when user profile field is None"""
        task_id = 1
        user_filter = {'age': [18, '>=']}
        user_profile = {'age': None, 'experience': 5}

        result = user_meet_task_requirement(task_id, user_filter, user_profile)

        assert result is False

    @with_context
    def test_user_meet_task_requirement_greater_than_pass(self):
        """Test user_meet_task_requirement returns True when user meets greater than requirement"""
        task_id = 1
        user_filter = {'age': [18, '>']}
        user_profile = {'age': 25}

        result = user_meet_task_requirement(task_id, user_filter, user_profile)

        assert result is True

    @with_context
    def test_user_meet_task_requirement_greater_than_fail(self):
        """Test user_meet_task_requirement returns False when user does not meet greater than requirement"""
        task_id = 1
        user_filter = {'age': [25, '>']}
        user_profile = {'age': 20}

        result = user_meet_task_requirement(task_id, user_filter, user_profile)

        assert result is False

    @with_context
    def test_user_meet_task_requirement_greater_than_equal_pass(self):
        """Test user_meet_task_requirement returns True when user meets greater than or equal requirement"""
        task_id = 1
        user_filter = {'age': [18, '>=']}
        user_profile = {'age': 18}

        result = user_meet_task_requirement(task_id, user_filter, user_profile)

        assert result is True

    @with_context
    def test_user_meet_task_requirement_greater_than_equal_fail(self):
        """Test user_meet_task_requirement returns False when user does not meet greater than or equal requirement"""
        task_id = 1
        user_filter = {'age': [25, '>=']}
        user_profile = {'age': 20}

        result = user_meet_task_requirement(task_id, user_filter, user_profile)

        assert result is False

    @with_context
    def test_user_meet_task_requirement_less_than_pass(self):
        """Test user_meet_task_requirement returns True when user meets less than requirement"""
        task_id = 1
        user_filter = {'age': [30, '<']}
        user_profile = {'age': 25}

        result = user_meet_task_requirement(task_id, user_filter, user_profile)

        assert result is True

    @with_context
    def test_user_meet_task_requirement_less_than_fail(self):
        """Test user_meet_task_requirement returns False when user does not meet less than requirement"""
        task_id = 1
        user_filter = {'age': [20, '<']}
        user_profile = {'age': 25}

        result = user_meet_task_requirement(task_id, user_filter, user_profile)

        assert result is False

    @with_context
    def test_user_meet_task_requirement_less_than_equal_pass(self):
        """Test user_meet_task_requirement returns True when user meets less than or equal requirement"""
        task_id = 1
        user_filter = {'age': [25, '<=']}
        user_profile = {'age': 25}

        result = user_meet_task_requirement(task_id, user_filter, user_profile)

        assert result is True

    @with_context
    def test_user_meet_task_requirement_less_than_equal_fail(self):
        """Test user_meet_task_requirement returns False when user does not meet less than or equal requirement"""
        task_id = 1
        user_filter = {'age': [20, '<=']}
        user_profile = {'age': 25}

        result = user_meet_task_requirement(task_id, user_filter, user_profile)

        assert result is False

    @with_context
    def test_user_meet_task_requirement_equal_pass(self):
        """Test user_meet_task_requirement returns True when user meets equal requirement"""
        task_id = 1
        user_filter = {'age': [25, '==']}
        user_profile = {'age': 25}

        result = user_meet_task_requirement(task_id, user_filter, user_profile)

        assert result is True

    @with_context
    def test_user_meet_task_requirement_equal_fail(self):
        """Test user_meet_task_requirement returns False when user does not meet equal requirement"""
        task_id = 1
        user_filter = {'age': [25, '==']}
        user_profile = {'age': 20}

        result = user_meet_task_requirement(task_id, user_filter, user_profile)

        assert result is False

    @with_context
    def test_user_meet_task_requirement_not_equal_pass(self):
        """Test user_meet_task_requirement returns True when user meets not equal requirement"""
        task_id = 1
        user_filter = {'age': [25, '!=']}
        user_profile = {'age': 20}

        result = user_meet_task_requirement(task_id, user_filter, user_profile)

        assert result is True

    @with_context
    def test_user_meet_task_requirement_not_equal_fail(self):
        """Test user_meet_task_requirement returns False when user does not meet not equal requirement"""
        task_id = 1
        user_filter = {'age': [25, '!=']}
        user_profile = {'age': 25}

        result = user_meet_task_requirement(task_id, user_filter, user_profile)

        assert result is False

    @with_context
    def test_user_meet_task_requirement_multiple_filters_pass(self):
        """Test user_meet_task_requirement returns True when user meets all multiple requirements"""
        task_id = 1
        user_filter = {
            'age': [18, '>='],
            'experience': [2, '>'],
            'rating': [4.0, '>=']
        }
        user_profile = {'age': 25, 'experience': 5, 'rating': 4.5}

        result = user_meet_task_requirement(task_id, user_filter, user_profile)

        assert result is True

    @with_context
    def test_user_meet_task_requirement_multiple_filters_fail_one(self):
        """Test user_meet_task_requirement returns False when user fails one of multiple requirements"""
        task_id = 1
        user_filter = {
            'age': [18, '>='],
            'experience': [2, '>'],
            'rating': [4.0, '>=']
        }
        user_profile = {'age': 25, 'experience': 1, 'rating': 4.5}  # experience too low

        result = user_meet_task_requirement(task_id, user_filter, user_profile)

        assert result is False

    @with_context
    def test_user_meet_task_requirement_string_to_float_conversion(self):
        """Test user_meet_task_requirement handles string to float conversion"""
        task_id = 1
        user_filter = {'age': [18, '>=']}
        user_profile = {'age': '25'}  # string that can be converted to float

        result = user_meet_task_requirement(task_id, user_filter, user_profile)

        assert result is True

    @with_context
    def test_user_meet_task_requirement_non_numeric_string(self):
        """Test user_meet_task_requirement handles non-numeric strings gracefully"""
        task_id = 1
        user_filter = {'skill': ['python', '==']}
        user_profile = {'skill': 'python'}  # string that cannot be converted to float

        result = user_meet_task_requirement(task_id, user_filter, user_profile)

        assert result is True

    @with_context
    def test_user_meet_task_requirement_invalid_operator(self):
        """Test user_meet_task_requirement returns False for invalid operator"""
        task_id = 1
        user_filter = {'age': [25, 'invalid_op']}
        user_profile = {'age': 25}

        result = user_meet_task_requirement(task_id, user_filter, user_profile)

        assert result is False

    @with_context
    def test_user_meet_task_requirement_alternative_operators(self):
        """Test user_meet_task_requirement works with alternative operator names"""
        task_id = 1
        user_filter = {
            'age': [18, 'greater_than_equal'],
            'experience': [5, 'less_than'],
            'rating': [3, 'equal']
        }
        user_profile = {'age': 25, 'experience': 3, 'rating': 3}

        result = user_meet_task_requirement(task_id, user_filter, user_profile)

        assert result is True

    @with_context
    def test_user_meet_task_requirement_negative_values(self):
        """Test user_meet_task_requirement handles negative values correctly"""
        task_id = 1
        user_filter = {'balance': [-100, '>']}
        user_profile = {'balance': -50}

        result = user_meet_task_requirement(task_id, user_filter, user_profile)

        assert result is True

    @with_context
    def test_user_meet_task_requirement_float_values(self):
        """Test user_meet_task_requirement handles float values correctly"""
        task_id = 1
        user_filter = {'rating': [3.5, '>=']}
        user_profile = {'rating': 4.2}

        result = user_meet_task_requirement(task_id, user_filter, user_profile)

        assert result is True

    @with_context
    def test_user_meet_task_requirement_string_value_match(self):
        """Test user_meet_task_requirement returns True when string values match exactly"""
        task_id = 1
        user_filter = {'department': ['engineering', '==']}
        user_profile = {'department': 'engineering'}

        result = user_meet_task_requirement(task_id, user_filter, user_profile)

        assert result is True

    @with_context
    def test_user_meet_task_requirement_string_value_mismatch(self):
        """Test user_meet_task_requirement returns False when string values do not match"""
        task_id = 1
        user_filter = {'department': ['engineering', '==']}
        user_profile = {'department': 'marketing'}

        result = user_meet_task_requirement(task_id, user_filter, user_profile)

        assert result is False
