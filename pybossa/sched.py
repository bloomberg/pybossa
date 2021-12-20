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
"""Scheduler module for PYBOSSA tasks."""
from functools import wraps
from sqlalchemy.sql import func, desc, text
from sqlalchemy.sql import and_, or_
from pybossa.model import DomainObject
from pybossa.model.task import Task
from pybossa.model.task_run import TaskRun
from pybossa.model.counter import Counter
from pybossa.core import db, sentinel, project_repo, task_repo
from .redis_lock import (LockManager, get_active_user_key, get_user_tasks_key,
                        get_task_users_key, get_task_id_project_id_key,
                        register_active_user, unregister_active_user,
                        get_active_user_count,
                        EXPIRE_RESERVE_TASK_LOCK_DELAY)
from .contributions_guard import ContributionsGuard
from werkzeug.exceptions import BadRequest, Forbidden
import random
import json
from pybossa.cache import users as cached_users
from pybossa.cache import task_browse_helpers as cached_task_browse_helpers
from flask import current_app
from pybossa import data_access
from datetime import datetime
import re


session = db.slave_session


class Schedulers(object):

    locked = 'locked_scheduler'
    user_pref = 'user_pref_scheduler'
    task_queue = 'task_queue_scheduler'


DEFAULT_SCHEDULER = Schedulers.locked
TIMEOUT = ContributionsGuard.STAMP_TTL


def new_task(project_id, sched, user_id=None, user_ip=None,
             external_uid=None, offset=0, limit=1, orderby='priority_0',
             desc=True, rand_within_priority=False,
             gold_only=False):
    """Get a new task by calling the appropriate scheduler function."""
    sched_map = {
        'default': get_locked_task,
        'breadth_first': get_breadth_first_task,
        'depth_first': get_depth_first_task,
        Schedulers.locked: get_locked_task,
        'incremental': get_incremental_task,
        Schedulers.user_pref: get_user_pref_task,
        'depth_first_all': get_depth_first_all_task,
        Schedulers.task_queue: get_user_pref_task
    }
    scheduler = sched_map.get(sched, sched_map['default'])
    project = project_repo.get(project_id)
    disable_gold = not project.info.get('enable_gold', True)

    task_type = 'gold_last'
    if gold_only:
        task_type = 'gold'
    elif disable_gold:
        # This is here for testing. It removes the random variable to make testing deterministic.
        task_type = 'no_gold'
    elif random.random() < project.get_gold_task_probability():
        task_type = 'gold_first'

    return scheduler(project_id,
                     user_id,
                     user_ip,
                     external_uid,
                     offset=offset,
                     limit=limit,
                     orderby=orderby,
                     desc=desc,
                     rand_within_priority=rand_within_priority,
                     filter_user_prefs=(sched in [Schedulers.user_pref, Schedulers.task_queue]),
                     task_type=task_type)


def is_locking_scheduler(sched):
    return sched in [Schedulers.locked, Schedulers.user_pref, Schedulers.task_queue, 'default']


def can_read_task(task, user):
    project_id = task.project_id
    scheduler, timeout = get_project_scheduler_and_timeout(project_id)
    if is_locking_scheduler(scheduler):
        return has_read_access(user) or has_lock(task.id, user.id,
                                                 timeout)
    else:
        return True


def can_post(project_id, task_id, user_id_or_ip):
    scheduler = get_project_scheduler(project_id, session)
    if is_locking_scheduler(scheduler):
        user_id = user_id_or_ip['user_id'] or \
                user_id_or_ip['external_uid'] or \
                user_id_or_ip['user_ip'] or \
                '127.0.0.1'
        allowed = has_lock(task_id, user_id, TIMEOUT)
        return allowed
    else:
        return True


def after_save(task_run, conn):
    scheduler = get_project_scheduler(task_run.project_id, conn)
    uid = task_run.user_id or \
          task_run.external_uid or \
          task_run.user_ip or \
          '127.0.0.1'
    if is_locking_scheduler(scheduler):
        release_lock(task_run.task_id, uid, TIMEOUT)
        release_reserve_task_lock_by_id(task_run.project_id, task_run.task_id, uid, TIMEOUT)


