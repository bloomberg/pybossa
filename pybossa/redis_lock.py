# -*- coding: utf8 -*-
# This file is part of PYBOSSA.
#
# Copyright (C) 2018 Scifabric LTD.
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
from datetime import timedelta, datetime
from math import ceil
import re
from time import time

from pybossa.contributions_guard import ContributionsGuard
from pybossa.core import sentinel
from werkzeug.exceptions import BadRequest
import os

TASK_USERS_KEY_PREFIX = 'pybossa:project:task_requested:timestamps:{0}'
USER_TASKS_KEY_PREFIX = 'pybossa:user:task_acquired:timestamps:{0}'
TASK_ID_PROJECT_ID_KEY_PREFIX = 'pybossa:task_id:project_id:{0}'
ACTIVE_USER_KEY = 'pybossa:active_users_in_project:{}'
EXPIRE_LOCK_DELAY = 5
EXPIRE_RESERVE_TASK_LOCK_DELAY = 30*60
USER_EXPORTED_REPORTS_KEY = 'pybossa:user:exported:reports:{}'
RESERVE_TASK_LOCK_KEY = 'reserve_task:v2:project:{}:user:{}:task:{}'
LEGACY_RESERVE_TASK_LOCK_KEY = \
    'reserve_task:project:{}:category:{}:user:{}:task:{}'
RESERVE_TASK_LOCK_PATTERN = re.compile(
    r'^reserve_task:v2:project:(?P<project>\d+):user:(?P<user>\d+):'
    r'task:(?P<task>\d+)$')
LEGACY_RESERVE_TASK_LOCK_PATTERN = re.compile(
    r'^reserve_task:project:(?P<project>\d+):category:(?P<category>.+):'
    r'user:(?P<user>\d+):task:(?P<task>\d+)$')


def get_reserve_task_lock_key(project_id, user_id, task_id):
    return RESERVE_TASK_LOCK_KEY.format(project_id, user_id, task_id)

def get_active_user_key(project_id):
    return ACTIVE_USER_KEY.format(project_id)

def get_task_users_key(task_id):
    if type(task_id) == bytes:
        task_id = task_id.decode()
    return TASK_USERS_KEY_PREFIX.format(task_id)

def get_user_tasks_key(user_id):
    # bytes to unicode string
    if type(user_id) == bytes:
        user_id = user_id.decode()
    return USER_TASKS_KEY_PREFIX.format(user_id)

def get_task_id_project_id_key(task_id):
    return TASK_ID_PROJECT_ID_KEY_PREFIX.format(task_id)

def get_active_user_count(project_id, conn):
    now = time()
    key = get_active_user_key(project_id)
    to_delete = [user for user, expiration in conn.hgetall(key).items()
                 if float(expiration) < now]
    if to_delete:
        conn.hdel(key, *to_delete)
    return conn.hlen(key)


def register_active_user(project_id, user_id, conn, ttl=2*60*60):
    now = time()
    key = get_active_user_key(project_id)
    conn.hset(key, user_id, now + ttl)
    conn.expire(key, ttl)


def unregister_active_user(project_id, user_id, conn):
    now = time()
    key = get_active_user_key(project_id)
    conn.hset(key, user_id, now + EXPIRE_LOCK_DELAY)


def get_locked_tasks_project(project_id):
    """Returns a list of locked tasks for a given project."""
    tasks = []
    redis_conn = sentinel.master
    timeout = ContributionsGuard.STAMP_TTL
    lock_manager = LockManager(sentinel.master, timeout)

    # Get the active users key for this project.
    key = get_active_user_key(project_id)

    # Get the users for each locked task.
    for user_key in redis_conn.hgetall(key).items():
        user_id = user_key[0]

        # Redis client in Python returns bytes string
        if type(user_id) == bytes:
            user_id = user_id.decode()

        # Get locks by user.
        user_tasks_key = get_user_tasks_key(user_id)
        user_tasks = lock_manager.get_locks(user_tasks_key)
        # Get task ids for the locks.
        user_task_ids = user_tasks.keys()
        # Get project ids for the task ids.
        results = []
        keys = [get_task_id_project_id_key(t) for t in user_task_ids]
        if keys:
            results = sentinel.master.mget(keys)

        # For each locked task, check if the lock is still active.
        for task_id, task_project_id in zip(user_task_ids, results):
            if not task_project_id:
                # Import at runtime due to order of execution for global initialization of task_repo.
                from pybossa.core import task_repo
                task = task_repo.get_task(task_id)
                if task:
                    task_project_id = task.project_id
                else:
                    # Locked task has been deleted.
                    task_users_key = get_task_users_key(task_id)
                    lock_manager.release_lock(task_users_key, user_id)
                    lock_manager.release_lock(user_tasks_key, task_id)
            # Match the requested project id.
            if task_project_id and int(task_project_id) == project_id:
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

def get_user_exported_reports_key(user_id):
    # redis key to store exported reports for user_id
    return USER_EXPORTED_REPORTS_KEY.format(user_id)

