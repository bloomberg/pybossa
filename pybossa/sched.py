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
import sys
from functools import wraps
from sqlalchemy.sql import func, desc, text
from sqlalchemy.sql import and_, or_
from pybossa.model import DomainObject
from pybossa.model.task import Task
from pybossa.model.task_run import TaskRun
from pybossa.core import db, sentinel, project_repo, task_repo
from .redis_lock import (LockManager, get_active_user_key, get_user_tasks_key,
                         get_task_users_key, get_task_id_project_id_key,
                         register_active_user, unregister_active_user,
                         get_active_user_count,
                         EXPIRE_RESERVE_TASK_LOCK_DELAY, EXPIRE_LOCK_DELAY)
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

from pybossa.util import SavedTaskPositionEnum, get_user_saved_partial_tasks

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
             gold_only=False, task_id=None, saved_task_position=None):
    """Get a new task by calling the appropriate scheduler function."""
    sched_map = {
        'default': get_locked_task,
        Schedulers.locked: get_locked_task,
        Schedulers.user_pref: get_user_pref_task,
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
                     task_type=task_type,
                     task_id=task_id if sched in [Schedulers.task_queue] else None,
                     saved_task_position=saved_task_position)


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


def locked_scheduler(query_factory):
    @wraps(query_factory)
    def template_get_locked_task(project_id, user_id=None, user_ip=None,
                                 external_uid=None, limit=1, offset=0,
                                 orderby='priority_0', desc=True,
                                 rand_within_priority=False, task_type='gold_last',
                                 filter_user_prefs=False,
                                 task_category_filters="",
                                 task_id=None,
                                 saved_task_position=None):
        if task_id:
            task = session.query(Task).get(task_id)
            # The task must belong to the project in the URL. Without this the
            # branch fetches by primary key alone and returns the task before
            # any lock, redundancy or worker-filter check, so any project the
            # caller can reach acts as a conduit to read tasks from projects
            # they have no membership in. Task ids are sequential.
            # str() on both sides: project_id reaches here as an int from
            # sched.new_task(project.id, ...), but the route declares
            # <project_id> with no converter, so a future caller could pass the
            # raw string. A bare != would then reject every legitimate
            # cherry-pick.
            if task and str(task.project_id) != str(project_id):
                current_app.logger.warning(
                    "locked_scheduler. Project %s, User %s - task_id %s belongs to project %s. Refusing.",
                    project_id, user_id, task_id, task.project_id
                )
                task = None
            if task:
                current_app.logger.info(
                    "locked_scheduler. Project %s, User %s - task_id %s requested directly.",
                    project_id, user_id, task_id
                )
                return [task]

        if offset > 2:
            raise BadRequest('')
        if offset > 0:
            return None
        project = project_repo.get(project_id)
        timeout = project.info.get('timeout', TIMEOUT)
        scheduler_type = project.info.get("sched", "default")
        task_queue_scheduler = scheduler_type in [Schedulers.task_queue]
        reserve_task_config = project.info.get("reserve_tasks", {}).get("category", [])

        # Enable filter_user_prefs for user_pref and task_queue schedulers if not explicitly set
        if not filter_user_prefs and scheduler_type in [Schedulers.user_pref, Schedulers.task_queue]:
            filter_user_prefs = True

        # "first" or "last" value of saved_task_position will result tasks retrieving from DB
        task_id, lock_seconds = (None, 0) if saved_task_position else get_task_id_and_duration_for_project_user(project_id, user_id)

        if lock_seconds > 10:
            task = session.query(Task).get(task_id)
            if task:
                return [task]
        user_count = get_active_user_count(project_id, sentinel.master)
        assign_user = json.dumps({'assign_user': [cached_users.get_user_email(user_id)]}) if user_id else None
        current_app.logger.info(
            "Project {} - number of current users: {}"
            .format(project_id, user_count))

        sql_filters, sql_filter_params, exclude_user = "", {}, False
        if task_queue_scheduler and reserve_task_config:
            sql_filters, sql_filter_params, category_keys = \
                get_reserve_task_category_info(
                    reserve_task_config, project_id, timeout, user_id)
            if not category_keys:
                # no category reserved by current user. search categories
                # excluding the ones reserved by other users
                current_app.logger.info(
                    "Project %s, user %s, %s", project_id, user_id,
                    "No task category reserved by user. Search tasks excuding categories reserved by other users"
                )
                exclude_user = True
                sql_filters, sql_filter_params, category_keys = \
                    get_reserve_task_category_info(
                        reserve_task_config, project_id, timeout, user_id,
                        exclude_user)
                current_app.logger.info("SQL filter excuding task categories reserved by other users. sql filter %s", sql_filters)

        limit = current_app.config.get('DB_MAXIMUM_BATCH_SIZE') if filter_user_prefs else user_count + 5 + current_app.config.get('MAX_SAVED_ANSWERS', 30)
        sql, sql_params = query_factory(
            project_id, user_id=user_id, limit=limit,
            rand_within_priority=rand_within_priority,
            task_type=task_type, task_category_filters=sql_filters)
        query_params = dict(project_id=project_id,
                            user_id=user_id,
                            assign_user=assign_user,
                            limit=limit)
        query_params.update(sql_filter_params)
        query_params.update(sql_params)
        rows = session.execute(sql, query_params)

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
            sql_filters, sql_filter_params, category_keys = \
                get_reserve_task_category_info(
                    reserve_task_config, project_id, timeout, user_id,
                    exclude_user)
            current_app.logger.info("SQL filter excuding task categories reserved by other users. sql filter %s", sql_filters)
            sql, sql_params = query_factory(
                project_id, user_id=user_id, limit=limit,
                rand_within_priority=rand_within_priority,
                task_type=task_type, task_category_filters=sql_filters)
            query_params = dict(project_id=project_id,
                                user_id=user_id,
                                assign_user=assign_user,
                                limit=limit)
            query_params.update(sql_filter_params)
            query_params.update(sql_params)
            rows = session.execute(sql, query_params)

        user_profile = cached_users.get_user_profile_metadata(user_id)

        # Get all saved task IDs from Redis for the current user
        task_id_map = None
        if saved_task_position:
            task_id_map = get_user_saved_partial_tasks(
                sentinel, project_id, user_id, task_repo)

        # validate user qualification and calculate task preference score
        user_profile = json.loads(user_profile) if user_profile else {}
        task_rank_info = []
        for task_id, taskcount, n_answers, calibration, w_filter, w_pref, timeout in rows:
            score = 0
            if filter_user_prefs:
                w_pref = w_pref or {}
                w_filter = w_filter or {}
                meet_requirement = cached_task_browse_helpers.user_meet_task_requirement(
                    task_id, w_filter, user_profile)
                if not meet_requirement:
                    continue
                score = cached_task_browse_helpers.get_task_preference_score(
                    w_pref, user_profile)
                current_app.logger.info("locked_scheduler. User met worker filter requirement for project %s, task %s, user_id %s, worker_filter: %s, user_profile: %s, score=%s",
                                        project_id, task_id, user_id, w_filter, user_profile, score)

            if task_id_map and task_id in task_id_map:
                ttl = task_id_map.get(task_id, -1)
                if ttl > 0 and saved_task_position == SavedTaskPositionEnum.LAST:
                    score = -ttl  # Saved tasks sink to the bottom, but with earliest saved task first
                elif ttl > 0 and saved_task_position == SavedTaskPositionEnum.FIRST:
                    score = sys.maxsize - ttl  # Earliest saved task first
                current_app.logger.info(
                    "locked_scheduler. User can obtain task via saved tasks for project %s, task %s, user %s, ttl %s, score %s",
                    project_id, task_id, user_id, ttl, score
                )
            elif not filter_user_prefs:  # Default/locker schedulers
                current_app.logger.info(
                    "locked_scheduler. Task %s added via DEFAULT path (no worker_filter check). "
                    "User %s, project %s, filter_user_prefs=%s, w_filter=%s",
                    task_id, user_id, project_id, filter_user_prefs, w_filter
                )
            task_rank_info.append((task_id, taskcount, n_answers, calibration, score, None, timeout))
        rows = sorted(task_rank_info, key=lambda tup: tup[4], reverse=True)

        # Iterate a list of tasks but only lock one task and return the locked task
        for task_id, taskcount, n_answers, calibration, _, _, timeout in rows:
            timeout = timeout or TIMEOUT
            remaining = float('inf') if calibration else n_answers - taskcount
            if acquire_locks(task_id, user_id, remaining, timeout):
                # reserve tasks
                acquire_reserve_task_lock(project_id, task_id, user_id, timeout)
                current_app.logger.info("locked_scheduler. User acquired lock for project %s, task %s, user %s", project_id, task_id, user_id)
                return _lock_task_for_user(task_id, project_id, user_id, timeout, calibration)
        return []

    return template_get_locked_task