def get_breadth_first_task(project_id, user_id=None, user_ip=None,
                           external_uid=None, offset=0, limit=1, orderby='id',
                           desc=False, **kwargs):
    """Get a new task which have the least number of task runs."""
    project_query = session.query(Task.id).filter(Task.project_id==project_id,
                                                  Task.state!='completed',
                                                  Task.state!='enrich')
    if user_id and not user_ip and not external_uid:
        subquery = session.query(TaskRun.task_id).filter_by(project_id=project_id,
                                                            user_id=user_id)
    else:
        if not user_ip:  # pragma: no cover
            user_ip = '127.0.0.1'
        if user_ip and not external_uid:
            subquery = session.query(TaskRun.task_id).filter_by(project_id=project_id,
                                                                user_ip=user_ip)
        else:
            subquery = session.query(TaskRun.task_id).filter_by(project_id=project_id,
                                                                external_uid=external_uid)

    tmp = project_query.except_(subquery)
    query = session.query(Task, func.sum(Counter.n_task_runs).label('n_task_runs'))\
                   .filter(Task.id==Counter.task_id)\
                   .filter(Counter.task_id.in_(tmp))\
                   .filter(or_(Task.expiration == None, Task.expiration > datetime.utcnow()))\
                   .group_by(Task.id)\
                   .order_by(text('n_task_runs ASC'))\

    query = _set_orderby_desc(query, orderby, desc)
    data = query.limit(limit).offset(offset).all()
    return _handle_tuples(data)


def get_depth_first_task(project_id, user_id=None, user_ip=None,
                         external_uid=None, offset=0, limit=1,
                         orderby='priority_0', desc=True, **kwargs):
    """Get a new task for a given project."""
    tasks = get_candidate_task_ids(project_id, user_id,
                                   user_ip, external_uid, limit, offset,
                                   orderby=orderby, desc=desc)
    return tasks


def get_depth_first_all_task(project_id, user_id=None, user_ip=None,
                             external_uid=None, offset=0, limit=1,
                             orderby='priority_0', desc=True, **kwargs):
    """Get a new task for a given project."""
    tasks = get_candidate_task_ids(project_id, user_id,
                                   user_ip, external_uid, limit, offset,
                                   orderby=orderby, desc=desc, completed=False)
    return tasks


def get_incremental_task(project_id, user_id=None, user_ip=None,
                         external_uid=None, offset=0, limit=1, orderby='id',
                         desc=False, **kwargs):
    """Get a new task for a given project with its last given answer.

    It is an important strategy when dealing with large tasks, as
    transcriptions.
    """
    candidate_tasks = get_candidate_task_ids(project_id, user_id, user_ip,
                                                external_uid, limit, offset,
                                                orderby='priority_0', desc=True)
    total_remaining = len(candidate_tasks)
    if total_remaining == 0:
        return None
    rand = random.randrange(0, total_remaining)
    task = candidate_tasks[rand]
    # Find last answer for the task
    q = session.query(TaskRun)\
        .filter(TaskRun.task_id == task.id)\
        .order_by(TaskRun.finish_time.desc())
    last_task_run = q.first()
    if last_task_run:
        task.info['last_answer'] = last_task_run.info
        # TODO: As discussed in GitHub #53
        # it is necessary to create a lock in the task!
    return [task]


def get_candidate_task_ids(project_id, user_id=None, user_ip=None,
                           external_uid=None, limit=1, offset=0,
                           orderby='priority_0', desc=True, completed=True):
    """Get all available tasks for a given project and user."""
    data = None
    if user_id and not user_ip and not external_uid:
        subquery = session.query(TaskRun.task_id).filter_by(project_id=project_id, user_id=user_id)
    else:
        if not user_ip:
            user_ip = '127.0.0.1'
        if user_ip and not external_uid:
            subquery = session.query(TaskRun.task_id).filter_by(project_id=project_id, user_ip=user_ip)
        else:
            subquery = session.query(TaskRun.task_id).filter_by(project_id=project_id, external_uid=external_uid)

    query = (
        session.query(Task)
        .filter(and_(~Task.id.in_(subquery.subquery()),
                    Task.project_id == project_id,
                    Task.state != 'completed',
                    Task.state != 'enrich'))
        .filter(or_(Task.expiration == None, Task.expiration > datetime.utcnow()))

        if completed else # completed means filter out completed

        session.query(Task)
        .filter(and_(
            ~Task.id.in_(subquery.subquery()),
            Task.project_id == project_id,
            Task.state != 'enrich'
        ))
    )

    query = _set_orderby_desc(query, orderby, desc)
    data = query.limit(limit).offset(offset).all()
    return _handle_tuples(data)


