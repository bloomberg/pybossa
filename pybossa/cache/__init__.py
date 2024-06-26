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
# Cache global variables for timeouts
"""
This module exports a set of decorators for caching functions.

It exports:
    * cache: for caching functions without parameters
    * memoize: for caching functions using its arguments as part of the key
    * delete_cached: to remove a cached value
    * delete_memoized: to remove a cached value from the memoize decorator

"""
import os
import hashlib
import time
from functools import wraps
from random import randrange

from flask import current_app
from redis.exceptions import LockError

from pybossa.core import sentinel

try:
    import pickle as pickle
except ImportError:  # pragma: no cover
    import pickle

try:
    from pybossa.app_settings import config as settings
    REDIS_KEYPREFIX = settings['REDIS_KEYPREFIX']
except ImportError:  # pragma: no cover
    import pybossa.default_settings as settings
    REDIS_KEYPREFIX = settings.REDIS_KEYPREFIX
    os.environ['PYBOSSA_REDIS_CACHE_DISABLED'] = '1'

DEFAULT_TIMEOUT = 300
MIN_TIMEOUT = 1
ONE_DAY = 24 * 60 * 60
ONE_HOUR = 60 * 60
HALF_HOUR = 30 * 60
FIVE_MINUTES = 5 * 60
ONE_WEEK = 7 * ONE_DAY
ONE_MINUTE = 60
L2_CACHE_TIMEOUT = ONE_DAY
MUTEX_LOCK_TIMEOUT = ONE_MINUTE
TWO_WEEKS = 14 * ONE_DAY
ONE_MONTH = 30 * ONE_DAY

management_dashboard_stats = [
    'project_chart', 'category_chart', 'task_chart',
    'submission_chart', 'number_of_active_jobs',
    'number_of_created_jobs', 'number_of_created_tasks',
    'number_of_completed_tasks', 'avg_time_to_complete_task',
    'number_of_active_users', 'categories_with_new_projects',
    'avg_task_per_job', 'tasks_per_category'
]


def get_key_to_hash(*args, **kwargs):
    """Return key to hash for *args and **kwargs."""
    key_to_hash = ""
    # First args
    for i in args:
        key_to_hash += ":%s" % i
    # Attach any kwargs
    for key in sorted(kwargs.keys()):
        key_to_hash += ":%s" % kwargs[key]
    return key_to_hash


def get_hash_key(prefix, key_to_hash):
    """Return hash for a prefix and a key to hash."""
    key_to_hash = key_to_hash.encode('utf-8')
    key = prefix + ":" + hashlib.md5(key_to_hash).hexdigest()
    return key


def get_cache_group_key(key):
    return '{}:memoize_cache_group:{}'.format(REDIS_KEYPREFIX, key)


def add_key_to_cache_groups(key_to_add, cache_group_keys_arg, *args, **kwargs):
    for cache_group_key_arg in (cache_group_keys_arg or []):
        cache_group_key = None
        if isinstance(cache_group_key_arg, list):
            cache_group_key = '_'.join(str(args[i]) for i in cache_group_key_arg)
        elif isinstance(cache_group_key_arg, str):
            cache_group_key = cache_group_key_arg
        elif callable(cache_group_key_arg):
            cache_group_key = cache_group_key_arg(*args, **kwargs)
        elif cache_group_key_arg is not None:
            raise Exception('Invalid cache_group_key_arg: {}'.format(cache_group_key_arg))
        else:
            return
        key = get_cache_group_key(cache_group_key)
        sentinel.master.sadd(key, key_to_add)


def delete_cache_group(cache_group_key):
    key = get_cache_group_key(cache_group_key)
    keys_to_delete = list(sentinel.slave.smembers(key)) + [key]
    sentinel.master.delete(*keys_to_delete)


def cache(key_prefix, timeout=300, cache_group_keys=None):
    """
    Decorator for caching functions.

    Returns the function value from cache, or the function if cache disabled

    """
    if timeout is None:
        timeout = DEFAULT_TIMEOUT
    elif timeout < MIN_TIMEOUT:
        timeout = MIN_TIMEOUT

    """
    Adding a random jitter to reduce DB load
    There are scheduled jobs refreshing cache. When refreshing happens, caches
    could have the same TTL. Thus they could expires at the same time, and
    requests will hitting DB, causing a burst of DB load. By adding a random
    jitter, it reduces the possibility that caches expiring at the same time
    and balanced the DB load to avoid many requests hitting the DB.
    """
    timeout += randrange(30)

    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            key = "%s::%s" % (REDIS_KEYPREFIX, key_prefix)
            if os.environ.get('PYBOSSA_REDIS_CACHE_DISABLED') is None:
                output = sentinel.slave.get(key)
                if output:
                    return pickle.loads(output)
                output = f(*args, **kwargs)
                sentinel.master.setex(key, timeout, pickle.dumps(output))
                add_key_to_cache_groups(key, cache_group_keys, *args, **kwargs)
                return output
            output = f(*args, **kwargs)
            sentinel.master.setex(key, timeout, pickle.dumps(output))
            add_key_to_cache_groups(key, cache_group_keys, *args, **kwargs)
            return output
        return wrapper
    return decorator


