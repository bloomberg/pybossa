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
"""Cache module with helper functions."""

import json
from flask import current_app
from sqlalchemy.sql import text
from pybossa.core import db
from pybossa.cache import memoize, ONE_HOUR
from pybossa.model.project_stats import ProjectStats
from pybossa.cache import users as cached_users
from pybossa.cache import task_browse_helpers as cached_task_browse_helpers
from pybossa.sched import Schedulers, get_reserve_task_category_info
from pybossa.contributions_guard import ContributionsGuard

session = db.slave_session
TIMEOUT = ContributionsGuard.STAMP_TTL
def n_gold_tasks(project_id):
    """Return the number of gold tasks for a given project"""
    query = text('''SELECT COUNT(*) AS n_gold_tasks FROM task
                    WHERE project_id=:project_id
                    AND state !='enrich'
                    AND calibration = 1;''')
    result = session.execute(query, dict(project_id=project_id))
    num_gold_tasks = 0
    for row in result:
        num_gold_tasks = row.n_gold_tasks
    return num_gold_tasks


def n_available_tasks(project_id, include_gold_task=False):
    """Return the number of tasks for a given project a user can contribute to.
    based on the completion of the project tasks,
    """
    if include_gold_task:
        query = text('''SELECT COUNT(*) AS n_tasks FROM task
                        WHERE project_id=:project_id AND state !='completed'
                        AND state !='enrich';''')
    else:
        query = text('''SELECT COUNT(*) AS n_tasks FROM task
                        WHERE project_id=:project_id AND state !='completed'
                        AND state !='enrich'
                        AND calibration = 0;''')
    result = session.execute(query, dict(project_id=project_id))
    n_tasks = 0
    for row in result:
        n_tasks = row.n_tasks
    return n_tasks


def oldest_available_task(project_id, user_id, user_ip=None):
    """Return the timestamp of the oldest task with the highest priority that a user can contribute to.
    """
    if user_id and not user_ip:
        query = text('''SELECT created FROM task
                        WHERE project_id=:project_id AND state !='completed'
                        AND state !='enrich'
                        AND id NOT IN
                        (SELECT task_id FROM task_run WHERE
                        project_id=:project_id AND user_id=:user_id)
                        ORDER BY priority_0 DESC, created ASC LIMIT 1;''')
        return session.scalar(query, dict(project_id=project_id,
                                             user_id=user_id))
    else:
        # Anonymous access isn't supported, therefore the else statement will never execute. Maybe in the future?
        if not user_ip:
            user_ip = '127.0.0.1'
        query = text('''SELECT created FROM task
                        WHERE project_id=:project_id AND state !='completed'
                        AND state !='enrich'
                        AND id NOT IN
                        (SELECT task_id FROM task_run WHERE
                        project_id=:project_id AND user_ip=:user_ip)
                        ORDER BY priority_0 DESC, created ASC LIMIT 1;''')

        return session.scalar(query, dict(project_id=project_id,
                                             user_ip=user_ip))


def n_completed_tasks_by_user(project_id, user_id):
    """Return number of completed tasks of a project."""
    sql = text('''SELECT COUNT(task_run.id) FROM task_run
                WHERE task_run.project_id=:project_id AND task_run.user_id=:user_id;
                ''')

    return session.scalar(sql, dict(project_id=project_id, user_id=user_id)) or 0


def check_contributing_state(project, user_id=None, user_ip=None,
                             external_uid=None, ps=None):
    """Return the state of a given project for a given user.

    Depending on whether the project is completed or not and the user can
    contribute more to it or not.
    """
    project_id = project['id'] if type(project) == dict else project.id
    published = project['published'] if type(project) == dict else project.published
    states = ('completed', 'draft', 'publish', 'can_contribute', 'cannot_contribute')
    if ps is None:
        ps = session.query(ProjectStats)\
                    .filter_by(project_id=project_id).first()
    if ps.overall_progress >= 100:
        return states[0]
    if not published:
        if has_no_presenter(project) or _has_no_tasks(project_id):
            return states[1]
        return states[2]
    if n_available_tasks_for_user(project, user_id=user_id) > 0:
        return states[3]
    return states[4]


def add_custom_contrib_button_to(project, user_id_or_ip, ps=None):
    """Add a customized contrib button for a project."""
    if type(project) != dict:
        project = project.dictize()
    project['contrib_button'] = check_contributing_state(project,
                                                         ps=ps,
                                                         **user_id_or_ip)

    project['enable_task_queue'] = (project['info'].get('sched', "default") == Schedulers.task_queue)
    if ps is None:
        ps = session.query(ProjectStats)\
                    .filter_by(project_id=project['id']).first()

    project['n_blogposts'] = ps.n_blogposts
    project['n_results'] = ps.n_results
    project['n_tasks'] = ps.n_tasks

    return project