def locked_scheduler(query_factory):
    @wraps(query_factory)
    def template_get_locked_task(project_id, user_id=None, user_ip=None,
                                 external_uid=None, limit=1, offset=0,
                                 orderby='priority_0', desc=True,
                                 rand_within_priority=False, task_type='gold_last',
                                 filter_user_prefs=False,
                                 task_category_filters=""):
        if offset > 2:
            raise BadRequest('')
        if offset > 0:
            return None
        project = project_repo.get(project_id)
        timeout = project.info.get('timeout', TIMEOUT)
        task_queue_scheduler = project.info.get("sched", "default") in [Schedulers.task_queue]
        reserve_task_config = project.info.get("reserve_tasks", {}).get("category", [])
        task_id, lock_seconds = get_task_id_and_duration_for_project_user(project_id, user_id)
        if lock_seconds > 10:
            task = session.query(Task).get(task_id)
            if task:
                return [task]
        task_id = None
        user_count = get_active_user_count(project_id, sentinel.master)
        assign_user = json.dumps({'assign_user': [cached_users.get_user_email(user_id)]}) if user_id else None
        current_app.logger.info(
            "Project {} - number of current users: {}"
            .format(project_id, user_count))

        sql_filters, exclude_user = "", False
        if task_queue_scheduler and reserve_task_config:
            sql_filters, category_keys = get_reserve_task_category_info(reserve_task_config, project_id, timeout, user_id)
            if not category_keys:
                # no category reserved by current user. search categories
                # excluding the ones reserved by other users
                current_app.logger.info(
                    "Project %s, user %s, %s", project_id, user_id,
                    "No task category reserved by user. Search tasks excuding categories reserved by other users"
                )
                exclude_user = True
                sql_filters, category_keys = get_reserve_task_category_info(
                    reserve_task_config, project_id, timeout, user_id, exclude_user
                )
                current_app.logger.info("SQL filter excuding task categories reserved by other users. sql filter %s", sql_filters)

        limit = current_app.config.get('DB_MAXIMUM_BATCH_SIZE') if filter_user_prefs else user_count + 5
        sql = query_factory(project_id, user_id=user_id, limit=limit,
                            rand_within_priority=rand_within_priority,
                            task_type=task_type, task_category_filters=sql_filters)
        rows = session.execute(sql, dict(project_id=project_id,
                                         user_id=user_id,
                                         assign_user=assign_user,
                                         limit=limit))

        if task_queue_scheduler and reserve_task_config and rows and not rows.rowcount and not exclude_user:
            # With task category reserved by user and no records returned,
            # no ongoing tasks with task category reserved by user exist.
            # Hence, query db for tasks excluding task categories reserved
            # by other users passing exclude_users = True
            current_app.logger.info(
                "Project %s, user %s, %s", project_id, user_id,
                "No task exist with task category already reserved by user. Search tasks excuding categories reserved by other users"
            )
            exclude_user = True
            release_reserve_task_lock_by_keys(category_keys, timeout)
            sql_filters, category_keys = get_reserve_task_category_info(
                reserve_task_config, project_id, timeout, user_id, exclude_user
            )
            current_app.logger.info("SQL filter excuding task categories reserved by other users. sql filter %s", sql_filters)
            sql = query_factory(project_id, user_id=user_id, limit=limit,
                            rand_within_priority=rand_within_priority,
                            task_type=task_type, task_category_filters=sql_filters)
            rows = session.execute(sql, dict(project_id=project_id,
                                            user_id=user_id,
                                            assign_user=assign_user,
                                            limit=limit))

        user_profile = cached_users.get_user_profile_metadata(user_id)

        if filter_user_prefs:
            # validate user qualification and calculate task preference score
            user_profile = json.loads(user_profile) if user_profile else {}
            task_rank_info = []
            for task_id, taskcount, n_answers, calibration, w_filter, w_pref, timeout in rows:
                w_pref = w_pref or {}
                w_filter = w_filter or {}
                meet_requirement = cached_task_browse_helpers.user_meet_task_requirement(task_id, w_filter, user_profile)
                if meet_requirement:
                    score = cached_task_browse_helpers.get_task_preference_score(w_pref, user_profile)
                    task_rank_info.append((task_id, taskcount, n_answers, calibration, score, None, timeout))
            rows = sorted(task_rank_info, key=lambda tup: tup[4], reverse=True)
        else:
            rows = [r for r in rows]

        for task_id, taskcount, n_answers, calibration, _, _, timeout in rows:
            timeout = timeout or TIMEOUT
            remaining = float('inf') if calibration else n_answers - taskcount
            if acquire_lock(task_id, user_id, remaining, timeout):
                # reserve tasks
                acquire_reserve_task_lock(project_id, task_id, user_id, timeout)
                return _lock_task_for_user(task_id, project_id, user_id, timeout, calibration)
        return []

    return template_get_locked_task