def register_user_exported_report(user_id, path, conn, ttl=60*60):
    # register report path for user_id
    # reports are stored as hset with key as user_id and field as timestamp:path
    now = time()
    key = get_user_exported_reports_key(user_id)
    filename = os.path.basename(path)
    value = json.dumps({"filename": filename, "path": path})
    conn.hset(key, now, value)
    conn.expire(key, ttl)
    cache_info = f"Registered exported report for user_id {user_id} at {now} with value {value}"
    return cache_info

def get_user_exported_reports(user_id, conn):
    # obtain all reports for user_id
    # reports are stored as hset with key as user_id and field as timestamp:path
    # return list of (timestamp, path) tuples
    key = get_user_exported_reports_key(user_id)
    reports_data = conn.hgetall(key).items()
    result = []
    for k, v in reports_data:
        decoded_value = json.loads(v.decode())
        formatted_time = datetime.fromtimestamp(float(k.decode())).strftime('%Y-%m-%d %H:%M:%S:%f')[:-3]
        result.append((formatted_time, decoded_value['filename'], decoded_value['path']))
    return result


class LockManager(object):
    """
    Class to manage resource locks
    :param cache: a Redis connection
    :param duration: how long a lock is valid after being acquired
        if not released (in seconds)
    """
    def __init__(self, cache, duration):
        self._redis = cache
        self._duration = duration

    def acquire_lock(self, resource_id, client_id, limit):
        """
        Acquire a lock on a resource.
        :param resource_id: resource on which lock is needed
        :param client_id: id of client needing the lock
        :param limit: how many clients can access the resource concurrently
        :return: True if lock was successfully acquired, else False
        """
        timestamp = time()
        expiration = timestamp + self._duration
        self._release_expired_locks(resource_id, timestamp)
        if self._redis.hexists(resource_id, client_id):
            return True

        pipeline = self._redis.pipeline()
        if limit == float('inf'):
            pipeline.hset(resource_id, client_id, expiration)
            pipeline.expire(resource_id, timedelta(seconds=self._duration))
            pipeline.execute()
            return True

        # Get a mutex lock for updating redis hash with default TTL 3s
        lock_name = f"{resource_id}_update_mutex"
        result = False

        try:
            with self._redis.lock(lock_name, timeout=3, blocking_timeout=1) as mutex:
                if not mutex.locked():
                    return False

                num_acquired = self._redis.hlen(resource_id)
                if num_acquired < limit:
                    pipeline.hset(resource_id, client_id, expiration)
                    pipeline.expire(resource_id, timedelta(seconds=self._duration))
                    pipeline.execute()
                    result = True
        finally:
            return result

    def has_lock(self, resource_id, client_id):
        """
        :param resource_id: resource on which lock is being held
        :param client_id: client id
        :return: True if client id holds a lock on the resource,
        False otherwise
        """
        exists = self._redis.hexists(resource_id, client_id)
        if not exists:
            return False
        time_str = self._redis.hget(resource_id, client_id)
        expiration = float(time_str)
        now = time()
        return expiration > now

    def release_lock(self, resource_id, client_id, pipeline=None):
        """
        Release a lock. Note that the lock is not release immediately, rather
        its expiration is set after a short interval from the current time.
        This is done so that concurrent requests will still see the lock and
        avoid race conditions due to possibly stale data already retrieved from
        the database.
        :param resource_id: resource on which lock is being held
        :param client_id: id of client holding the lock
        :param pipeline: object that can queue multiple commands for later execution
        """
        cache = pipeline or self._redis
        cache.hset(resource_id, client_id, time() + EXPIRE_LOCK_DELAY)

    def get_locks(self, resource_id):
        """
        Get all locks associated with a particular resource.
        :param resource_id: resource on which lock is being held
        """
        locks = self._redis.hgetall(resource_id)

        # By default, all responses are returned as bytes in Python 3 and
        # str in Python 2 - per https://github.com/andymccurdy/redis-py
        decoded_locks = {k.decode(): v.decode() for k, v in locks.items()}
        return decoded_locks

    def get_reservation_keys(self, resource_id):
        """
        Get all reservation key/resource_id associated with partial resource information.
        :param resource_id: resource on project/task/user
        """
        reservations = self.scan_keys(resource_id)
        decoded_reservation_keys = [
            key.decode() if isinstance(key, bytes) else key
            for key in reservations
        ]
        return decoded_reservation_keys

    def _release_expired_locks(self, resource_id, now):
        locks = self.get_locks(resource_id)
        to_delete = []
        for key, expiration in locks.items():
            expiration = float(expiration)
            if now > expiration:
                to_delete.append(key)
        if to_delete:
            self._redis.hdel(resource_id, *to_delete)

    def _release_expired_reserve_for_project(self, project_id):
        timestamp = time()
        patterns = [
            LEGACY_RESERVE_TASK_LOCK_KEY.format(project_id, '*', '*', '*'),
            RESERVE_TASK_LOCK_KEY.format(project_id, '*', '*')
        ]
        reservation_keys = []
        for pattern in patterns:
            reservation_keys.extend(self.get_reservation_keys(pattern))
        for k in reservation_keys:
            self._release_expired_reserve_task_locks(k, timestamp)

    def _release_expired_reserve_task_locks(self, resource_id, now):
        try:
            reservation = self._decode_reserve_task_lock(resource_id)
        except (TypeError, ValueError):
            self._redis.delete(resource_id)
            return
        if reservation is None or now > reservation['expires_at']:
            self._redis.delete(resource_id)

    @staticmethod
    def _normalize_reserve_task_category(category):
        if not isinstance(category, (list, tuple)) or not category:
            raise ValueError('Invalid reserved task category')
        normalized = []
        for pair in category:
            if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                raise ValueError('Invalid reserved task category')
            normalized.append([str(pair[0]), str(pair[1])])
        return sorted(normalized)

    def _decode_reserve_task_lock(self, resource_id):
        raw_value = self._redis.get(resource_id)
        if raw_value is None:
            return None
        if isinstance(raw_value, bytes):
            raw_value = raw_value.decode()

        match = RESERVE_TASK_LOCK_PATTERN.match(resource_id)
        if match:
            payload = json.loads(raw_value)
            if not isinstance(payload, dict) or payload.get('version') != 2:
                raise ValueError('Invalid reserved task lock version')
            category = self._normalize_reserve_task_category(
                payload.get('category'))
            expiration = float(payload['expires_at'])
        else:
            match = LEGACY_RESERVE_TASK_LOCK_PATTERN.match(resource_id)
            if not match:
                raise ValueError('Invalid reserved task lock key')
            category_fields = match.group('category').split(':')
            if len(category_fields) % 2:
                raise ValueError('Invalid reserved task category')
            category = self._normalize_reserve_task_category([
                category_fields[index:index + 2]
                for index in range(0, len(category_fields), 2)
            ])
            expiration = float(raw_value)

        return {
            'resource_id': resource_id,
            'project_id': match.group('project'),
            'user_id': match.group('user'),
            'task_id': match.group('task'),
            'category': category,
            'expires_at': expiration
        }


    @staticmethod
    def seconds_remaining(expiration):
        return float(expiration) - time()

    def get_task_category_lock(self, project_id, user_id=None, category=None, exclude_user=False, task_id=None):
        """
        Returns True when task category for a given user
        can be reserved or its already reserved, False otherwise.
        To fetch task category for all users who've reserved the category, pass user_id = None
        To fetch task category for all tasks reserved, pass task_id = None
        To fetch task category other than user_id, pass exclude_user = True
        """

        if not project_id:
            raise BadRequest('Missing required parameters')

        # with exclude_user set to True, user_id is to be excluded from list of
        # task category found for all users. raise error if user_id not passed
        if exclude_user and not user_id:
            raise BadRequest('Missing user id')

        # release expired task reservations
        self._release_expired_reserve_for_project(project_id)

        category_fields = []
        if category:
            if isinstance(category, str):
                category_fields = category.split(':')[::2]
            elif isinstance(category[0], (list, tuple)):
                category_fields = [pair[0] for pair in category]
            else:
                category_fields = category
        category_fields = sorted(str(field) for field in category_fields)
        selected_user = '*' if not user_id or exclude_user else user_id
        selected_task = '*' if not task_id else task_id
        patterns = [
            LEGACY_RESERVE_TASK_LOCK_KEY.format(
                project_id, '*', selected_user, selected_task),
            RESERVE_TASK_LOCK_KEY.format(
                project_id, selected_user, selected_task)
        ]
        reservations = []
        for pattern in patterns:
            for resource_id in self.get_reservation_keys(pattern):
                reservation = self._decode_reserve_task_lock(resource_id)
                if reservation is None:
                    continue
                reservation_fields = sorted(
                    pair[0] for pair in reservation['category'])
                if category_fields and reservation_fields != category_fields:
                    continue
                if exclude_user and reservation['user_id'] == str(user_id):
                    continue
                reservations.append(reservation)
        return reservations

    def acquire_reserve_task_lock(self, project_id, task_id, user_id, category):
        if not(project_id and user_id and task_id and category):
            raise BadRequest('Missing required parameters')

        category = self._normalize_reserve_task_category(category)
        resource_id = get_reserve_task_lock_key(project_id, user_id, task_id)
        timestamp = time()
        self._release_expired_reserve_task_locks(resource_id, timestamp)
        expiration = timestamp + self._duration + EXPIRE_RESERVE_TASK_LOCK_DELAY
        payload = json.dumps({
            'version': 2,
            'category': category,
            'expires_at': expiration
        }, sort_keys=True, separators=(',', ':'))
        ttl = max(1, int(ceil(self._duration + EXPIRE_RESERVE_TASK_LOCK_DELAY)))
        return self._redis.set(resource_id, payload, ex=ttl)

    def release_reserve_task_lock(self, resource_id, expiry):
        #cache = pipeline or self._redis # https://pythonrepo.com/repo/andymccurdy-redis-py-python-connecting-and-operating-databases#locks
        cache = self._redis
        cache.expire(resource_id, expiry)

    def scan_keys(self, pattern):
        return self._redis.scan_iter(pattern)
