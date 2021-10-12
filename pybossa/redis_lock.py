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

from datetime import timedelta
from time import time

from contributions_guard import ContributionsGuard
from pybossa.core import sentinel

TASK_USERS_KEY_PREFIX = 'pybossa:project:task_requested:timestamps:{0}'
USER_TASKS_KEY_PREFIX = 'pybossa:user:task_acquired:timestamps:{0}'
TASK_ID_PROJECT_ID_KEY_PREFIX = 'pybossa:task_id:project_id:{0}'
ACTIVE_USER_KEY = 'pybossa:active_users_in_project:{}'
EXPIRE_LOCK_DELAY = 5


def get_active_user_key(project_id):
    return ACTIVE_USER_KEY.format(project_id)

def get_task_users_key(task_id):
    return TASK_USERS_KEY_PREFIX.format(task_id)

def get_user_tasks_key(user_id):
    return USER_TASKS_KEY_PREFIX.format(user_id)

def get_task_id_project_id_key(task_id):
    return TASK_ID_PROJECT_ID_KEY_PREFIX.format(task_id)

def get_active_user_count(project_id, conn):
    now = time()
    key = get_active_user_key(project_id)
    to_delete = [user for user, expiration in conn.hgetall(key).iteritems()
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
    for user_key in redis_conn.hgetall(key).iteritems():
        user_id = user_key[0]

        # Get locks by user.
        user_tasks_key = get_user_tasks_key(user_id)
        user_tasks = lock_manager.get_locks(user_tasks_key)
        # Get task ids for the locks.
        user_task_ids = user_tasks.keys()
        # Get project ids for the task ids.
        # results = get_task_ids_project_id(user_task_ids)
        results = []
        keys = [get_task_id_project_id_key(t) for t in user_task_ids]
        if keys:
            results = sentinel.master.mget(keys)

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

    def acquire_lock(self, resource_id, client_id, limit, pipeline=None):
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
        num_acquired = self._redis.hlen(resource_id)
        if num_acquired < limit:
            cache = pipeline or self._redis
            cache.hset(resource_id, client_id, expiration)
            cache.expire(resource_id, timedelta(seconds=self._duration))
            return True
        return False

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
        """
        cache = pipeline or self._redis
        cache.hset(resource_id, client_id, time() + EXPIRE_LOCK_DELAY)

    def get_locks(self, resource_id):
        """
        Get all locks associated with a particular resource.
        :param resource_id: resource on which lock is being held
        """
        return self._redis.hgetall(resource_id)

    def _release_expired_locks(self, resource_id, now):
        locks = self.get_locks(resource_id)
        to_delete = []
        for key, expiration in locks.iteritems():
            expiration = float(expiration)
            if now > expiration:
                to_delete.append(key)
        if to_delete:
            self._redis.hdel(resource_id, *to_delete)

    @staticmethod
    def seconds_remaining(expiration):
        return float(expiration) - time()