def reserve_task_sql_filters(project_id, reserve_task_keys, exclude):
    # build sql query filter from task category cache key
    # return sql filter for matching task category keys and list of
    # task category keys that qualifies for a given project_id

    filters, category_keys = "", []

    if not (project_id and len(reserve_task_keys)):
        return filters, category_keys

    # convert task category redis cache key to sql query
    # ex "co:name:IBM:ticker:IBM_US" would be converted to
    # "task.info->>'co_name' IN ('IBM')"
    filters_dict = {}
    current_app.logger.info("Project %s, exclude %s. Build sql filter from reserver task keys", project_id, exclude)
    current_app.logger.info("reserve tasks keys: %s", json.dumps(reserve_task_keys))
    regex_key = "reserve_task:project:{}:category:(.+?):user".format(project_id)
    for item in reserve_task_keys:
        data = re.search(regex_key, item)
        if not data:
            continue

        category_keys += [item]
        category = data.group(1)
        category_fv = category.split(":")
        for i in range(0, len(category_fv), 2):
            key, value = category_fv[i], category_fv[i + 1]
            if key in filters_dict:
                if value not in filters_dict[key]:
                    filters_dict[key] += [value]
            else:
                filters_dict[key] = [value]

    # TODO: pull task # from category keys, look for values from task._add_user_info
    # generate sql_filter considering value field type instead.
    data = []
    for key, value in filters_dict.items():
        val = ["'{}'".format(val) for val in value]
        data += ["task.info->>'{}' IN ({})".format(key, ", ".join(val))]
    if not data:
        current_app.logger.info("sql filter %s, reserve keys %s", filters, json.dumps(category_keys))
        return filters, category_keys

    exclude_clause = "IS NOT TRUE" if exclude else ""
    filters = "({}) {}".format(" AND ".join(data), exclude_clause)
    filters = " AND {}".format(filters) if filters else filters
    current_app.logger.info("sql filter %s, reserve keys %s", filters, json.dumps(category_keys))
    return filters, category_keys


def get_reserve_task_key(task_id):
    reserve_key = ""
    task = task_repo.get_task(task_id)
    if not task:
        return reserve_key

    project = project_repo.get(task.project_id)
    if not (project and project.info.get("sched", "default") in [Schedulers.task_queue]):
        return reserve_key

    reserve_task_config = project.info.get("reserve_tasks", {}).get("category", [])
    if not reserve_task_config:
        return reserve_key

    if not all(field in task.info for field in reserve_task_config):
        return reserve_key

    reserve_key = ":".join(["{}:{}".format(field, task.info[field]) for field in sorted(reserve_task_config)])
    return reserve_key


def get_reserve_task_category_info(reserve_task_config, project_id, timeout, user_id, exclude_user=False):
    """Get reserved category info for a given user under a given project"""
    sql_filters, category_keys = "", []

    if not reserve_task_config:
        return sql_filters, category_keys

    category = ":".join(["{}:*".format(field) for field in sorted(reserve_task_config)])
    lock_manager = LockManager(sentinel.master, timeout)
    category_keys = lock_manager.get_task_category_lock(project_id, user_id, category, exclude_user)
    current_app.logger.info(
        "Project %s, user %s, reserve config %s, exclude %s. reserve task category keys %s",
        project_id, user_id, json.dumps(reserve_task_config), exclude_user, str(category_keys)
    )
    if not category_keys:
        return sql_filters, category_keys

    sql_filters, category_keys = reserve_task_sql_filters(project_id, category_keys, exclude_user)
    return sql_filters, category_keys


