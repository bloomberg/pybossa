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
from datetime import timedelta
from time import time

from pybossa.contributions_guard import ContributionsGuard
from pybossa.core import sentinel
from werkzeug.exceptions import BadRequest

TASK_USERS_KEY_PREFIX = 'pybossa:project:task_requested:timestamps:{0}'
USER_TASKS_KEY_PREFIX = 'pybossa:user:task_acquired:timestamps:{0}'
TASK_ID_PROJECT_ID_KEY_PREFIX = 'pybossa:task_id:project_id:{0}'
ACTIVE_USER_KEY = 'pybossa:active_users_in_project:{}'
EXPIRE_LOCK_DELAY = 5
EXPIRE_RESERVE_TASK_LOCK_DELAY = 30*60


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
        reservations = self._redis.keys(resource_id) or []
        decoded_reservation_keys = [k.decode() for k in reservations]
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
        resource_id = "reserve_task:project:{}:category:*:user:*:task:*".format(project_id)
        timestamp = time()

        reservation_keys = self.get_reservation_keys(resource_id)
        for k in reservation_keys:
            self._release_expired_reserve_task_locks(k, timestamp)

    def _release_expired_reserve_task_locks(self, resource_id, now):
        expiration = self._redis.get(resource_id) or 0
        if now > float(expiration):
            self._redis.delete(resource_id)


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

        resource_id = "reserve_task:project:{}:category:{}:user:{}:task:{}".format(
            project_id,
            "*" if not category else category,
            "*" if not user_id or exclude_user else user_id,
            "*" if not task_id else task_id
        )

        category_keys = self.get_reservation_keys(resource_id)

        # if key present but for different user, with redundancy = 1, return false
        # TODO: for redundancy > 1, check if additional task run
        # available for this user and if so, return category_key else ""
        if exclude_user:
            # exclude user_id from list of keys passed
            drop_user = ":user:{}:task:".format(user_id)
            category_keys = [ key for key in category_keys if drop_user not in key ]
        return category_keys


    def acquire_reserve_task_lock(self, project_id, task_id, user_id, category):
        if not(project_id and user_id and task_id and category):
            raise BadRequest('Missing required parameters')

        # check task category reserved by user
        resource_id = "reserve_task:project:{}:category:{}:user:{}:task:{}".format(project_id, category, user_id, task_id)

        timestamp = time()
        self._release_expired_reserve_task_locks(resource_id, timestamp)
        expiration = timestamp + self._duration + EXPIRE_RESERVE_TASK_LOCK_DELAY
        return self._redis.set(resource_id, expiration)


    def release_reserve_task_lock(self, resource_id, expiry):
        #cache = pipeline or self._redis # https://pythonrepo.com/repo/andymccurdy-redis-py-python-connecting-and-operating-databases#locks
        cache = self._redis
        cache.expire(resource_id, expiry)