def reserve_task_sql_filters(project_id, reserve_task_keys, exclude):
    # build sql query filter from task category cache key
    # return sql filter for matching task category keys and list of
    # task category keys that qualifies for a given project_id

    filters, filter_params, category_keys = "", {}, []

    if not (project_id and len(reserve_task_keys)):
        return filters, filter_params, category_keys

    filter_dict = {}
    current_app.logger.info("Project %s, exclude %s. Build sql filter from reserver task keys", project_id, exclude)
    current_app.logger.info(
        "reserve tasks keys: %s",
        json.dumps([item.get('resource_id')
                    if isinstance(item, dict) else item
                    for item in reserve_task_keys]))
    regex_key = "reserve_task:project:{}:category:(.+?):user".format(project_id)

    for item in reserve_task_keys:
        if isinstance(item, dict):
            resource_id = item.get('resource_id')
            category_pairs = item.get('category')
            if not resource_id or not category_pairs:
                continue
            if item.get('project_id') and \
                    str(item['project_id']) != str(project_id):
                continue
        else:
            resource_id = item
            data = re.search(regex_key, resource_id)
            if not data:
                continue
            category_fields = data.group(1).split(":")
            if len(category_fields) % 2:
                raise ValueError("Invalid reserved task category")
            category_pairs = [
                category_fields[index:index + 2]
                for index in range(0, len(category_fields), 2)
            ]

        category_keys += [resource_id]
        category_id = json.dumps(category_pairs, sort_keys=True)
        if category_id in filter_dict:
            continue
        filter_list = []
        for index, pair in enumerate(category_pairs):
            if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                raise ValueError("Invalid reserved task category")
            key, value = pair
            if not cached_task_browse_helpers.is_valid_searchable_column(key):
                raise ValueError("Invalid reserved task category key")
            param_suffix = "{}_{}".format(len(filter_dict), index)
            key_param = "reserve_category_key_{}".format(param_suffix)
            value_param = "reserve_category_value_{}".format(param_suffix)
            filter_list.append(
                "task.info ->> :{} = :{}".format(key_param, value_param))
            filter_params[key_param] = key
            filter_params[value_param] = str(value)
        filter_dict[category_id] = "({})".format(" AND ".join(filter_list))

    if filter_dict:
        exclude_clause = "IS NOT TRUE " if exclude else ""
        filters = "({}) {}".format(" OR ".join(filter_dict.values()), exclude_clause)
        filters = " AND {}".format(filters) if filters else filters

    current_app.logger.info("sql filter %s, reserve keys %s", filters, json.dumps(category_keys))

    # TODO: pull task # from category keys, look for values from task._add_user_info
    # generate sql_filter considering value field type instead.
    return filters, filter_params, category_keys


