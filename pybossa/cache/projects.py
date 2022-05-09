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
"""Cache module for projects."""
from sqlalchemy.sql import text
from pybossa.core import db, timeouts
from pybossa.model.project import Project
from pybossa.util import pretty_date, static_vars, convert_utc_to_est
from pybossa.cache import memoize, cache, delete_memoized, delete_cached, \
    memoize_essentials, delete_memoized_essential, delete_cache_group, ONE_DAY, \
    ONE_HOUR, memoize_with_l2_cache, delete_memoize_with_l2_cache
from pybossa.cache.task_browse_helpers import get_task_filters, allowed_fields, user_meet_task_requirement, get_task_preference_score
import pybossa.app_settings as app_settings
from pybossa.redis_lock import get_locked_tasks_project
from pybossa.util import get_taskrun_date_range_sql_clause_params

import heapq

session = db.slave_session


@cache(timeout=timeouts.get('STATS_FRONTPAGE_TIMEOUT'),
       key_prefix="front_page_top_projects")
def get_top(n=4):
    """Return top n=4 projects with most task runs.
    projects without updating more than 3 months could be ignored, depending on
    whether the project owner is "pro" or not.
    ref:  get_project_jobs in jobs.py
    """
    sql = text('''SELECT p.id, p.name, p.short_name, p.description, p.info, ps.n_task_runs AS total
                FROM project p
                JOIN project_stats ps
                ON p.id = ps.project_id
                ORDER BY ps.n_task_runs DESC
                LIMIT :limit;''')

    results = session.execute(sql, dict(limit=n))
    top_projects = []
    for row in results:
        project = dict(id=row.id, name=row.name, short_name=row.short_name,
                       description=row.description,
                       info=row.info)

        top_projects.append(Project().to_public_json(project))
    return top_projects


@memoize_essentials(timeout=timeouts.get('BROWSE_TASKS_TIMEOUT'), essentials=[0],
                    cache_group_keys=[[0]])