def memoize(timeout=300, cache_group_keys=None):
    """
    Decorator for caching functions using its arguments as part of the key.

    Returns the cached value, or the function if the cache is disabled

    """
    if timeout is None:
        timeout = DEFAULT_TIMEOUT
    elif timeout < MIN_TIMEOUT:
        timeout = MIN_TIMEOUT

    timeout += randrange(30)  # add a random jitter to reduce DB load

    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            key = "%s:%s_args:" % (REDIS_KEYPREFIX, f.__name__)
            key_to_hash = get_key_to_hash(*args, **kwargs)
            key = get_hash_key(key, key_to_hash)
            if os.environ.get('PYBOSSA_REDIS_CACHE_DISABLED') is None:
                output = sentinel.slave.get(key)
                if output:
                    return pickle.loads(output)
                output = f(*args, **kwargs)
                sentinel.master.setex(key, timeout, pickle.dumps(output))
                add_key_to_cache_groups(key, cache_group_keys, *args, **kwargs)
                return output
            output = f(*args, **kwargs)
            sentinel.master.setex(key, timeout, pickle.dumps(output))
            add_key_to_cache_groups(key, cache_group_keys, *args, **kwargs)
            return output
        return wrapper
    return decorator


def memoize_essentials(timeout=300, essentials=None, cache_group_keys=None):
    """
    Decorator for caching functions using its arguments as part of the key.

    Essential arguments aren't hashed to make it possible to remove a group of cache entries

    Returns the cached value, or the function if the cache is disabled

    """
    if timeout is None:
        timeout = DEFAULT_TIMEOUT
    elif timeout < MIN_TIMEOUT:
        timeout = MIN_TIMEOUT
    if essentials is None:
        essentials = []

    timeout += randrange(30)  # add a random jitter to reduce DB load

    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            key = "%s:%s_args:" % (REDIS_KEYPREFIX, f.__name__)
            essential_args = [args[i] for i in essentials]
            key += get_key_to_hash(*essential_args) + ":"
            key_to_hash = get_key_to_hash(*args, **kwargs)
            key = get_hash_key(key, key_to_hash)
            if os.environ.get('PYBOSSA_REDIS_CACHE_DISABLED') is None:
                if not kwargs.get("force_refresh"):
                    output = sentinel.slave.get(key)
                    if output:
                        return pickle.loads(output)
                output = f(*args, **kwargs)
                sentinel.master.setex(key, timeout, pickle.dumps(output))
                add_key_to_cache_groups(key, cache_group_keys, *args, **kwargs)
                return output
            output = f(*args, **kwargs)
            sentinel.master.setex(key, timeout, pickle.dumps(output))
            add_key_to_cache_groups(key, cache_group_keys, *args, **kwargs)
            return output
        return wrapper
    return decorator