def get_reserve_task_category(task_id):
    category = []
    task = task_repo.get_task(task_id)
    if not task:
        return category

    project = project_repo.get(task.project_id)
    if not (project and project.info.get("sched", "default") in [Schedulers.task_queue]):
        return category

    reserve_task_config = project.info.get("reserve_tasks", {}).get("category", [])
    if not reserve_task_config:
        return category

    if not all(field in task.info for field in reserve_task_config):
        return category

    return [[field, str(task.info[field])]
            for field in sorted(reserve_task_config)]


def get_reserve_task_category_info(reserve_task_config, project_id, timeout, user_id, exclude_user=False):
    """Get reserved category info for a given user under a given project"""
    timeout = timeout or TIMEOUT
    sql_filters, sql_filter_params, category_keys = "", {}, []

    if not reserve_task_config:
        return sql_filters, sql_filter_params, category_keys

    if current_app.config.get('PRIVATE_INSTANCE'):
        current_app.logger.info("Reserve task by category disabled for private instance. project_id %s, reserve_task_config %s",
            project_id, str(reserve_task_config))
        return sql_filters, sql_filter_params, category_keys

    lock_manager = LockManager(sentinel.master, timeout)
    category_locks = lock_manager.get_task_category_lock(
        project_id, user_id, sorted(reserve_task_config), exclude_user)
    current_app.logger.info(
        "Project %s, user %s, reserve config %s, exclude %s. reserve task category keys %s",
        project_id, user_id, json.dumps(reserve_task_config), exclude_user,
        str([lock.get('resource_id', lock)
             if isinstance(lock, dict) else lock for lock in category_locks])
    )
    if not category_locks:
        return sql_filters, sql_filter_params, category_keys

    sql_filters, sql_filter_params, category_keys = \
        reserve_task_sql_filters(project_id, category_locks, exclude_user)
    return sql_filters, sql_filter_params, category_keys