@static_vars(allowed_fields=allowed_fields)
def browse_tasks(project_id, args, filter_user_prefs=False, user_id=None, **kwargs):
    """Cache browse tasks view for a project."""

    sorting = {"lock_status asc": "(coalesce(ct, 0)/float4(task.n_answers)) desc",
               "lock_status desc": "(coalesce(ct, 0)/float4(task.n_answers)) asc"}

    # TODO: use Jinja filters to format date
    def format_date(date):
        if date is not None:
            return convert_utc_to_est(date).strftime('%m-%d-%y %H:%M')

    def format_task(row, lock_users=[]):
        """convert database record to task dictionary and format data."""
        finish_time = format_date(row.ft)
        created = format_date(row.created)
        user_pref = row.user_pref or {}
        task = dict(id=row.id, n_task_runs=row.n_task_runs,
                    n_answers=row.n_answers, priority_0=row.priority_0,
                    finish_time=finish_time, created=created,
                    calibration=row.calibration,
                    userPrefLang=", ".join(user_pref.get("languages", [])),
                    userPrefLoc=", ".join(user_pref.get("locations", [])),
                    lock_users=lock_users,
                    available=False)
        task['pct_status'] = _pct_status(row.n_task_runs, row.n_answers)
        return task

    def search_lock_status_sorting_result():
        tasks = []
        sql_order_by = sorting[order_by]

        # if there are locked tasks in project, need to merge sort locked tasks and unlocked tasks
        # otherwise just sort by pcomplete
        if locked_tasks_in_project:
            locked_tasks = [format_task(row, locked_tasks_in_project.get(row.id, []))
                                for row in session.execute(text(sql+sql_lock_filter), params)]

            if order_by == 'lock_status asc':
                # sort by completed tasks, then incomplete tasks, then locked tasks

                # if current offset is less than number of unlocked tasks
                #   need to query unlocked tasks first, then append locked tasks to fulfill the page size
                # if current offset is more than number of unlocked tasks
                #   should skip all unlocked tasks and partial locked tasks, and present the rest locked tasks
                if offset < total_count - len(locked_tasks):
                    sql_query = sql + sql_unlock_filter + sql_order.format(sql_order_by) + sql_limit_offset
                    results = session.execute(text(sql_query), params)
                else:
                    locked_tasks = locked_tasks[offset-(total_count-len(locked_tasks)):]
                    results = []

                tasks.extend([format_task(row) for row in results])

                # fill up the page size with locked tasks until the page size is reached or exhausted
                tasks.extend(locked_tasks[:limit-len(tasks)])

            else:
                # sort by locked tasks, then incompleted tasks, then completed tasks
                tasks = locked_tasks[offset: offset+limit]

                # if locked tasks is not enough to fulfill the page,
                #   need to append unlocked tasks to get full page size
                #   query additional unlocked tasks and append them
                if len(tasks) < limit:
                    sql_query = sql + sql_unlock_filter + sql_order.format(sql_order_by) + sql_limit_offset
                    params["offset"] = max(params["offset"]-len(locked_tasks), 0)
                    params["limit"] -= len(tasks)
                    results = session.execute(text(sql_query), params)

                    tasks.extend([format_task(row) for row in results])

        return tasks


    order_by = args.get('order_by') or ""
    tasks = []
    total_count = task_count(project_id, args)
    if not total_count:
        return total_count, tasks

    locked_tasks_in_project = {}
    for lock in get_locked_tasks_project(project_id):
        locked_tasks_in_project.setdefault(int(lock["task_id"]), []).append(lock["user_id"])

    args['user_id'] = user_id
    filters, filter_params = get_task_filters(args)
    task_reserve_filter =  args.get("filter_by_wfilter_upref", {}).get("reserve_filter", "")

    params = dict(project_id=project_id, **filter_params)
    limit = args.get('records_per_page') or 10
    offset = args.get('offset') or 0

     # TODO: RDISCROWD-5000
     # refactor code once Task Browse page optimization is settled
    if filter_user_prefs:
        # construct task list for worker view
        sql = """ SELECT task.id,
                (
                    SELECT COUNT(id) as ct FROM task_run
                    WHERE task_id = task.id
                ) as n_task_runs,
                task.n_answers,
                (
                    SELECT MAX(finish_time) as ft FROM task_run
                    WHERE task_id = task.id
                ) as ft,
                priority_0,
                task.created,
                task.calibration,
                task.user_pref,
                task.worker_filter,
                task.worker_pref
                FROM task
                WHERE task.project_id =:project_id"""

        params["assign_user"] = args["sql_params"]["assign_user"]

        all_available_tasks_sql = sql + filters +\
                " ORDER BY %s" % (args.get('order_by') or 'priority_0 desc')
        all_available_tasks = [row for row in session.execute(text(all_available_tasks_sql), params)]

        task_reserve_filter = args.get("filter_by_wfilter_upref", {}).get("reserve_filter", "")
        if task_reserve_filter:
            unreserved_tasks_sql = sql + filters + task_reserve_filter
            unreserved_tasks = session.execute(text(unreserved_tasks_sql), params)
        else:
            unreserved_tasks = all_available_tasks
        unreserved_task_ids = set([row.id for row in unreserved_tasks])

        task_rank_info = []
        user_profile = args.get("filter_by_wfilter_upref", {}).get("current_user_profile", {})

        for row in all_available_tasks:
            score = 0
            w_pref = row.worker_pref or {}
            w_filter = row.worker_filter or {}
            # validate worker_filter and compute preference score
            if not user_meet_task_requirement(row.id, w_filter, user_profile):
                continue
            if not args.get('order_by'):
                # if there is no sort defined, sort task by preference scores
                score = get_task_preference_score(w_pref, user_profile)

            task = format_task(row)
            task_rank_info.append((task, score))

        # get a list of available tasks for current worker
        total_count = len(task_rank_info)
        select_available_tasks(task_rank_info, locked_tasks_in_project,
                                user_id, offset+limit, args.get("order_by"),
                                eligible_tasks=unreserved_task_ids)

        tasks = [t[0] for t in task_rank_info[offset: offset+limit]]

    else:
        # construct task browse page for owners/admins
        session.execute("SET LOCAL enable_indexscan = OFF;")
        sql = """
            SELECT task.id,
            coalesce(ct, 0) as n_task_runs, task.n_answers, ft,
            priority_0, task.created, task.calibration,
            task.user_pref, task.worker_filter, task.worker_pref
            FROM task LEFT OUTER JOIN
            (SELECT task_id, COUNT(id) AS ct,
            MAX(finish_time) as ft FROM task_run
            WHERE project_id=:project_id GROUP BY task_id) AS log_counts
            ON task.id=log_counts.task_id
            WHERE task.project_id=:project_id""" + filters

        locked_task_ids = [lock["task_id"] for lock in get_locked_tasks_project(project_id)]
        sql_lock_filter = " AND id IN ({})".format(",".join(locked_task_ids))
        sql_unlock_filter = " AND id NOT IN ({})".format(",".join(locked_task_ids))
        sql_order = " ORDER BY {} "
        sql_limit_offset = " LIMIT :limit OFFSET :offset "
        params["limit"] = limit
        params["offset"] = offset

        if "lock_status" in order_by:
            tasks = search_lock_status_sorting_result()
        else:
            # if not sort by lock_status, sort by the column "order_by"
            sql_order_by = args.get('order_by') or 'id ASC'
            sql_query = sql + sql_order.format(sql_order_by) + sql_limit_offset

            results = session.execute(text(sql_query), params)
            tasks = [format_task(row, locked_tasks_in_project.get(row.id, [])) for row in results]

        session.execute("RESET enable_indexscan;")

    return total_count, tasks