def memoize_with_l2_cache(timeout=DEFAULT_TIMEOUT,
                          timeout_l2=L2_CACHE_TIMEOUT,
                          timeout_mutex_lock=MUTEX_LOCK_TIMEOUT,
                          cache_group_keys=None,
                          key_prefix=None):
    """
    Decorator for caching functions using its arguments as part of the key.
    Returns the cached value, or the function if the cache is disabled
    If l1 cache miss, it will try to read l2 cache, which has a longer TTL
    If l2 cache miss, it will try to obtain a mutex lock, read DB and
    update l1 and l2 caches.
    """
    if timeout is None:
        timeout = DEFAULT_TIMEOUT
    if timeout < MIN_TIMEOUT:
        timeout = MIN_TIMEOUT

    timeout += randrange(30)  # add a random jitter to reduce DB load

    def decorator(f):
        def update_cache(key_l1, key_l2, *args, **kwargs):
            """ Execute f and then update l1 and l2 cache """
            output = f(*args, **kwargs)
            output_bytes = pickle.dumps(output)
            sentinel.master.setex(key_l1, timeout, output_bytes)
            sentinel.master.setex(key_l2, timeout_l2, output_bytes)
            add_key_to_cache_groups(key_l1, cache_group_keys, *args, **kwargs)
            add_key_to_cache_groups(key_l2, cache_group_keys, *args, **kwargs)
            return output

        def update_cache_sync(key_l1, key_l2, *args, **kwargs):
            """ Update l1 and l2 cache synchronously with a mutex lock.
            If the other request is updating, return None """
            lock_name = f"{key_l1}:mutex_lock"
            mutex_lock = sentinel.master.lock(lock_name, timeout_mutex_lock)

            # acquiring a non blocking lock: default is blocking
            lock_success = mutex_lock.acquire(blocking=False)
            if lock_success:
                output = update_cache(key_l1, key_l2, *args, **kwargs)
                try:
                    mutex_lock.release()  # release the lock
                except LockError as e:
                    msg = "Consider to set a longer timeout_mutex_lock value."
                    current_app.logger.info(f"{str(e)}. {msg}")
                finally:
                    return output
            return None

        @wraps(f)
        def wrapper(*args, **kwargs):
            if key_prefix is None:
                key = "%s:%s_args:" % (REDIS_KEYPREFIX, f.__name__)
                key_to_hash = get_key_to_hash(*args, **kwargs)
                key = get_hash_key(key, key_to_hash)
            else:
                key = "%s::%s" % (REDIS_KEYPREFIX, key_prefix)
            key_l2 = f"{key}:l2"

            if os.environ.get('PYBOSSA_REDIS_CACHE_DISABLED') is None:
                output_bytes = sentinel.slave.get(key)  # read l1 cache
                if output_bytes:
                    return pickle.loads(output_bytes)

                # If l1 cache miss, try to read from l2 cache
                output_bytes = sentinel.slave.get(key_l2)

                # If l2 cache has the data
                if output_bytes:
                    # Try to keep the cache up-to-date
                    output = update_cache_sync(key, key_l2, *args, **kwargs)
                    if output:
                        return output

                    # return l2 cache data if the other request is updating data
                    return pickle.loads(output_bytes)

                # If l1 and l2 cache miss: get a mutex lock, then update cache
                output = update_cache_sync(key, key_l2, *args, **kwargs)
                if output:
                    return output

                # output is None, meaning the other request is updating data.
                # Then just keep querying the l2 cache until MUTEX_LOCK_TIMEOUT
                total_retry_time = 0
                while total_retry_time < timeout_mutex_lock:
                    output_bytes = sentinel.slave.get(key_l2)
                    if output_bytes:
                        return pickle.loads(output_bytes)

                    sleep_time = 0.1  # seconds
                    total_retry_time += sleep_time
                    time.sleep(sleep_time)
            output = update_cache(key, key_l2, *args, **kwargs)
            return output
        return wrapper
    return decorator


def delete_cached(key):
    """
    Delete a cached value from the cache.

    Returns True if success or no cache is enabled

    """
    if os.environ.get('PYBOSSA_REDIS_CACHE_DISABLED') is None:
        key = "%s::%s" % (REDIS_KEYPREFIX, key)
        return bool(sentinel.master.delete(key))
    return True


def delete_memoized(function, *args, **kwargs):
    """
    Delete a memoized value from the cache.

    Returns True if success or no cache is enabled

    """
    if os.environ.get('PYBOSSA_REDIS_CACHE_DISABLED') is None:
        key = "%s:%s_args:" % (REDIS_KEYPREFIX, function.__name__)
        if args or kwargs:
            key_to_hash = get_key_to_hash(*args, **kwargs)
            key = get_hash_key(key, key_to_hash)
            return bool(sentinel.master.delete(key))
        keys_to_delete = list(sentinel.slave.scan_iter(match=key + '*', count=10000))
        if not keys_to_delete:
            return False
        return bool(sentinel.master.delete(*keys_to_delete))
    return True


def delete_memoized_essential(function, *args, **kwargs):
    """
    Use the essential arguments list to delete all matching memoized values from the cache.

    Returns True if success or no cache is enabled

    """
    if os.environ.get('PYBOSSA_REDIS_CACHE_DISABLED') is None:
        key = "%s:%s_args:" % (REDIS_KEYPREFIX, function.__name__)
        if args or kwargs:
            key += get_key_to_hash(*args, **kwargs)
        keys_to_delete = list(sentinel.slave.scan_iter(match=key + '*', count=10000))
        if not keys_to_delete:
            return False
        return bool(sentinel.master.delete(*keys_to_delete))
    return True


def delete_memoize_with_l2_cache(function, *args, **kwargs):
    """
    Delete a memoize_with_l2_cache value from the cache.

    Returns True if success or no cache is enabled

    """
    if os.environ.get('PYBOSSA_REDIS_CACHE_DISABLED') is None:
        key = "%s:%s_args:" % (REDIS_KEYPREFIX, function.__name__)
        if args or kwargs:
            key_to_hash = get_key_to_hash(*args, **kwargs)
            key = get_hash_key(key, key_to_hash)
            key_l2 = f"{key}:l2"
            key_deleted = bool(sentinel.master.delete(key))
            key_l2_deleted = bool(sentinel.master.delete(key_l2))
            return key_deleted and key_l2_deleted
        keys_to_delete = list(sentinel.slave.scan_iter(match=key + '*', count=10000))
        if not keys_to_delete:
            return False
        return bool(sentinel.master.delete(*keys_to_delete))
    return True