def locked_task_sql(project_id, user_id=None, limit=1, rand_within_priority=False,
                    task_type='gold_last', filter_user_prefs=False,
                    priority_sort=True, task_category_filters=""):
    '''
    `task_type` will affect the type of tasks return by the query and can be one
    one of the following values:
        gold ->         only gold tasks will be returned
        no_gold ->      only non-gold tasks will be returned
        gold_last ->    non-gold tasks will be returned before gold tasks. (Default)
        gold_first ->   gold tasks will be returned before non-gold tasks.
    '''
    filters = []
    if filter_user_prefs:
        filters.append('AND ({}) AND ({})'.format(cached_users.get_user_preferences(user_id), cached_users.get_user_filters(user_id)))
    if task_type == 'gold':
        filters.append('AND task.calibration = 1')
    elif task_type == 'no_gold':
        filters.append('AND task.calibration != 1')

    order_by = []
    if task_type == 'gold_last':
        order_by.append('task.calibration')
    elif task_type == 'gold_first':
        order_by.append('task.calibration DESC NULLS LAST')
    if priority_sort:
        order_by.append('priority_0 DESC')
    if rand_within_priority:
        order_by.append('random()')
    else:
        order_by.append('id ASC')

    sql = '''
           SELECT task.id, COUNT(task_run.task_id) AS taskcount, n_answers, task.calibration,
           worker_filter, worker_pref,
              (SELECT info->'timeout'
               FROM project
               WHERE id=:project_id) as timeout
           FROM task
           LEFT JOIN task_run ON (task.id = task_run.task_id)
           WHERE NOT EXISTS
           (SELECT 1 FROM task_run WHERE project_id=:project_id AND
           user_id=:user_id AND task_id=task.id)
           AND task.project_id=:project_id
           AND ((task.expiration IS NULL) OR (task.expiration > (now() at time zone 'utc')::timestamp))
           AND task.state !='completed'
           AND task.state !='enrich'
           {}
           {}
           group by task.id
           ORDER BY {}
           LIMIT :limit;
           '''.format(' '.join(filters), task_category_filters,
                      ','.join(order_by))
    print(sql)
    return text(sql)


def select_contributable_task(project, user_id, **kwargs):
    sched, _ = get_scheduler_and_timeout(project)
    with_user_pref = sched in [Schedulers.user_pref, Schedulers.task_queue]
    kwargs['filter_user_prefs'] = with_user_pref

    params = dict(project_id=project.id, user_id=user_id, limit=1)
    if with_user_pref:
        params['assign_user'] = None

    sql = locked_task_sql(project.id, user_id, **kwargs)
    rows = session.execute(sql, params)
    for row in rows:
        return task_repo.get_task(row.id)
    return {}


def select_task_for_gold_mode(project, user_id):
    return select_contributable_task(project, user_id,
        rand_within_priority=True, task_type='no_gold', priority_sort=False)


@locked_scheduler
def get_locked_task(project_id, user_id=None, limit=1, rand_within_priority=False,
                    task_type='gold_last', task_category_filters=""):
    return locked_task_sql(project_id, user_id=user_id, limit=limit,
                           rand_within_priority=rand_within_priority, task_type=task_type,
                           filter_user_prefs=False, task_category_filters=task_category_filters)


@locked_scheduler
def get_user_pref_task(project_id, user_id=None, limit=1, rand_within_priority=False,
                       task_type='gold_last', filter_user_prefs=True, task_category_filters=""):
    """ Select a new task based on user preference set under user profile.

    For each incomplete task, check if the number of users working on the task
    is smaller than the number of answers still needed. In that case, acquire
    a lock on the task that matches user preference(if any) with users profile
    and return the task to the user. If offset is nonzero, skip that amount of
    available tasks before returning to the user.
    """
    return locked_task_sql(project_id, user_id=user_id, limit=limit,
                           rand_within_priority=rand_within_priority, task_type=task_type,
                           filter_user_prefs=True, task_category_filters=task_category_filters)