def select_available_tasks(task_rank_info, locked_tasks, user_id, num_tasks_needed, sort_by=None, eligible_tasks=set()):
    """remove tasks without redundant taskruns,
       disable tasks that had been locked,
       sort tasks based on preference score"""

    # if there is no sort parameter, use preference score to sort tasks
    if not sort_by:
        task_rank_info = heapq.nlargest(num_tasks_needed+len(locked_tasks)+1,
                                        task_rank_info,
                                        key=lambda tup: tup[1])

    for t, _ in task_rank_info:
        remaining = float('inf') if t["calibration"] else t["n_answers"]-t["n_task_runs"]
        # does not show completed tasks to users
        if remaining == 0:
            continue

        # for tasks that are available to contribute, mark available=true
        locked_users = locked_tasks.get(t["id"], [])
        if t["id"] in eligible_tasks and (str(user_id) in locked_users or len(locked_users) < remaining):
            t["available"] = True


def task_count(project_id, args):
    """Return the count of tasks in a project matching the given filters."""
    filters, filter_params = get_task_filters(args)
    sql = text('''
                SELECT COUNT(*) AS total_count
                FROM task WHERE task.id IN
                (
                SELECT task.id FROM task LEFT OUTER JOIN
                    (
                    SELECT task_id, COUNT(id) AS ct,
                    MAX(finish_time) as ft FROM task_run
                    WHERE project_id=:project_id GROUP BY task_id
                    ) AS log_counts
                    ON task.id=log_counts.task_id
                    WHERE task.project_id=:project_id {}
                )
               '''.format(filters))

    results = session.execute(sql, dict(project_id=project_id,
                                        **filter_params))

    row = results.first()
    return row.total_count if row else 0


def _pct_status(n_task_runs, n_answers):
    """Return percentage status."""
    if n_answers != 0 and n_answers is not None:
        if n_task_runs > n_answers:
            return float(1)
        else:
            return float(n_task_runs) / n_answers
    return float(0)


@memoize_with_l2_cache(timeout=ONE_HOUR)
def first_task_id(project_id):
    """Return the oldest task id of a project"""

    # limit 20 is on purpose so that it uses top-N heapsort.
    # Compared to limit 1 or select min(id) from task where project_id=:xxx
    # the following SQL is way faster (10ms vs 8000ms)
    # This kind of trick/optimization should be done by SQL planner/optimizer,
    # not programmers. We might need to consider upgrading postgresql engine
    sql = text('''
        SELECT MIN(id) AS first_task_id FROM
        (SELECT id FROM task WHERE project_id=:project_id ORDER BY id limit 20)
        AS ids;
                ''')

    return session.scalar(sql, dict(project_id=project_id)) or 0