def locked_task_sql(project_id, user_id=None, limit=1, rand_within_priority=False,
                    task_type='gold_last', filter_user_prefs=False,
                    priority_sort=True, task_category_filters=""):
    '''
    Returns (sql, params). params carries the bound values for any
    user-controlled filter built into the statement and must be merged into the
    dict passed to session.execute().

    `task_type` will affect the type of tasks return by the query and can be one
    one of the following values:
        gold ->         only gold tasks will be returned
        no_gold ->      only non-gold tasks will be returned
        gold_last ->    non-gold tasks will be returned before gold tasks. (Default)
        gold_first ->   gold tasks will be returned before non-gold tasks.
    '''
    filters = []
    params = {}
    if filter_user_prefs:
        user_pref_sql, user_pref_params = \
            cached_users.get_user_preferences(user_id)
        user_filter_sql, user_filter_params = \
            cached_users.get_user_filters(user_id)
        filters.append('AND ({}) AND ({})'.format(
            user_pref_sql, user_filter_sql))
        params.update(user_pref_params)
        params.update(user_filter_params)
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
    return text(sql), params


def select_contributable_task(project, user_id, **kwargs):
    sched, _ = get_scheduler_and_timeout(project)
    with_user_pref = sched in [Schedulers.user_pref, Schedulers.task_queue]
    kwargs['filter_user_prefs'] = with_user_pref

    params = dict(project_id=project.id, user_id=user_id, limit=1)
    if with_user_pref:
        params['assign_user'] = None

    sql, sql_params = locked_task_sql(project.id, user_id, **kwargs)
    params.update(sql_params)
    rows = session.execute(sql, params)
    for row in rows:
        return task_repo.get_task(row.id)
    return {}


def select_task_for_gold_mode(project, user_id):
    return select_contributable_task(project, user_id,
        rand_within_priority=True, task_type='no_gold', priority_sort=False)


@locked_scheduler
def get_locked_task(project_id, user_id=None, limit=1, rand_within_priority=False,
                    task_type='gold_last', task_category_filters="", saved_task_position=None):
    return locked_task_sql(project_id, user_id=user_id, limit=limit,
                           rand_within_priority=rand_within_priority, task_type=task_type,
                           filter_user_prefs=False, task_category_filters=task_category_filters)


@locked_scheduler
def get_user_pref_task(project_id, user_id=None, limit=1, rand_within_priority=False,
                       task_type='gold_last', filter_user_prefs=True, task_category_filters="", saved_task_position=None):
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


def fetch_lock_for_user(project_id, task_id, user_id):
    scheduler, timeout = get_project_scheduler_and_timeout(project_id)

    ttl = None
    if is_locking_scheduler(scheduler):
        task_locked_by_user = has_lock(task_id, user_id, timeout)
        if task_locked_by_user:
            locks = get_locks(task_id, timeout)
            ttl = locks.get(str(user_id))

    return timeout, ttl


def has_lock(task_id, user_id, timeout):
    lock_manager = LockManager(sentinel.master, timeout)
    task_users_key = get_task_users_key(task_id)
    return lock_manager.has_lock(task_users_key, user_id)