TASK_USERS_KEY_PREFIX = 'pybossa:project:task_requested:timestamps:{0}'
USER_TASKS_KEY_PREFIX = 'pybossa:user:task_acquired:timestamps:{0}'
TASK_ID_PROJECT_ID_KEY_PREFIX = 'pybossa:task_id:project_id:{0}'
TIMEOUT = ContributionsGuard.STAMP_TTL


def has_lock(task_id, user_id, timeout):
    lock_manager = LockManager(sentinel.master, timeout)
    task_users_key = get_task_users_key(task_id)
    return lock_manager.has_lock(task_users_key, user_id)


def acquire_lock(task_id, user_id, limit, timeout, pipeline=None, execute=True):
    redis_conn = sentinel.master
    pipeline = pipeline or redis_conn.pipeline(transaction=True)
    lock_manager = LockManager(redis_conn, timeout)
    task_users_key = get_task_users_key(task_id)
    user_tasks_key = get_user_tasks_key(user_id)
    if lock_manager.acquire_lock(task_users_key, user_id, limit, pipeline=pipeline):
        lock_manager.acquire_lock(user_tasks_key, task_id, float('inf'), pipeline=pipeline)
        if execute:
            return all(not isinstance(r, Exception) for r in pipeline.execute())
        return True
    return False


def release_reserve_task_lock_by_id(project_id, task_id, user_id, timeout, expiry=EXPIRE_RESERVE_TASK_LOCK_DELAY):
    reserve_key = get_reserve_task_key(task_id)
    if not reserve_key:
        return

    redis_conn = sentinel.master
    lock_manager = LockManager(redis_conn, timeout)
    resource_id = "reserve_task:project:{}:category:{}:user:{}:task:{}".format(
        project_id, reserve_key, user_id, task_id)
    lock_manager.release_reserve_task_lock(resource_id, expiry)
    current_app.logger.info(
        "Release reserve task lock. project %s, task %s, user %s, expiry %d",
        project_id, task_id, user_id, expiry
    )


def release_reserve_task_lock_by_keys(resource_ids, timeout, pipeline=None, expiry=EXPIRE_RESERVE_TASK_LOCK_DELAY):
    if not resource_ids:
        return

    redis_conn = sentinel.master
    lock_manager = LockManager(redis_conn, timeout)
    for resource_id in resource_ids:
        lock_manager.release_reserve_task_lock(resource_id, expiry)
        current_app.logger.info(
        "Release reserve task lock. resource id %s, expiry %d", resource_id, expiry)


def acquire_reserve_task_lock(project_id, task_id, user_id, timeout, pipeline=None, execute=True):
    task = task_repo.get_task(task_id)
    project = project_repo.get(project_id)
    if not (task and project and project.info.get("sched", "default") in [Schedulers.task_queue]):
        return False

    reserve_task_config = project.info.get("reserve_tasks", {}).get("category", [])
    category_exist = reserve_task_config and all(task.info.get(field, False) for field in reserve_task_config)
    if not category_exist:
        return False

    category = ["{}:{}".format(field, task.info.get(field)) for field in reserve_task_config]
    category = ":".join(category)
    redis_conn = sentinel.master
    pipeline = pipeline or redis_conn.pipeline(transaction=True)
    lock_manager = LockManager(redis_conn, timeout)
    if lock_manager.acquire_reserve_task_lock(project_id, task_id, user_id, category):
        current_app.logger.info(
            "Acquired reserve task lock. project %s, task %s, user %s, category %s",
            project_id, task_id, user_id, category
        )
        return True
    return False


def lock_task_for_user(task_id, project_id, user_id):
    sql = '''
        SELECT task.id, COUNT(task_run.task_id) AS taskcount, n_answers, task.calibration,
            (SELECT info->'timeout'
            FROM project
            WHERE id=:project_id) as timeout
        FROM task
        LEFT JOIN task_run ON (task.id = task_run.task_id)
        WHERE NOT EXISTS
        (SELECT 1 FROM task_run WHERE project_id=:project_id AND
        user_id=:user_id AND task_id=task.id)
        AND task.project_id=:project_id
        AND task.id = :task_id
        AND ((task.expiration IS NULL) OR (task.expiration > (now() at time zone 'utc')::timestamp))
        AND task.state !='completed'
        AND task.state !='enrich'
        group by task.id
        '''

    rows = session.execute(sql, dict(project_id=project_id,
                                    user_id=user_id,
                                    task_id=task_id))
    for task_id, taskcount, n_answers, calibration, timeout in rows:
        timeout = timeout or TIMEOUT
        remaining = float('inf') if calibration else n_answers - taskcount
        if acquire_lock(task_id, user_id, remaining, timeout):
            return _lock_task_for_user(task_id, project_id, user_id, timeout, calibration)