@memoize(timeout=timeouts.get('APP_TIMEOUT'), cache_group_keys=[[0]])
def n_tasks(project_id):
    """Return number of tasks of a project."""
    sql = text('''SELECT COUNT(task.id) AS n_tasks FROM task
                  WHERE task.project_id=:project_id;''')
    results = session.execute(sql, dict(project_id=project_id))
    n_tasks = 0
    for row in results:
        n_tasks = row.n_tasks
    return n_tasks


@memoize(timeout=timeouts.get('APP_TIMEOUT'), cache_group_keys=[[0]])
def n_tasks_not_gold(project_id):
    """Return number of tasks of a project that are not gold."""
    sql = text('''SELECT COUNT(task.id) AS n_tasks FROM task
                  WHERE task.project_id=:project_id AND calibration != 1;''')
    results = session.execute(sql, dict(project_id=project_id))
    n_tasks = 0
    for row in results:
        n_tasks = row.n_tasks
    return n_tasks


@memoize(timeout=timeouts.get('APP_TIMEOUT'), cache_group_keys=[[0]])
def n_completed_tasks(project_id):
    """Return number of completed tasks of a project."""
    sql = text('''SELECT COUNT(task.id) AS n_completed_tasks FROM task
                WHERE task.project_id=:project_id AND task.state=\'completed\';
                ''')

    results = session.execute(sql, dict(project_id=project_id))
    n_completed_tasks = 0
    for row in results:
        n_completed_tasks = row.n_completed_tasks
    return n_completed_tasks


@memoize(timeout=timeouts.get('APP_TIMEOUT'), cache_group_keys=[[0]])
def n_results(project_id):
    """Return number of results of a project."""
    return 0

    query = text('''
                 SELECT COUNT(id) AS ct FROM result
                 WHERE project_id=:project_id
                 AND info IS NOT NULL
                 AND cast(info AS TEXT) != 'null'
                 AND cast(info AS TEXT) != '';
                 ''')
    results = session.execute(query, dict(project_id=project_id))
    n_results = 0
    for row in results:
        n_results = row.ct
    return n_results


@memoize(timeout=timeouts.get('REGISTERED_USERS_TIMEOUT'), cache_group_keys=[[0]])
def n_registered_volunteers(project_id):
    """Return number of registered users that have participated in a project."""
    sql = text('''SELECT COUNT(DISTINCT(task_run.user_id))
               AS n_registered_volunteers FROM task_run
               WHERE task_run.user_id IS NOT NULL AND
               task_run.user_ip IS NULL AND
               task_run.project_id=:project_id;''')

    results = session.execute(sql, dict(project_id=project_id))
    n_registered_volunteers = 0
    for row in results:
        n_registered_volunteers = row.n_registered_volunteers
    return n_registered_volunteers


@memoize(timeout=timeouts.get('ANON_USERS_TIMEOUT'), cache_group_keys=[[0]])
def n_anonymous_volunteers(project_id):
    """Return number of anonymous users that have participated in a project."""
    sql = text('''SELECT COUNT(DISTINCT(task_run.user_ip))
               AS n_anonymous_volunteers FROM task_run
               WHERE task_run.user_ip IS NOT NULL AND
               task_run.user_id IS NULL AND
               task_run.project_id=:project_id;''')

    results = session.execute(sql, dict(project_id=project_id))
    n_anonymous_volunteers = 0
    for row in results:
        n_anonymous_volunteers = row.n_anonymous_volunteers
    return n_anonymous_volunteers


def n_volunteers(project_id):
    """Return total number of volunteers of a project."""
    total = n_registered_volunteers(project_id)
    if not app_settings.config.get('DISABLE_ANONYMOUS_ACCESS'):
        total += n_anonymous_volunteers(project_id)
    return total


@memoize(timeout=timeouts.get('APP_TIMEOUT'), cache_group_keys=[[0]])
def n_task_runs(project_id):
    """Return number of task_runs of a project."""
    sql = text('''SELECT COUNT(task_run.id) AS n_task_runs FROM task_run
                  WHERE task_run.project_id=:project_id''')

    results = session.execute(sql, dict(project_id=project_id))
    n_task_runs = 0
    for row in results:
        n_task_runs = row.n_task_runs
    return n_task_runs