def has_no_presenter(project):
    """Return if a project has no presenter."""
    if current_app.config.get('DISABLE_TASK_PRESENTER'):
        return False
    else:
        empty_presenters = ('', None)
        try:
            return not project.has_presenter()
        except AttributeError:
            try:
                return (project.get('info').get('task_presenter') in
                        empty_presenters)
            except AttributeError:
                return True


def _has_no_tasks(project_id):
    """Return if a project has no tasks."""
    query = text('''SELECT COUNT(id) AS n_tasks FROM task
               WHERE project_id=:project_id;''')
    result = session.execute(query, dict(project_id=project_id))
    for row in result:
        n_tasks = row.n_tasks
    return n_tasks == 0


def n_available_tasks_for_user(project, user_id=None, user_ip=None):
    """Return the number of tasks for a given project a user can contribute to.
    based on the completion of the project tasks, previous task_runs
    submitted by the user and user preference set under user profile.
    """
    from pybossa.sched import Schedulers

    n_tasks = 0
    if user_id is None or user_id <= 0:
        return n_tasks
    assign_user = json.dumps({'assign_user': [cached_users.get_user_email(user_id)]}) if user_id else None
    project_info = project["info"] if type(project) == dict else project.info
    scheduler = project_info.get('sched', 'default')
    project_id = project['id'] if type(project) == dict else project.id
    if scheduler not in [Schedulers.user_pref, Schedulers.task_queue]:
        sql = '''
               SELECT COUNT(*) AS n_tasks FROM task
               WHERE project_id=:project_id AND state !='completed'
               AND state !='enrich'
               AND id NOT IN
               (SELECT task_id FROM task_run WHERE
               project_id=:project_id AND user_id=:user_id)
               ; '''
    else:
        user_pref_list = cached_users.get_user_preferences(user_id)
        user_filter_list = cached_users.get_user_filters(user_id)
        reserve_task_config = project_info.get("reserve_tasks", {}).get("category", [])
        timeout = project_info.get("timeout", TIMEOUT)
        reserve_task_filter, _ = get_reserve_task_category_info(reserve_task_config, project_id, timeout, user_id, True)
        sql = '''
               SELECT task.id, worker_filter FROM task
               WHERE project_id=:project_id AND state !='completed'
               AND state !='enrich'
               {}
               AND id NOT IN
               (SELECT task_id FROM task_run WHERE
               project_id=:project_id AND user_id=:user_id)
               AND ({})
               AND ({})
               ;'''.format(reserve_task_filter, user_pref_list, user_filter_list)
    sqltext = text(sql)
    try:
        result = session.execute(sqltext, dict(project_id=project_id, user_id=user_id, assign_user=assign_user))
        if scheduler not in [Schedulers.user_pref, Schedulers.task_queue]:
            for row in result:
                n_tasks = row.n_tasks
                return n_tasks
        else:
            num_available_tasks = 0
            user_profile = cached_users.get_user_profile_metadata(user_id)
            user_profile = json.loads(user_profile) if user_profile else {}
            for task_id, w_filter in result:
                w_filter = w_filter or {}
                num_available_tasks += int(
                    cached_task_browse_helpers.user_meet_task_requirement(task_id, w_filter, user_profile)
                )
            return num_available_tasks

    except Exception as e:
        current_app.logger.exception('Exception in get_user_pref_task {0}, sql: {1}'.format(str(e), str(sqltext)))
        return None


def latest_submission_task_date(project_id):
    """Return date of the last completed task."""
    sql = text('''SELECT MAX(finish_time) FROM task_run
                WHERE project_id=:project_id;''')
    return session.scalar(sql, dict(project_id=project_id))


def n_unexpired_gold_tasks(project_id):
    query = text('''
        SELECT COUNT(id) AS n_tasks FROM task
        WHERE project_id=:project_id
        AND calibration = 1
        AND ((expiration IS NULL) OR (expiration > (now() at time zone 'utc')::timestamp))
    ''')
    result = session.execute(query, dict(project_id=project_id))
    return result.scalar()

def n_priority_x_tasks(project_id, priority=1.0, include_gold_task=False):
    """Return the number of ongoing tasks with a given priority for a given project."""
    if include_gold_task:
        query = text('''SELECT COUNT(*) AS n_tasks FROM task
                        WHERE project_id=:project_id AND state = 'ongoing'
                        AND priority_0=:priority;''')
    else:
        query = text('''SELECT COUNT(*) AS n_tasks FROM task
                        WHERE project_id=:project_id AND state = 'ongoing'
                        AND calibration = 0 AND priority_0=:priority;''')
    result = session.execute(query, dict(project_id=project_id, priority=priority))
    n_tasks = 0
    for row in result:
        n_tasks = row.n_tasks
    return n_tasks