def _lock_task_for_user(task_id, project_id, user_id, timeout, calibration=False):
    save_task_id_project_id(task_id, project_id, 2 * timeout)
    register_active_user(project_id, user_id, sentinel.master, ttl=timeout)

    task_type = 'gold task' if calibration else 'task'
    current_app.logger.info(
        'Project {} - user {} obtained {} {}, timeout: {}'
        .format(project_id, user_id, task_type, task_id, timeout))
    return [session.query(Task).get(task_id)]


def release_user_locks_for_project(user_id, project_id):
    user_tasks = get_user_tasks(user_id, TIMEOUT)
    user_task_ids = list(user_tasks.keys())
    results = get_task_ids_project_id(user_task_ids)
    task_ids = []
    for task_id, task_project_id in zip(user_task_ids, results):
        if not task_project_id:
            task_project_id = task_repo.get_task(task_id).project_id
        if int(task_project_id) == project_id:
            release_lock(task_id, user_id, TIMEOUT)
            task_ids.append(task_id)
    current_app.logger.info('released user id {} locks on tasks {}'.format(user_id, task_ids))
    return task_ids


def release_lock(task_id, user_id, timeout, pipeline=None, execute=True):
    redis_conn = sentinel.master
    pipeline = pipeline or redis_conn.pipeline(transaction=True)
    lock_manager = LockManager(redis_conn, timeout)
    task_users_key = get_task_users_key(task_id)
    user_tasks_key = get_user_tasks_key(user_id)
    lock_manager.release_lock(task_users_key, user_id, pipeline=pipeline)
    lock_manager.release_lock(user_tasks_key, task_id, pipeline=pipeline)

    project_ids = get_task_ids_project_id([task_id])
    remaining_user_tasks_id = [t for t in get_user_tasks(user_id, timeout).keys() if t != str(task_id)]
    if project_ids:
        if project_ids[0] not in get_task_ids_project_id(remaining_user_tasks_id):
            unregister_active_user(project_ids[0], user_id, sentinel.master)

    if execute:
        pipeline.execute()


def get_locks(task_id, timeout):
    lock_manager = LockManager(sentinel.master, timeout)
    task_users_key = get_task_users_key(task_id)
    return lock_manager.get_locks(task_users_key)


def get_user_tasks(user_id, timeout):
    lock_manager = LockManager(sentinel.master, timeout)
    user_tasks_key = get_user_tasks_key(user_id)
    return lock_manager.get_locks(user_tasks_key)


def save_task_id_project_id(task_id, project_id, timeout):
    task_id_project_id_key = get_task_id_project_id_key(task_id)
    sentinel.master.setex(task_id_project_id_key, timeout, project_id)


def get_task_ids_project_id(task_ids):
    keys = [get_task_id_project_id_key(t) for t in task_ids]
    if keys:
        return sentinel.master.mget(keys)
    return []


def get_task_users_key(task_id):
    # bytes to unicode string
    if type(task_id) == bytes:
        task_id = task_id.decode()
    return TASK_USERS_KEY_PREFIX.format(task_id)


def get_user_tasks_key(user_id):
    # bytes to unicode string
    if type(user_id) == bytes:
        user_id = user_id.decode()
    return USER_TASKS_KEY_PREFIX.format(user_id)