@memoize(timeout=timeouts.get('APP_TIMEOUT'), cache_group_keys=[[0]])
def n_remaining_task_runs(project_id):
    """Return total number of tasks runs currently remaining for a project."""
    sql = text('''SELECT SUM(task.n_answers - COALESCE(t.actual_answers, 0))
                  FROM task
                  LEFT JOIN (SELECT task_id, COUNT(id) AS actual_answers
                             FROM task_run WHERE project_id=:project_id
                             GROUP BY task_id) AS t
                  ON task.id = t.task_id
                  WHERE task.project_id=:project_id
                  AND calibration = 0
                  AND task.state = 'ongoing';''')
    return session.execute(sql, dict(project_id=project_id)).scalar() or 0


def n_expected_task_runs(project_id):
    """Return total number of expected task_runs of a project (exclude gold task)."""
    sql = text('''SELECT SUM(n_answers) AS n_task_runs FROM task
                  WHERE project_id=:project_id
                  AND calibration = 0;''')

    results = session.execute(sql, dict(project_id=project_id))
    n_task_runs = 0
    for row in results:
        n_task_runs = row.n_task_runs
    return n_task_runs


def overall_progress(project_id):
    """Return the percentage of completed tasks out of non gold tasks for a project."""
    total_tasks = n_tasks_not_gold(project_id)
    return ((n_completed_tasks(project_id) * 100) // total_tasks) if total_tasks != 0 else 0


@memoize_with_l2_cache(timeout=timeouts.get('APP_TIMEOUT'), cache_group_keys=[[0]])
def last_activity(project_id):
    """Return last activity, date, from a project."""
    sql = text('''SELECT finish_time FROM task_run WHERE project_id=:project_id
               ORDER BY finish_time DESC LIMIT 1''')

    results = session.execute(sql, dict(project_id=project_id))
    for row in results:
        if row is not None:
            return row[0]
        else:  # pragma: no cover
            return None


@memoize(timeout=timeouts.get('APP_TIMEOUT'))
def average_contribution_time(project_id):
    sql = text('''SELECT
        AVG(to_timestamp(finish_time, 'YYYY-MM-DD"T"HH24-MI-SS.US') -
            to_timestamp(created, 'YYYY-MM-DD"T"HH24-MI-SS.US')) AS average_time
        FROM task_run
        WHERE project_id=:project_id;''')

    results = session.execute(sql, dict(project_id=project_id)).fetchall()
    for row in results:
        average_time = row.average_time
    if average_time:
        return average_time.total_seconds()
    else:
        return 0


def n_blogposts(project_id):
    """Return number of blogposts of a project."""
    sql = text('''
               SELECT COUNT(id) as ct from blogpost
               WHERE project_id=:project_id;
               ''')
    results = session.execute(sql, dict(project_id=project_id))
    n_blogposts = 0
    for row in results:
        n_blogposts = row.ct
    return n_blogposts


# This function does not change too much, so cache it for a longer time
@cache(timeout=timeouts.get('STATS_FRONTPAGE_TIMEOUT'),
       key_prefix="number_featured_projects")
def _n_featured():
    """Return number of featured projects."""
    sql = text('''SELECT COUNT(*) FROM project WHERE featured=true;''')

    results = session.execute(sql)
    for row in results:
        count = row[0]
    return count


# This function does not change too much, so cache it for a longer time
@memoize(timeout=timeouts.get('STATS_FRONTPAGE_TIMEOUT'))
def get_all_featured(category=None):
    """Return a list of featured projects with a pagination."""
    sql = text(
        '''SELECT project.id, project.name, project.short_name, project.info,
               project.created, project.updated, project.description,
               "user".fullname AS owner
           FROM project, "user"
           WHERE project.featured=true
           AND "user".id=project.owner_id
           AND "user".restrict=false
           GROUP BY project.id, "user".id;''')

    results = session.execute(sql)
    projects = []
    for row in results:
        project = dict(id=row.id, name=row.name, short_name=row.short_name,
                       created=row.created, description=row.description,
                       updated=row.updated,
                       last_activity=pretty_date(last_activity(row.id)),
                       last_activity_raw=last_activity(row.id),
                       owner=row.owner,
                       overall_progress=overall_progress(row.id),
                       n_tasks=n_tasks(row.id),
                       n_volunteers=n_volunteers(row.id),
                       info=row.info)
        projects.append(Project().to_public_json(project))
    return projects


def get_featured(category=None, page=1, per_page=5):
    """Return a list of featured project with a pagination."""
    offset = (page - 1) * per_page
    return get_all_featured()[offset:offset+per_page]


@cache(key_prefix="number_published_projects",
       timeout=timeouts.get('STATS_APP_TIMEOUT'))
def n_published():
    """Return number of published projects."""
    sql = text('''SELECT COUNT(id) FROM project WHERE published=true;''')

    results = session.execute(sql)
    for row in results:
        count = row[0]
    return count


# Cache it for longer times, as this is only shown to admin users
@cache(timeout=timeouts.get('STATS_DRAFT_TIMEOUT'),
       key_prefix="number_draft_projects")
def _n_draft():
    """Return number of draft projects."""
    sql = text('''SELECT COUNT(id) FROM project WHERE published=false;''')

    results = session.execute(sql)
    for row in results:
        count = row[0]
    return count


@memoize(timeout=timeouts.get('STATS_FRONTPAGE_TIMEOUT'), cache_group_keys=['get_all_draft',])
def get_all_draft(category=None):
    """Return list of all draft projects."""
    sql = text(
        '''SELECT project.id, project.name, project.short_name, project.created,
            project.description, project.info, project.updated,
            "user".fullname AS owner
           FROM "user", project
           WHERE project.owner_id="user".id
           AND "user".restrict=false
           AND project.published=false;''')

    results = session.execute(sql)
    projects = []
    for row in results:
        project = dict(id=row.id, name=row.name, short_name=row.short_name,
                       created=row.created,
                       updated=row.updated,
                       description=row.description,
                       owner=row.owner,
                       last_activity=pretty_date(last_activity(row.id)),
                       last_activity_raw=last_activity(row.id),
                       overall_progress=overall_progress(row.id),
                       n_tasks=n_tasks(row.id),
                       n_volunteers=n_volunteers(row.id),
                       info=row.info)
        projects.append(Project().to_public_json(project))
    return projects


def get_draft(category=None, page=1, per_page=5):
    """Return a list of draft project with a pagination."""
    offset = (page - 1) * per_page
    return get_all_draft()[offset:offset+per_page]


@memoize(timeout=timeouts.get('N_APPS_PER_CATEGORY_TIMEOUT'), cache_group_keys=[[0]])
def n_count(category):
    """Count the number of projects in a given category."""
    if category == 'featured':
        return _n_featured()
    if category == 'draft':
        return _n_draft()
    sql = text('''
               WITH uniq AS (
               SELECT COUNT(project.id) FROM project
               LEFT OUTER JOIN category ON project.category_id=category.id
               WHERE
               category.short_name=:category
               AND project.published=true
               AND coalesce(project.hidden, false)=false
               GROUP BY project.id)
               SELECT COUNT(*) FROM uniq
               ''')

    results = session.execute(sql, dict(category=category))
    count = 0
    for row in results:
        count = row[0]
    return count


@memoize(timeout=timeouts.get('APP_TIMEOUT'), cache_group_keys=[[0]])
def get_all(category):
    """Return a list of published projects for a given category.
    """
    sql = text(
        '''SELECT project.id, project.name, project.short_name,
           project.description, project.info, project.created, project.updated,
           project.category_id, project.featured, "user".fullname AS owner
           FROM "user", project
           LEFT OUTER JOIN category ON project.category_id=category.id
           WHERE
           category.short_name=:category
           AND "user".id=project.owner_id
           AND "user".restrict=false
           AND project.published=true
           AND coalesce(project.hidden, false)=false
           GROUP BY project.id, "user".id ORDER BY project.name;''')

    results = session.execute(sql, dict(category=category))
    projects = []
    for row in results:
        project = dict(id=row.id,
                       name=row.name, short_name=row.short_name,
                       created=row.created,
                       updated=row.updated,
                       description=row.description,
                       owner=row.owner,
                       featured=row.featured,
                       last_activity=pretty_date(last_activity(row.id)),
                       last_activity_raw=last_activity(row.id),
                       overall_progress=overall_progress(row.id),
                       n_tasks=n_tasks(row.id),
                       n_volunteers=n_volunteers(row.id),
                       info=row.info)
        projects.append(Project().to_public_json(project))
    return projects


def get(category, page=1, per_page=5):
    """Return a list of published projects with a pagination for a given category.
    """
    offset = (page - 1) * per_page
    return get_all(category)[offset:offset + per_page]


@memoize_with_l2_cache(timeout=timeouts.get('APP_TIMEOUT'))
def get_from_pro_user():
    """Return the list of published projects belonging to 'pro' users."""
    sql = text('''SELECT project.id, project.short_name FROM project, "user"
               WHERE project.owner_id="user".id AND "user".pro=True and project.published=True;''')
    results = db.slave_session.execute(sql)
    projects = []
    for row in results:
        project = dict(id=row.id, short_name=row.short_name)
        projects.append(project)
    return projects


@memoize(timeout=ONE_DAY)
def get_recently_updated_projects():
    """Return the list of projects that has task creations in last 3 months.
    "updated" column in the project table get updated when new tasks are created,
    new task runs submitted, task setting updated, project updated and etc.
    ref: model/event_listener.py:update_project
    """

    # Including unpublished projects so that project_stats data is more accurate
    sql = text('''
               SELECT id, short_name FROM project
               WHERE TO_DATE(updated, 'YYYY-MM-DD"T"HH24:MI:SS.US') >= NOW() - '3 months' :: INTERVAL;
               ''')

    results = db.slave_session.execute(sql)
    projects = []
    for row in results:
        project = dict(id=row.id, short_name=row.short_name)
        projects.append(project)
    return projects


@memoize(timeout=timeouts.get('APP_TIMEOUT'))
def get_all_projects():
    """Return a list of published projects short_names.
    """
    sql = text(
        '''SELECT name, short_name FROM project
           WHERE project.published=true
           ORDER BY project.short_name;''')

    results = session.execute(sql)
    projects = []
    for row in results:
        project = dict(name=row.name, short_name=row.short_name)
        projects.append(project)
    return projects


@memoize(timeout=60 * 2)
def text_search(search_text, show_unpublished=True, show_hidden=True):
    """Return a list of published projects short_names.
    """
    sql = text(
        '''SELECT project.id, project.name, project.short_name,
        project.description, project.info, project.created, project.updated,
        project.category_id, project.featured, "user".fullname AS owner
        FROM project
        LEFT JOIN "user" ON project.owner_id="user".id
        WHERE
        (project.name ILIKE '%' || :search_text || '%'
         OR "user".fullname ILIKE '%' || :search_text || '%'
         OR project.description ILIKE '%' || :search_text || '%')
         {}
         {}
        ORDER BY project.name;'''.format(
          'AND project.published=true' if not show_unpublished else '',
          'AND coalesce(project.hidden, false)=false' if not show_hidden else ''))
    results = session.execute(sql, dict(search_text=search_text))
    projects = []
    for row in results:
        project = dict(id=row.id,
                       name=row.name, short_name=row.short_name,
                       created=row.created,
                       updated=row.updated,
                       description=row.description,
                       owner=row.owner,
                       featured=row.featured,
                       last_activity=pretty_date(last_activity(row.id)),
                       last_activity_raw=last_activity(row.id),
                       overall_progress=overall_progress(row.id),
                       n_tasks=n_tasks(row.id),
                       n_volunteers=n_volunteers(row.id),
                       info=row.info)
        projects.append(Project().to_public_json(project))
    return projects


@memoize(timeout=timeouts.get('APP_TIMEOUT'))
def n_total_tasks():
    """Return number of tasks from published project."""
    sql = text('''SELECT COUNT(task.id) AS n_total_tasks
                FROM task JOIN project
                ON task.project_id = project.id
                WHERE project.published=true;''')
    results = session.execute(sql)
    n_total_tasks = 0
    for row in results:
        n_total_tasks = row.n_total_tasks
    return n_total_tasks


@memoize(timeout=timeouts.get('APP_TIMEOUT'))
def get_project_scheduler(project_id):
    """Return type of scheduler for a given project"""
    sql = text('''SELECT info->'sched' FROM project
                WHERE id=:project_id;
                ''')

    return session.scalar(sql, dict(project_id=project_id)) or 'default'


@memoize(timeout=timeouts.get('APP_TIMEOUT'))
def get_project_data(project_id):
    """Return the short_name for a given project"""
    sql = text('''SELECT id, short_name, info, owners_ids FROM project
                WHERE id=:project_id;''')

    return session.execute(sql, dict(project_id=project_id)).first()


def reset():
    """Clean the cache"""
    delete_cached('front_page_top_projects')
    delete_cached('number_featured_projects')
    delete_cached('number_published_projects')
    delete_cached('number_draft_projects')
    delete_memoized(get_all_projects)
    delete_memoized(get_all_featured)
    delete_memoized(get_all_draft)
    delete_memoized(text_search)
    delete_memoized(n_total_tasks)
    delete_memoized(n_count)
    delete_memoized(get_all)
    delete_memoize_with_l2_cache(first_task_id)
    delete_memoize_with_l2_cache(get_from_pro_user)


def delete_browse_tasks(project_id):
    """Reset browse_tasks value in cache"""
    delete_memoized_essential(browse_tasks, project_id)


def delete_n_tasks(project_id):
    """Reset n_tasks value in cache"""
    delete_memoized(n_tasks, project_id)


def delete_n_results(project_id):
    """Reset n_results value in cache"""
    delete_memoized(n_results, project_id)


def delete_n_completed_tasks(project_id):
    """Reset n_completed_tasks value in cache"""
    delete_memoized(n_completed_tasks, project_id)


def delete_n_task_runs(project_id):
    """Reset n_tasks value in cache"""
    delete_memoized(n_task_runs, project_id)


def delete_overall_progress(project_id):
    """Reset overall_progress value in cache"""
    delete_memoized(overall_progress, project_id)


def delete_last_activity(project_id):
    """Reset last_activity value in cache"""
    delete_memoize_with_l2_cache(last_activity, project_id)


def delete_n_registered_volunteers(project_id):
    """Reset n_registered_volunteers value in cache"""
    delete_memoized(n_registered_volunteers, project_id)


def delete_n_anonymous_volunteers(project_id):
    """Reset n_anonymous_volunteers value in cache"""
    delete_memoized(n_anonymous_volunteers, project_id)


def delete_n_volunteers(project_id):
    """Reset n_volunteers value in cache"""
    delete_memoized(n_volunteers, project_id)


def clean(project_id):
    """Clean all items in cache"""
    reset()
    clean_project(project_id)


def clean_project(project_id, category=None):
    """Clean cache for a specific project"""
    project = db.session.query(Project).get(project_id)
    delete_cache_group(project_id)
    if project:
        delete_cache_group(project.category.short_name)
        delete_cache_group('get_all_draft')


@memoize(timeout=timeouts.get('APP_TIMEOUT'))
def get_project_report_projectdata(project_id, start_date, end_date):
    """Return data to build project report"""
    date_clause, sql_params = get_taskrun_date_range_sql_clause_params(start_date, end_date)
    sql_params["project_id"] = project_id
    sql = text(
            '''
            SELECT id, name, short_name,
            (SELECT COUNT(id) FROM task WHERE project_id = p.id) AS total_tasks,
            (SELECT MIN(finish_time) FROM task_run WHERE project_id = p.id''' + date_clause +''') AS first_task_submission,
            (SELECT MAX(finish_time) FROM task_run WHERE project_id = p.id''' + date_clause +''') AS last_task_submission,
            (SELECT MAX(n_answers) FROM task WHERE project_id = p.id) AS redundancy,
            (SELECT coalesce(AVG(to_timestamp(finish_time, 'YYYY-MM-DD"T"HH24-MI-SS.US') -
            to_timestamp(created, 'YYYY-MM-DD"T"HH24-MI-SS.US')), interval '0s') FROM task_run WHERE project_id=p.id''' + date_clause +''')
            AS average_time
            FROM project p
            WHERE p.id=:project_id;
            ''')
    results = session.execute(sql, sql_params)
    project_data = []
    for row in results:
        project_data.extend((project_id, row.name, row.short_name, row.total_tasks,
            row.first_task_submission, row.last_task_submission,
            round(row.average_time.total_seconds()/60,2), row.redundancy))
    return project_data