def acquire_locks(task_id, user_id, limit, timeout):
    lock_manager = LockManager(sentinel.master, timeout)
    task_users_key = get_task_users_key(task_id)
    user_tasks_key = get_user_tasks_key(user_id)
    if lock_manager.acquire_lock(task_users_key, user_id, limit):
        lock_manager.acquire_lock(user_tasks_key, task_id, float('inf'))
        return True
    return False


def release_reserve_task_lock_by_id(project_id, task_id, user_id, timeout, expiry=EXPIRE_RESERVE_TASK_LOCK_DELAY, release_all_task=False):
    category = get_reserve_task_category(task_id)
    if not category:
        return

    redis_conn = sentinel.master
    lock_manager = LockManager(redis_conn, timeout)
    if release_all_task:
        reservations = lock_manager.get_task_category_lock(
            project_id, user_id, category)
        reservations = [reservation for reservation in reservations
                        if reservation['category'] == category]

        # get_user_tasks contains task_id and time_stamp pair. Filter out non expired tasks
        tasks_locked_by_user = {task_id: time_stamp for task_id, time_stamp
                                in get_user_tasks(user_id, timeout).items()
                                if LockManager.seconds_remaining(time_stamp) > EXPIRE_LOCK_DELAY}

        for reservation in reservations:
            resource_id = reservation['resource_id']
            task_id_in_key = int(reservation['task_id'])
            # If a task is locked by the user(in other tab), then the category lock should not be released
            if task_id_in_key == task_id or str(task_id_in_key) not in tasks_locked_by_user:
                lock_manager.release_reserve_task_lock(resource_id, expiry)
                current_app.logger.info("Release reserve task locks: %s, task: %d, project: %s, user: %s", resource_id, task_id_in_key, project_id, user_id)
    else:
        reservations = lock_manager.get_task_category_lock(
            project_id, user_id, category, task_id=task_id)
        for reservation in reservations:
            lock_manager.release_reserve_task_lock(
                reservation['resource_id'], expiry)
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

    category = [[field, str(task.info.get(field))]
                for field in sorted(reserve_task_config)]
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
        if not calibration:
            # Re-check against master DB to guard against slave replication lag
            actual_count = db.session.query(
                func.count(TaskRun.id)
            ).filter_by(task_id=task_id).scalar()
            if actual_count >= n_answers:
                current_app.logger.warning(
                    "lock_task_for_user: skipping task %s, "
                    "master DB shows %d task_runs >= n_answers %d",
                    task_id, actual_count, n_answers
                )
                return []
            remaining = n_answers - actual_count
        else:
            remaining = float('inf')
        if acquire_locks(task_id, user_id, remaining, timeout):
            # reserve tasks
            acquire_reserve_task_lock(project_id, task_id, user_id, timeout)
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
    project_ids = get_task_ids_project_id(user_task_ids)
    task_ids = []
    for task_id, task_project_id in zip(user_task_ids, project_ids):
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


def get_task_id_and_duration_for_project_user(project_id, user_id):
    """Returns the max seconds remaining locked task for a user and project."""
    user_tasks = get_user_tasks(user_id, TIMEOUT)
    user_task_ids = list(user_tasks.keys())
    project_ids = get_task_ids_project_id(user_task_ids)
    max_seconds_task_id = -1
    max_seconds_remaining = float('-inf')
    for task_id, task_project_id in zip(user_task_ids, project_ids):
        if not task_project_id:
            task = task_repo.get_task(task_id)
            if task:
                task_project_id = task.project_id
                save_task_id_project_id(task_id, task_project_id, 2 * TIMEOUT)
            else:
                # No task found for task_id.
                current_app.logger.info(
                    "Project {}, User {}, Task Id {} - task not found in get_task_id_and_duration_for_project_user()."
                    .format(project_id, user_id, task_id))

        if task_project_id and int(task_project_id) == project_id:
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
    return [('default', 'Default'),
            (Schedulers.locked, 'Locked'),
            (Schedulers.user_pref, 'User Preference Scheduler'),
            (Schedulers.task_queue, 'Task Queues')
            ]


def randomizable_scheds():
    scheds = [Schedulers.locked, Schedulers.user_pref]
    if DEFAULT_SCHEDULER in scheds:
        scheds.append('default')
    return scheds