def get_locked_tasks_project(project_id):
    """Returns a list of locked tasks for a given project."""
    tasks = []
    redis_conn = sentinel.master

    # Get the active users key for this project.
    key = get_active_user_key(project_id)

    # Get the users for each locked task.
    for user_key in redis_conn.hgetall(key).items():
        user_id = user_key[0]
        # Data from Redis is bytes, thus convert it to unicode string
        if type(user_id) == bytes:
            user_id = user_id.decode()

        # Get locks by user.
        user_tasks = get_user_tasks(user_id, TIMEOUT)
        # Get task ids for the locks.
        user_task_ids = list(user_tasks.keys())
        # Get project ids for the task ids.
        results = get_task_ids_project_id(user_task_ids)
        # For each locked task, check if the lock is still active.
        for task_id, task_project_id in zip(user_task_ids, results):
            # Match the requested project id.
            if int(task_project_id) == project_id:
                # Calculate seconds remaining.
                seconds_remaining = LockManager.seconds_remaining(user_tasks[task_id])
                if seconds_remaining > 0:
                    # This lock has not yet expired.
                    tasks.append({
                        "user_id": user_id,
                        "task_id": task_id,
                        "seconds_remaining": seconds_remaining
                    })
    return tasks


def get_task_id_and_duration_for_project_user(project_id, user_id):
    """Returns the max seconds remaining locked task for a user and project."""
    user_tasks = get_user_tasks(user_id, TIMEOUT)
    user_task_ids = list(user_tasks.keys())
    results = get_task_ids_project_id(user_task_ids)
    max_seconds_task_id = -1
    max_seconds_remaining = float('-inf')
    for task_id, task_project_id in zip(user_task_ids, results):
        if not task_project_id:
            task_project_id = task_repo.get_task(task_id).project_id
            save_task_id_project_id(task_id, task_project_id, 2 * TIMEOUT)
        if int(task_project_id) == project_id:
            seconds_remaining = LockManager.seconds_remaining(user_tasks[task_id])
            if seconds_remaining > max_seconds_remaining:
                max_seconds_task_id = int(task_id)
                max_seconds_remaining = seconds_remaining
    if max_seconds_task_id > 0:
        return max_seconds_task_id, max_seconds_remaining
    return None, -1


def release_user_locks(user_id):
    redis_conn = sentinel.master
    pipeline = redis_conn.pipeline(transaction=True)
    for key in get_user_tasks(user_id, TIMEOUT).keys():
        release_lock(key, user_id, TIMEOUT, pipeline=pipeline, execute=False)
    pipeline.execute()


def get_project_scheduler_and_timeout(project_id):
    project = project_repo.get(project_id)
    if not project:
        raise Forbidden('Invalid project_id')
    return get_scheduler_and_timeout(project)


def get_scheduler_and_timeout(project):
    scheduler = project.info.get('sched', 'default')
    timeout = project.info.get('timeout', TIMEOUT)
    if scheduler == 'default':
        scheduler = DEFAULT_SCHEDULER
    return scheduler, timeout


def has_read_access(user):
    return not user.is_anonymous and (user.admin or user.subadmin)


def get_project_scheduler(project_id, conn):
    sql = text('''
        SELECT info->>'sched' as sched FROM project WHERE id=:project_id;
        ''')
    row = conn.execute(sql, dict(project_id=project_id)).first()
    if not row:
        return 'default'
    return row.sched or 'default'


def sched_variants():
    return [('default', 'Default'), ('breadth_first', 'Breadth First'),
            ('depth_first', 'Depth First'),
            (Schedulers.locked, 'Locked'),
            (Schedulers.user_pref, 'User Preference Scheduler'),
            ('depth_first_all', 'Depth First All'),
            (Schedulers.task_queue, 'Task Queues')
            ]


def randomizable_scheds():
    scheds = [Schedulers.locked, Schedulers.user_pref]
    if DEFAULT_SCHEDULER in scheds:
        scheds.append('default')
    return scheds


def _set_orderby_desc(query, orderby, descending):
    """Set order by to query."""
    if orderby == 'fav_user_ids':
        n_favs = func.coalesce(func.array_length(Task.fav_user_ids, 1), 0).label('n_favs')
        query = query.add_column(n_favs)
        if descending:
            query = query.order_by(desc("n_favs"))
        else:
            query = query.order_by("n_favs")
    else:
        if descending:
            query = query.order_by(getattr(Task, orderby).desc())
        else:
            query = query.order_by(getattr(Task, orderby).asc())
    query = query.order_by(Task.id.asc())
    return query


def _handle_tuples(data):
    """Handle tuples when query returns several columns."""
    tmp = []
    for datum in data:
        if isinstance(datum, DomainObject):
            tmp.append(datum)
        else:
            tmp.append(datum[0])
    return tmp
