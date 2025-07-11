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
"""Jobs module for running background tasks in PYBOSSA server."""
import json
import math
import os
import time
from collections import OrderedDict
from datetime import datetime, timedelta
from io import BytesIO
from zipfile import ZipFile

import pandas as pd
import requests
from flask import current_app, render_template
from flask_mail import Message, Attachment
from rq.timeouts import JobTimeoutException
from sqlalchemy.sql import text

import pybossa.app_settings as app_settings
import pybossa.cache.users as cached_users
import pybossa.dashboard.jobs as dashboard
from pybossa.auditlogger import AuditLogger
from pybossa.cache import site_stats
from pybossa.cache.helpers import n_available_tasks
from pybossa.cache.users import get_users_for_report
from pybossa.cloud_store_api.connection import create_connection
from pybossa.core import mail, task_repo, importer
from pybossa.core import user_repo, auditlog_repo
from pybossa.leaderboard.jobs import leaderboard
from pybossa.model.webhook import Webhook
from pybossa.util import with_cache_disabled, publish_channel, \
    mail_with_enabled_users
from pybossa.core import email_service
from pybossa.cloud_store_api.s3 import upload_email_attachment

MINUTE = 60
IMPORT_TASKS_TIMEOUT = (20 * MINUTE)
TASK_DELETE_TIMEOUT = (60 * MINUTE)
EXPORT_TASKS_TIMEOUT = (20 * MINUTE)
MAX_RECIPIENTS = 50
BATCH_DELETE_TASK_DELAY = 2 # seconds
BATCH_SIZE_BULK_DELETE_TASKS = 100
MAX_BULK_DELETE_TASK_ITERATIONS = 1000

from pybossa.exporter.json_export import JsonExporter

auditlogger = AuditLogger(auditlog_repo, caller='web')

DUMMY_ENVIRON = {'wsgi.url_scheme': "", 'SERVER_PORT': "", 'SERVER_NAME': "", 'REQUEST_METHOD': ""}


def schedule_job(function, scheduler):
    """Schedule a job and return a log message."""
    scheduled_jobs = scheduler.get_jobs()
    for sj in scheduled_jobs:
        if (function['name'].__name__ in sj.description and
            sj.args == function['args'] and
                sj.kwargs == function['kwargs']):
            sj.cancel()
            msg = ('WARNING: Job %s(%s, %s) is already scheduled'
                   % (function['name'].__name__, function['args'],
                      function['kwargs']))
            return msg
    # If job was scheduled, it exists up here, else it continues
    scheduler.schedule(
        scheduled_time=(function.get('scheduled_time') or datetime.utcnow()),
        func=function['name'],
        args=function['args'],
        kwargs=function['kwargs'],
        interval=function['interval'],
        repeat=None,
        timeout=function['timeout'])

    msg = ('Scheduled %s(%s, %s) to run every %s seconds'
           % (function['name'].__name__, function['args'], function['kwargs'],
              function['interval']))
    return msg


def get_quarterly_date(now):
    """Get quarterly date."""
    if not isinstance(now, datetime):
        raise TypeError('Expected %s, got %s' % (type(datetime), type(now)))
    execute_month = int(math.ceil(now.month / 3.0) * 3)
    execute_day = 31 if execute_month in [3, 12] else 30
    execute_date = datetime(now.year, execute_month, execute_day)
    return datetime.combine(execute_date, now.time())


def get_saturday_4pm_date(now):
    """Get weekend date Saturday 4pm for weekly execution jobs."""
    if not isinstance(now, datetime):
        raise TypeError('Expected %s, got %s' % (type(datetime), type(now)))
    # Mon - 0, Tue - 1, Wed - 2, Thurs - 3, Fri - 4, Sat - 5, Sun - 6
    SATURDAY = 5
    DAYS_IN_WEEK = 7
    offset = (SATURDAY - now.weekday()) % DAYS_IN_WEEK
    saturday = now + timedelta(days=offset)
    saturday = saturday.strftime('%Y-%m-%dT16:00:00')
    saturday = datetime.strptime(saturday, '%Y-%m-%dT%H:%M:%S')
    return saturday


def enqueue_job(job):
    """Enqueues a job."""
    from pybossa.core import sentinel
    from rq import Queue
    redis_conn = sentinel.master
    queue = Queue(job['queue'], connection=redis_conn)
    queue.enqueue_call(func=job['name'],
                       args=job['args'],
                       kwargs=job['kwargs'],
                       timeout=job['timeout'])
    return True

def enqueue_periodic_jobs(queue_name):
    """Enqueue all PYBOSSA periodic jobs."""
    from pybossa.core import sentinel
    from rq import Queue
    redis_conn = sentinel.master

    jobs_generator = get_periodic_jobs(queue_name)
    n_jobs = 0
    queue = Queue(queue_name, connection=redis_conn)
    for job in jobs_generator:
        if (job['queue'] == queue_name):
            n_jobs += 1
            queue.enqueue_call(func=job['name'],
                               args=job['args'],
                               kwargs=job['kwargs'],
                               timeout=job['timeout'])
    msg = "%s jobs in %s have been enqueued" % (n_jobs, queue_name)
    return msg


def get_periodic_jobs(queue):
    """Return a list of periodic jobs for a given queue."""
    # A job is a dict with the following format: dict(name, args, kwargs,
    # timeout, queue)
    # Default ones
    jobs = get_default_jobs()
    # Admin jobs
    admin_report_jobs = get_weekly_admin_report_jobs() if queue == 'low' else []
    # Based on type of user
    project_jobs = get_project_jobs(queue) if queue in ('super', 'high') else []
    autoimport_jobs = get_autoimport_jobs() if queue == 'low' else []
    # User engagement jobs
    engage_jobs = get_inactive_users_jobs() if queue == 'quaterly' else []
    non_contrib_jobs = get_non_contributors_users_jobs() \
        if queue == 'quaterly' else []
    dashboard_jobs = get_dashboard_jobs() if queue == 'low' else []
    leaderboard_jobs = get_leaderboard_jobs() if queue == 'super' else []
    weekly_update_jobs = get_weekly_stats_update_projects() if queue == 'low' else []
    failed_jobs = get_maintenance_jobs() if queue == 'maintenance' else []
    # completed_tasks_cleanup_job = get_completed_tasks_cleaup_jobs() if queue == 'weekly' else [] # TODO: uncomment in future PR
    _all = [jobs, admin_report_jobs, project_jobs, autoimport_jobs,
            engage_jobs, non_contrib_jobs, dashboard_jobs,
            weekly_update_jobs, failed_jobs, leaderboard_jobs]
    return (job for sublist in _all for job in sublist if job['queue'] == queue)


def get_default_jobs():  # pragma: no cover
    """Return default jobs."""
    timeout = current_app.config.get('TIMEOUT')
    unpublish_projects = current_app.config.get('UNPUBLISH_PROJECTS')
    yield dict(name=warm_up_stats, args=[], kwargs={},
               timeout=timeout, queue='high')
    if unpublish_projects:
        yield dict(name=warn_old_project_owners, args=[], kwargs={},
                   timeout=timeout, queue='low')
    yield dict(name=warm_cache, args=[], kwargs={},
               timeout=2*timeout, queue='super')
    yield dict(name=news, args=[], kwargs={},
               timeout=timeout, queue='low')
    yield dict(name=disable_users_job, args=[],kwargs={},
               timeout=timeout, queue='low')
    yield dict(name=send_email_notifications, args=[], kwargs={},
               timeout=timeout, queue='super')


def get_maintenance_jobs():
    """Return mantainance jobs."""
    timeout = current_app.config.get('TIMEOUT')
    yield dict(name=check_failed, args=[], kwargs={},
               timeout=timeout, queue='maintenance')


def get_export_task_jobs(queue):
    """Export tasks to zip."""
    from pybossa.core import project_repo
    import pybossa.cache.projects as cached_projects
    from pybossa.pro_features import ProFeatureHandler
    feature_handler = ProFeatureHandler(current_app.config.get('PRO_FEATURES'))
    timeout = current_app.config.get('TIMEOUT')
    if feature_handler.only_for_pro('updated_exports'):
        if queue == 'high':
            projects = cached_projects.get_from_pro_user()
        else:
            projects = (p.dictize() for p in project_repo.filter_by(published=True)
                        if p.owner.pro is False)
    else:
        projects = (p.dictize() for p in project_repo.filter_by(published=True))
    for project in projects:
        project_id = project.get('id')
        job = dict(name=project_export,
                   args=[project_id], kwargs={},
                   timeout=timeout,
                   queue=queue)
        yield job


def project_export(_id):
    """Export project."""
    from pybossa.core import project_repo, json_exporter, csv_exporter
    app = project_repo.get(_id)
    if app is not None:
        # print "Export project id %d" % _id
        json_exporter.pregenerate_zip_files(app)
        csv_exporter.pregenerate_zip_files(app)


def get_project_jobs(queue):
    """Return a list of jobs based on user type."""
    from pybossa.cache import projects as cached_projects
    timeout = current_app.config.get('TIMEOUT')
    if queue == 'super':
        projects = cached_projects.get_from_pro_user()
    elif queue == 'high':
        projects = cached_projects.get_recently_updated_projects()
    else:
        projects = []
    for project in projects:
        project_id = project.get('id')
        project_short_name = project.get('short_name')
        job = dict(name=get_project_stats,
                   args=[project_id, project_short_name], kwargs={},
                   timeout=timeout,
                   queue=queue)
        yield job


def create_dict_jobs(data, function, timeout, queue='low'):
    """Create a dict job."""
    for d in data:
        jobs = dict(name=function,
                    args=[d['id'], d['short_name']], kwargs={},
                    timeout=timeout,
                    queue=queue)
        yield jobs


def get_inactive_users_jobs(queue='quaterly'):
    """Return a list of inactive users that have contributed to a project."""
    from sqlalchemy.sql import text
    from pybossa.model.user import User
    from pybossa.core import db
    # First users that have participated once but more than 3 months ago
    sql = text('''SELECT user_id FROM task_run
               WHERE user_id IS NOT NULL
               AND to_date(task_run.finish_time, 'YYYY-MM-DD\THH24:MI:SS.US')
               >= NOW() - '12 month'::INTERVAL
               AND to_date(task_run.finish_time, 'YYYY-MM-DD\THH24:MI:SS.US')
               < NOW() - '3 month'::INTERVAL
               GROUP BY user_id ORDER BY user_id;''')
    results = db.slave_session.execute(sql)

    timeout = current_app.config.get('TIMEOUT')

    for row in results:

        user = User.query.get(row.user_id)

        if user.subscribed and user.restrict is False:
            subject = "We miss you!"
            body = render_template('/account/email/inactive.md',
                                   user=user.dictize(),
                                   config=current_app.config)
            html = render_template('/account/email/inactive.html',
                                   user=user.dictize(),
                                   config=current_app.config)

            mail_dict = dict(recipients=[user.email_addr],
                             subject=subject,
                             body=body,
                             html=html)

            job = dict(name=send_mail,
                       args=[mail_dict],
                       kwargs={},
                       timeout=timeout,
                       queue=queue)
            yield job


def get_dashboard_jobs(queue='low'):  # pragma: no cover
    """Return dashboard jobs."""
    timeout = current_app.config.get('TIMEOUT')
    yield dict(name=dashboard.active_users_week, args=[], kwargs={},
               timeout=timeout, queue=queue)
    yield dict(name=dashboard.active_anon_week, args=[], kwargs={},
               timeout=timeout, queue=queue)
    yield dict(name=dashboard.draft_projects_week, args=[], kwargs={},
               timeout=timeout, queue=queue)
    yield dict(name=dashboard.published_projects_week, args=[], kwargs={},
               timeout=timeout, queue=queue)
    yield dict(name=dashboard.update_projects_week, args=[], kwargs={},
               timeout=timeout, queue=queue)
    yield dict(name=dashboard.new_tasks_week, args=[], kwargs={},
               timeout=timeout, queue=queue)
    yield dict(name=dashboard.new_task_runs_week, args=[], kwargs={},
               timeout=timeout, queue=queue)
    yield dict(name=dashboard.new_users_week, args=[], kwargs={},
               timeout=timeout, queue=queue)
    yield dict(name=dashboard.returning_users_week, args=[], kwargs={},
               timeout=timeout, queue=queue)


def get_leaderboard_jobs(queue='super'):  # pragma: no cover
    """Return leaderboard jobs."""
    timeout = current_app.config.get('TIMEOUT')
    leaderboards = current_app.config.get('LEADERBOARDS')
    if leaderboards:
        for leaderboard_key in leaderboards:
            yield dict(name=leaderboard, args=[], kwargs={'info': leaderboard_key},
                       timeout=timeout, queue=queue)
    yield dict(name=leaderboard, args=[], kwargs={},
               timeout=timeout, queue=queue)


def get_non_contributors_users_jobs(queue='quaterly'):
    """Return a list of users that have never contributed to a project."""
    from sqlalchemy.sql import text
    from pybossa.model.user import User
    from pybossa.core import db
    # Second users that have created an account but never participated
    sql = text('''SELECT id FROM "user" WHERE
               NOT EXISTS (SELECT user_id FROM task_run
               WHERE task_run.user_id="user".id)''')
    results = db.slave_session.execute(sql)
    timeout = current_app.config.get('TIMEOUT')
    for row in results:
        user = User.query.get(row.id)

        if (user.subscribed and user.restrict is False):
            subject = "Why don't you help us?!"
            body = render_template('/account/email/noncontributors.md',
                                   user=user.dictize(),
                                   config=current_app.config)
            html = render_template('/account/email/noncontributors.html',
                                   user=user.dictize(),
                                   config=current_app.config)
            mail_dict = dict(recipients=[user.email_addr],
                             subject=subject,
                             body=body,
                             html=html)

            job = dict(name=send_mail,
                       args=[mail_dict],
                       kwargs={},
                       timeout=timeout,
                       queue=queue)
            yield job


def get_autoimport_jobs(queue='low'):
    """Get autoimport jobs."""
    from pybossa.core import project_repo
    import pybossa.cache.projects as cached_projects
    from pybossa.pro_features import ProFeatureHandler
    feature_handler = ProFeatureHandler(current_app.config.get('PRO_FEATURES'))

    timeout = current_app.config.get('TIMEOUT')

    if feature_handler.only_for_pro('autoimporter'):
        projects = cached_projects.get_from_pro_user()
    else:
        projects = (p.dictize() for p in project_repo.get_all())
    for project_dict in projects:
        project = project_repo.get(project_dict['id'])
        if project.has_autoimporter():
            job = dict(name=import_tasks,
                       args=[project.id, True],
                       kwargs=project.get_autoimporter(),
                       timeout=timeout,
                       queue=queue)
            yield job


# The following are the actual jobs (i.e. tasks performed in the background)

@with_cache_disabled
def get_project_stats(_id, short_name):  # pragma: no cover
    """Get stats for project."""
    with current_app.request_context(DUMMY_ENVIRON):
        import pybossa.cache.project_stats as stats

        # cached_projects.get_project(short_name)
        stats.update_stats(_id)


@with_cache_disabled
def warm_up_stats():  # pragma: no cover
    """Background job for warming stats."""
    # print "Running on the background warm_up_stats"
    from pybossa.cache.site_stats import (n_auth_users, n_anon_users,
                                          n_tasks_site, n_total_tasks_site,
                                          n_task_runs_site,
                                          get_top5_projects_24_hours,
                                          get_top5_users_24_hours)
    current_app.logger.info('warm_up_stats - n_auth_users')
    n_auth_users()
    if not app_settings.config.get('DISABLE_ANONYMOUS_ACCESS'):
        n_anon_users()
    current_app.logger.info('warm_up_stats - n_tasks_site')
    n_tasks_site()
    current_app.logger.info('warm_up_stats - n_total_tasks_site')
    n_total_tasks_site()
    current_app.logger.info('warm_up_stats - n_task_runs_site')
    n_task_runs_site()
    current_app.logger.info('warm_up_stats - get_top5_projects_24_hours')
    get_top5_projects_24_hours()
    current_app.logger.info('warm_up_stats - get_top5_users_24_hours')
    get_top5_users_24_hours()

    return True


@with_cache_disabled
def warm_cache():  # pragma: no cover
    """Background job to warm cache."""
    from pybossa.core import create_app
    app = create_app(run_as_server=False)
    projects_cached = []

    with app.request_context(DUMMY_ENVIRON):
        import pybossa.cache.projects as cached_projects
        import pybossa.cache.categories as cached_cat
        from pybossa.util import rank
        from pybossa.core import user_repo

        def warm_project(_id, short_name, featured=False):
            if _id not in projects_cached:
                # stats.update_stats(_id)  # duplicate work of get_project_jobs
                projects_cached.append(_id)

        start = time.time()
        # Cache top projects
        projects = cached_projects.get_top()
        for p in projects:
            current_app.logger.info('warm_project - top projects. id {} short_name: {}'
                .format(p['id'], p['short_name']))
            warm_project(p['id'], p['short_name'])

        # Cache 3 pages
        to_cache = 3 * app.config['APPS_PER_PAGE']
        projects = rank(cached_projects.get_all_featured('featured'))[:to_cache]
        for p in projects:
            current_app.logger.info('warm_project - ranked project. id {} short_name{}'
                .format(p['id'], p['short_name']))
            warm_project(p['id'], p['short_name'], featured=True)

        # Categories
        categories = cached_cat.get_used()
        for c in categories:
            projects = rank(cached_projects.get_all(c['short_name']))[:to_cache]
            for p in projects:
                current_app.logger.info('warm_project - categories->rank project. id {} short_name{}'
                    .format(p['id'], p['short_name']))
                warm_project(p['id'], p['short_name'])

        current_app.logger.info(f'warm_project - completed {len(projects_cached)} projects in {time.time() - start} seconds')

        # Users
        users = cached_users.get_leaderboard(app.config['LEADERBOARD'])
        current_app.logger.info(f'warm_project - get_leaderboard for {len(users)} users')
        for user in users:
            u = user_repo.get_by_name(user['name'])
            cached_users.get_user_summary(user['name'])
            current_app.logger.info(
                f"warm_project - user get_user_summary: name { user['name']} "
                f"in {time.time() - start} seconds")

            cached_users.projects_contributed_cached(u.id)
            current_app.logger.info(
                f"warm_project - user projects_contributed_cached: id {u.id} "
                f"in {time.time() - start} seconds")

            cached_users.published_projects_cached(u.id)
            current_app.logger.info(
                f"warm_project - user published_projects_cached: id {u.id} "
                f"in {time.time() - start} seconds")

            cached_users.draft_projects_cached(u.id)
            current_app.logger.info(
                f"warm_project - user draft_projects_cached: id {u.id} "
                f"in {time.time() - start} seconds")

        return True


def get_non_updated_projects():
    """Return a list of non updated projects excluding completed ones."""
    from sqlalchemy.sql import text
    from pybossa.model.project import Project
    from pybossa.core import db
    sql = text('''SELECT id FROM project WHERE TO_DATE(updated,
                'YYYY-MM-DD\THH24:MI:SS.US') <= NOW() - '3 month':: INTERVAL
               AND contacted != True AND published = True
               AND project.id NOT IN
               (SELECT task.project_id FROM task
               WHERE task.state='completed'
               GROUP BY task.project_id)''')
    results = db.slave_session.execute(sql)
    projects = []
    for row in results:
        a = Project.query.get(row.id)
        projects.append(a)
    return projects


def warn_old_project_owners():
    """E-mail the project owners not updated in the last 3 months."""
    from smtplib import SMTPRecipientsRefused
    from pybossa.core import mail, project_repo
    from pybossa.cache.projects import clean
    from flask_mail import Message

    projects = get_non_updated_projects()

    with mail.connect() as conn:
        for project in projects:
            if (project.owner.consent and project.owner.subscribed):
                subject = ('Your %s project: %s has been inactive'
                           % (current_app.config.get('BRAND'), project.name))
                body = render_template('/account/email/inactive_project.md',
                                       project=project)
                html = render_template('/account/email/inactive_project.html',
                                       project=project)
                msg = Message(recipients=[project.owner.email_addr],
                              subject=subject,
                              body=body,
                              html=html)
                try:
                    conn.send(msg)
                    project.contacted = True
                    project.published = False
                    clean(project.id)
                    project_repo.update(project)
                except SMTPRecipientsRefused:
                    return False
            else:
                return False
    return True


def disable_users_job():
    from sqlalchemy.sql import text
    from pybossa.model.user import User
    from pybossa.core import db, user_repo

    # default user deactivation time
    user_interval = current_app.config.get('STALE_USERS_MONTHS') or 3
    # domains that are in extended users category
    ext_user_domains = current_app.config.get('EXTENDED_STALE_USERS_DOMAINS') or []

    if ext_user_domains:
        # never disable extended users
        ext_users_filter = ' OR '.join('(u.email_addr LIKE \'%{}\')'.format(domain) for domain in ext_user_domains)
        where = '''((u.inactivity > interval '{} month') AND NOT ({}))'''.format(user_interval, ext_users_filter)
    else:
        where = 'u.inactivity > interval \'{} month\''.format(user_interval)

    sql = text('''
        SELECT id FROM (
            SELECT id, enabled, email_addr, (current_timestamp - to_timestamp(last_login, 'YYYY-MM-DD"T"HH24:MI:SS.US')) AS inactivity
            FROM "user"
        ) u
        WHERE ({}) AND u.enabled = true;
    '''.format(where))
    results = db.slave_session.execute(sql)
    users_disabled = []

    for row in results:
        user = User.query.get(row.id)
        user.enabled = False
        user_repo.update(user)
        user_info = 'name: {}, id: {}, email: {}, last_login: {}'.format(
                        user.name, user.id, user.email_addr, user.last_login)
        users_disabled.append(user_info)

    if users_disabled:
        current_app.logger.info('disable_users_job has disabled following {} users\n{}'
            .format(len(users_disabled), ', '.join(users_disabled)))
    return True


def send_mail(message_dict, mail_all=False):
    """Send email."""

    if mail_all or mail_with_enabled_users(message_dict):
        message = Message(**message_dict)
        spam = False
        for r in message_dict['recipients']:
            acc, domain = r.split('@')
            if domain in current_app.config.get('SPAM', []):
                spam = True
                break
        if not spam:
            if email_service.enabled:
                # Normalize email aliases in recipients
                recipients = []
                for r in message_dict.get("recipients", []):
                    if "+" in r:
                        local, domain = r.split("@", 1)
                        local = local.split("+", 1)[0]
                        r = f"{local}@{domain}"
                    recipients.append(r)
                # Remove duplicates
                recipients = list(dict.fromkeys(recipients))
                message_dict["recipients"] = recipients
                current_app.logger.info("Send email calling email_service %s", message_dict)
                email_service.send(message_dict)
            else:
                current_app.logger.info("Send email calling flask.mail %s", message_dict)
                mail.send(message)


def count_records(table, task_ids):
    from pybossa.core import db

    task_ids_tuple = tuple(task_ids)
    sql = f"SELECT COUNT(*) FROM {table} WHERE task_id IN :taskids;"
    response = db.session.execute(sql, {"taskids": task_ids_tuple}).scalar()
    return response


def count_rows_to_delete(task_ids):
    total_task = len(task_ids)
    total_taskrun = count_records("task_run", task_ids)
    total_result = count_records("result", task_ids)
    return total_task, total_taskrun, total_result


def cleanup_task_records(task_ids, force_reset):
    """Cleanup records associated with task from all related tables."""

    from pybossa.core import db
    from pybossa.cache.task_browse_helpers import get_task_filters

    tables = ["result", "task_run", "task"] if force_reset else ["task"]
    current_app.logger.info("Task ids staged for deletion: %s", task_ids)
    task_ids_tuple = tuple(task_ids)
    for table in tables:
        sql = f"DELETE FROM {table} "
        sql += "WHERE id IN :taskids;" if table == "task" else "WHERE task_id IN :taskids;"
        db.session.execute(sql, {"taskids": task_ids_tuple})
        db.session.commit()

    current_app.logger.info("Total %d tasks deleted from db tables %s", len(task_ids), tables)

def get_tasks_to_delete(project_id, task_filter_args):
    from pybossa.core import db
    from pybossa.cache.task_browse_helpers import get_task_filters

    conditions, params = get_task_filters(task_filter_args)
    sql = text('''
            SELECT task.id as id,
                coalesce(ct, 0) as n_task_runs, task.n_answers, ft,
                priority_0, task.created
                FROM task LEFT OUTER JOIN
                (SELECT task_id, CAST(COUNT(id) AS FLOAT) AS ct,
                MAX(finish_time) as ft FROM task_run
                WHERE project_id=:project_id GROUP BY task_id) AS log_counts
                ON task.id=log_counts.task_id
                WHERE task.project_id=:project_id {}
                ORDER BY task.id;
            '''.format(conditions))
    response = db.bulkdel_session.execute(sql, dict(project_id=project_id, **params)).fetchall()
    task_ids = [id[0] for id in response]
    return task_ids


def delete_bulk_tasks_in_batches(project_id, force_reset, task_filter_args):
    """Delete bulk tasks in batches from project."""

    current_app.logger.info("Deleting tasks in batches for project %d", project_id)
    batch_size = BATCH_SIZE_BULK_DELETE_TASKS
    task_ids = get_tasks_to_delete(project_id, task_filter_args)
    total_task, total_taskrun, total_result = count_rows_to_delete(task_ids)
    current_app.logger.info("total records to delete. task %d, task_run %d, result %d",
                            total_task, total_taskrun, total_result)

    # count iterations required to delete records from all tables
    result_iterations = int(total_result / batch_size) + (1 if total_result % batch_size else 0)
    taskrun_iterations = int(total_taskrun / batch_size) + (1 if total_taskrun % batch_size else 0)
    task_iterations = int(total_task / batch_size) + (1 if total_task % batch_size else 0)
    current_app.logger.info("total iterations. task %d, task_run %d, result %d",
                            task_iterations, taskrun_iterations, result_iterations)

    limit = batch_size
    total_iterations = max(result_iterations, taskrun_iterations, task_iterations)
    total_iterations = min(total_iterations, MAX_BULK_DELETE_TASK_ITERATIONS)
    for i in range(total_iterations):
        start_position = i * batch_size
        end_position = start_position + batch_size
        batched_task_ids = task_ids[start_position:end_position]
        cleanup_task_records(batched_task_ids, force_reset)
        time.sleep(BATCH_DELETE_TASK_DELAY) # allow sql queries other than delete records to execute
    current_app.logger.info("Completed deleting tasks in batches for project %d", project_id)


def delete_bulk_tasks_with_session_repl(project_id, force_reset, task_filter_args):
    from pybossa.core import db
    from pybossa.cache.task_browse_helpers import get_task_filters

    # bulkdel db conn is with db user having session_replication_role
    # when bulkdel is not configured, make explict sql query to set
    # session replication role to replica
    sql_session_repl = ''
    if not 'bulkdel' in current_app.config.get('SQLALCHEMY_BINDS'):
        sql_session_repl = 'SET session_replication_role TO replica;'

    # lock tasks for given project with SELECT FOR UPDATE
    # create temp table with all tasks to be deleted
    # during transaction, disable constraints check with session_replication_role
    # delete rows from child talbes first and then from parent
    if not force_reset:
        """Delete only tasks that have no results associated."""
        params = {}
        sql = text('''
                BEGIN;
                SELECT task_id FROM task_run WHERE project_id=:project_id FOR UPDATE;
                SELECT id FROM task WHERE project_id=:project_id FOR UPDATE;

                {}

                CREATE TEMP TABLE to_delete ON COMMIT DROP AS (
                    SELECT task.id as id FROM task WHERE project_id=:project_id
                    AND task.id NOT IN
                    (SELECT task_id FROM result
                    WHERE result.project_id=:project_id
                    GROUP BY result.task_id)
                );

                DELETE FROM task_run WHERE project_id=:project_id
                        AND task_id IN (SELECT id FROM to_delete);
                DELETE FROM task WHERE project_id=:project_id
                        AND id IN (SELECT id FROM to_delete);

                COMMIT;
                '''.format(sql_session_repl))
    else:
        conditions, params = get_task_filters(task_filter_args)
        sql = text('''
                BEGIN;
                SELECT task_id FROM result WHERE project_id=:project_id FOR UPDATE;
                SELECT task_id FROM task_run WHERE project_id=:project_id FOR UPDATE;
                SELECT id FROM task WHERE project_id=:project_id FOR UPDATE;

                {}

                CREATE TEMP TABLE to_delete ON COMMIT DROP AS (
                    SELECT task.id as id,
                    coalesce(ct, 0) as n_task_runs, task.n_answers, ft,
                    priority_0, task.created
                    FROM task LEFT OUTER JOIN
                    (SELECT task_id, CAST(COUNT(id) AS FLOAT) AS ct,
                    MAX(finish_time) as ft FROM task_run
                    WHERE project_id=:project_id GROUP BY task_id) AS log_counts
                    ON task.id=log_counts.task_id
                    WHERE task.project_id=:project_id {}
                );

                DELETE FROM result WHERE project_id=:project_id
                       AND task_id in (SELECT id FROM to_delete);
                DELETE FROM task_run WHERE project_id=:project_id
                       AND task_id in (SELECT id FROM to_delete);
                DELETE FROM task WHERE task.project_id=:project_id
                       AND id in (SELECT id FROM to_delete);

                COMMIT;
                '''.format(sql_session_repl, conditions))
    db.bulkdel_session.execute(sql, dict(project_id=project_id, **params))

def delete_bulk_tasks(data):
    """Delete tasks in bulk from project."""
    import pybossa.cache.projects as cached_projects


    project_id = data['project_id']
    project_name = data['project_name']
    curr_user = data['curr_user']
    coowners = data['coowners']
    current_user_fullname = data['current_user_fullname']
    force_reset = data['force_reset']
    url = data['url']

    task_filter_args = data.get('filters', {})
    if (current_app.config.get("SESSION_REPLICATION_ROLE_DISABLED")):
        delete_bulk_tasks_in_batches(project_id, force_reset, task_filter_args)
    else:
        delete_bulk_tasks_with_session_repl(project_id, force_reset, task_filter_args)

    cached_projects.clean_project(project_id)
    if not force_reset:
        msg = ("Tasks and taskruns with no associated results have been "
            "deleted from project {0} by {1}"
            .format(project_name, current_user_fullname))
    else:
        msg = ("Tasks, taskruns and results associated have been "
               "deleted from project {0} on {1} as requested by {2}"
               .format(project_name, url, current_user_fullname))

    subject = 'Tasks deletion from %s' % project_name
    body = 'Hello,\n\n' + msg + '\n\nThe %s team.'\
        % current_app.config.get('BRAND')

    recipients = [curr_user]
    for user in coowners:
        recipients.append(user.email_addr)

    mail_dict = dict(recipients=recipients, subject=subject, body=body)
    send_mail(mail_dict)
    check_and_send_task_notifications(project_id)


def send_email_notifications():
    from pybossa.core import sentinel
    from pybossa.cache import projects as cached_projects
    from pybossa.core import project_repo
    from pybossa.sched import Schedulers

    redis_conn = sentinel.master
    project_set = redis_conn.hgetall('updated_project_ids') or {}
    for project_id, timestamp in project_set.items():
        # data from Redis client in Python3 returns bytes
        project_id = project_id.decode()
        timestamp = timestamp.decode()

        project = project_repo.get(project_id)
        redis_conn.hdel('updated_project_ids', project_id)
        if not project.email_notif:
            continue
        user_emails = []
        if cached_projects.get_project_scheduler(project_id) in [Schedulers.user_pref, Schedulers.task_queue]:
            user_emails = user_repo.get_user_pref_recent_contributor_emails(project_id, timestamp)
        else:
            if cached_projects.overall_progress(project_id) != 100:
                user_emails = user_repo.get_recent_contributor_emails(project_id)

        if user_emails:
            recipients = []
            for email_addr in user_emails:
                if email_addr not in recipients:
                    recipients.append(email_addr)
            subject = ('New Tasks have been imported to {}'.format(project.name))
            body = 'Hello,\n\nThere have been new tasks uploaded to the previously finished project, {0}. ' \
                   '\nLog on to {1} to complete any available tasks.' \
                .format(project.name, current_app.config.get('BRAND'))
            recipients_chunk = [recipients[x : x + MAX_RECIPIENTS]
                                for x in range(0, len(recipients), MAX_RECIPIENTS)]
            for group in recipients_chunk:
                mail_dict = dict(recipients=group, subject=subject, body=body)
                send_mail(mail_dict)
    return True


def _num_tasks_imported(project_id):
    from sqlalchemy.sql import text
    from pybossa.core import db
    sql = text('''
        SELECT COUNT(*) FROM task WHERE
        project_id=:project_id AND
            clock_timestamp()
                - to_timestamp(task.created, 'YYYY-MM-DD"T"HH24:MI:SS.US')
            < INTERVAL ':seconds seconds'
        ''')
    params = dict(seconds=IMPORT_TASKS_TIMEOUT + 10, project_id=project_id)
    return db.session.execute(sql, params).scalar()


def import_tasks(project_id, current_user_fullname, from_auto=False, **form_data):
    """Import tasks for a project."""
    from pybossa.core import project_repo, user_repo
    import pybossa.cache.projects as cached_projects

    current_app.logger.info("Importing tasks for project %d", project_id)
    project = project_repo.get(project_id)
    recipients = []
    for user in user_repo.get_users(project.owners_ids):
        recipients.append(user.email_addr)

    try:
        with current_app.test_request_context():
            report = importer.create_tasks(task_repo, project, **form_data)
    except JobTimeoutException:
        from pybossa.core import db
        db.session.rollback()
        n_tasks = _num_tasks_imported(project_id)
        subject = 'Your import task has timed out'
        body = '\n'.join(
            ['Hello,\n',
             'Import task to your project {} by {} failed because the file was too large.',
             'It was able to process approximately {} tasks.',
             'Please break up your task upload into smaller CSV files.',
             'Thank you,\n',
             'The {} team.']).format(project.name, current_user_fullname,
                                     n_tasks, current_app.config.get('BRAND'))
        mail_dict = dict(recipients=recipients, subject=subject, body=body)
        send_mail(mail_dict)
        raise
    except Exception as e:
        msg = ('Import tasks to your project {} by {} failed. Error: {}'
               .format(project.name, current_user_fullname, str(e)))
        subject = 'Tasks Import to your project %s' % project.name
        body = ('Hello,\n\n{0}\n\nPlease contact {1} administrator,\nThe {1} team.'
                .format(msg, current_app.config.get('BRAND')))
        mail_dict = dict(recipients=recipients, subject=subject, body=body)
        send_mail(mail_dict)
        raise

    cached_projects.delete_browse_tasks(project_id)
    check_and_send_task_notifications(project_id)
    if from_auto:
        form_data['last_import_meta'] = report.metadata
        project.set_autoimporter(form_data)
        project_repo.save(project)
    msg = report.message + ' to your project {0} by {1}.'.format(project.name, current_user_fullname)
    current_app.logger.info("Task import status %s", msg)
    subject = 'Tasks Import to your project %s' % project.name
    body = 'Hello,\n\n' + msg + '\n\nAll the best,\nThe %s team.'\
        % current_app.config.get('BRAND')
    mail_dict = dict(recipients=recipients, subject=subject, body=body)
    send_mail(mail_dict)
    return msg


def export_tasks(current_user_email_addr, short_name,
                 ty, expanded, filetype, filters=None, disclose_gold=False):
    """Export tasks/taskruns from a project."""
    from pybossa.core import (task_csv_exporter, task_json_exporter,
                              project_repo)
    import pybossa.exporter.consensus_exporter as export_consensus
    project = project_repo.get_by_shortname(short_name)
    current_app.logger.info(f"exporting tasks for project {project.id}")

    try:
        # Export data and upload .zip file locally
        if ty == 'consensus':
            export_fn = getattr(export_consensus,
                                'export_consensus_{}'.format(filetype))
        elif filetype == 'json':
            export_fn = task_json_exporter.make_zip
        elif filetype == 'csv':
            export_fn = task_csv_exporter.make_zip
        else:
            export_fn = None

        mail_dict = dict(recipients=[current_user_email_addr])
        expires_in = current_app.config.get('EXPORT_EXPIRY', 60 * 60 * 12)  # default 12 hours
        # Construct message
        if export_fn is not None:
            mail_dict['subject'] = 'Data exported for your project: {0}'.format(project.name)
            with export_fn(project, ty, expanded, filters, disclose_gold) as fp:
                filename = fp.filename
                content = fp.read()

            bucket_name = current_app.config.get('EXPORT_BUCKET')
            max_email_size = current_app.config.get('EXPORT_MAX_EMAIL_SIZE', float('Inf'))
            max_s3_upload_size = current_app.config.get('EXPORT_MAX_UPLOAD_SIZE', float('Inf'))

            if len(content) > max_s3_upload_size and bucket_name:
                current_app.logger.info("Task export project id %s: Task export exceeded max size %d, actual size: %d",
                                        project.id, max_s3_upload_size, len(content))
                mail_dict['subject'] = 'Data export exceeded max file size: {0}'.format(project.name)
                msg = '<p>Your export exceeded the maximum file upload size. ' + \
                    'Please try again with a smaller subset of tasks'
            elif len(content) > max_email_size and bucket_name:
                current_app.logger.info("uploading exporting tasks to s3 for project, %s", project.id)
                conn_kwargs = current_app.config.get('S3_EXPORT_CONN', {})
                conn = create_connection(**conn_kwargs)
                bucket = conn.get_bucket(bucket_name, validate=False)
                timestamp = datetime.utcnow().isoformat()
                key = bucket.new_key('{}-{}'.format(timestamp, filename))
                key.set_contents_from_string(content)
                url = key.generate_url(expires_in)
                current_app.logger.info("Task export project id %s: Exported file uploaded to s3 %s",
                                        project.id, url)
                msg = '<p>You can download your file <a href="{}">here</a>.</p>'.format(url)
            else:
                if email_service.enabled:
                    current_app.logger.info("Uploading email attachment to s3. user email %s, project id %d",
                                            current_user_email_addr, project.id)
                    expiration_date = (datetime.now() + timedelta(days=90)).strftime('%a, %d %b %Y %H:%M:%S GMT')
                    url = upload_email_attachment(content, filename, current_user_email_addr, project.id)
                    msg = f'<p>You can download your file <a href="{url}">here</a> until {expiration_date}.</p>'
                    current_app.logger.info("Task export project id %s. Email service export_task attachment link %s", project.id, url)
                else:
                    msg = '<p>Your exported data is attached.</p>'
                    mail_dict['attachments'] = [Attachment(filename, "application/zip", content)]
                    current_app.logger.info("Task export project id %s. Exported file attached to email to send",
                                            project.id)
        else:
            # Failure email
            mail_dict['subject'] = 'Data export failed for your project: {0}'.format(project.name)
            msg = '<p>There was an issue with your export. ' + \
                  'Please try again or report this issue ' + \
                  'to a {0} administrator.</p>'
            msg = msg.format(current_app.config.get('BRAND'))

        if email_service.enabled:
            mail_dict["body"] = f'\nHello,\n{msg}\nThe {current_app.config.get("BRAND")} team\n'
            current_app.logger.info("Send email calling email_service. %s", mail_dict)
            email_service.send(mail_dict)
        else:
            body = '<p>Hello,</p>' + msg + '<p>The {0} team.</p>'
            body = body.format(current_app.config.get('BRAND'))
            mail_dict['html'] = body
            message = Message(**mail_dict)
            mail.send(message)
        current_app.logger.info(
            'Email sent successfully - Project: %s', project.name)
        job_response = '{0} {1} file was successfully exported for: {2}'
        return job_response.format(
                ty.capitalize(), filetype.upper(), project.name)
    except Exception as e:
        current_app.logger.exception(
                'Export email failed - Project: %s, exception: %s',
                project.name, str(e))
        subject = 'Email delivery failed for your project: {0}'.format(project.name)
        msg = 'There was an error when attempting to deliver your data export via email.'
        body = 'Hello,\n\n' + msg + '\n\nThe {0} team.'
        body = body.format(current_app.config.get('BRAND'))
        mail_dict = dict(recipients=[current_user_email_addr],
                         subject=subject,
                         body=body)
        message = Message(**mail_dict)
        if email_service.enabled:
            current_app.logger.info("Sending error email for export tasks using email_service. %r", mail_dict)
            email_service.send(mail_dict)
        else:
            mail.send(message)
        raise


def webhook(url, payload=None, oid=None, rerun=False):
    """Post to a webhook."""
    from flask import current_app
    from readability.readability import Document
    try:
        import json
        from pybossa.core import sentinel, webhook_repo, project_repo
        project = project_repo.get(payload['project_id'])
        headers = {'Content-type': 'application/json', 'Accept': 'text/plain'}
        if oid:
            webhook = webhook_repo.get(oid)
        else:
            webhook = Webhook(project_id=payload['project_id'],
                              payload=payload)
        if url:
            params = dict()
            if rerun:
                params['rerun'] = True
            response = requests.post(url, params=params,
                                     data=json.dumps(payload),
                                     headers=headers)
            webhook.response = Document(response.text).summary()
            webhook.response_status_code = response.status_code
        else:
            raise requests.exceptions.ConnectionError('Not URL')
        if oid:
            webhook_repo.update(webhook)
            webhook = webhook_repo.get(oid)
        else:
            webhook_repo.save(webhook)
    except requests.exceptions.ConnectionError:
        webhook.response = 'Connection Error'
        webhook.response_status_code = None
        webhook_repo.save(webhook)
    finally:
        if project.published and webhook.response_status_code != 200 and current_app.config.get('ADMINS'):
            subject = "Broken: %s webhook failed" % project.name
            body = 'Sorry, but the webhook failed'
            mail_dict = dict(recipients=current_app.config.get('ADMINS'),
                             subject=subject, body=body, html=webhook.response)
            send_mail(mail_dict)
    if current_app.config.get('SSE'):
        publish_channel(sentinel, payload['project_short_name'],
                        data=webhook.dictize(), type='webhook',
                        private=True)
    return webhook


def notify_blog_users(blog_id, project_id, queue='high'):
    """Send email with new blog post."""
    from sqlalchemy.sql import text
    from pybossa.core import db
    from pybossa.core import blog_repo
    from pybossa.pro_features import ProFeatureHandler

    blog = blog_repo.get(blog_id)
    users = 0
    feature_handler = ProFeatureHandler(current_app.config.get('PRO_FEATURES'))
    only_pros = feature_handler.only_for_pro('notify_blog_updates')
    timeout = current_app.config.get('TIMEOUT')
    if blog.project.featured or (blog.project.owner.pro or not only_pros):
        sql = text('''
                   SELECT email_addr, name from "user", task_run
                   WHERE task_run.project_id=:project_id
                   AND task_run.user_id="user".id
                   AND "user".subscribed=true
                   AND "user".restrict=false
                   GROUP BY email_addr, name, subscribed;
                   ''')
        results = db.slave_session.execute(sql, dict(project_id=project_id))
        for row in results:
            subject = "Project Update: %s by %s" % (blog.project.name,
                                                    blog.project.owner.fullname)
            body = render_template('/account/email/blogupdate.md',
                                   user_name=row.name,
                                   blog=blog,
                                   config=current_app.config)
            html = render_template('/account/email/blogupdate.html',
                                   user_name=row.name,
                                   blog=blog,
                                   config=current_app.config)
            mail_dict = dict(recipients=[row.email_addr],
                             subject=subject,
                             body=body,
                             html=html)

            job = dict(name=send_mail,
                       args=[mail_dict],
                       kwargs={},
                       timeout=timeout,
                       queue=queue)
            enqueue_job(job)
            users += 1
    msg = "%s users notified by email" % users
    return msg


def notify_task_progress(info, email_addr, queue='high'):
    """ send email about the progress of task completion """

    subject = "Project progress reminder for {}".format(info['project_name'])
    msg = """There are only {} tasks left as incomplete in your project {}.
          """.format(info['n_available_tasks'], info['project_name'])
    body = ('Hello,\n\n{}\nThe {} team.'
            .format(msg, current_app.config.get('BRAND')))
    mail_dict = dict(recipients=email_addr,
                        subject=subject,
                        body=body)

    timeout = current_app.config.get('TIMEOUT')
    job = dict(name=send_mail,
                args=[mail_dict],
                kwargs={},
                timeout=timeout,
                queue=queue)
    enqueue_job(job)

def get_weekly_admin_report_jobs():
    """Return email jobs with weekly report to admins"""
    send_emails_date = current_app.config.get('WEEKLY_ADMIN_REPORTS').lower()
    recipients = current_app.config.get('WEEKLY_ADMIN_REPORTS_EMAIL')
    today = datetime.today().strftime('%A').lower()
    timeout = current_app.config.get('TIMEOUT')
    current_app.logger.info('Checking weekly report for admins, scheduled date: {}, today: {}'
                            .format(send_emails_date, today))
    jobs = []
    if recipients and today == send_emails_date:
        info = dict(timestamp=datetime.now().isoformat(),
            user_id=0, # user_id=0 indicates auto-generated report for admins
            base_url=current_app.config.get('SERVER_URL') or '' + '/project/')
        project_report = dict(name=mail_project_report,
                    args=[info, recipients],
                    kwargs={},
                    timeout=timeout,
                    queue='low')
        fmt = 'csv'
        user_report = dict(name=export_all_users,
                    args=[fmt, recipients],
                    kwargs={},
                    timeout=timeout,
                    queue='low')
        jobs = [project_report, user_report]
    return iter(jobs)

def get_weekly_stats_update_projects():
    """Return email jobs with weekly stats update for project owner."""
    from sqlalchemy.sql import text
    from pybossa.core import db
    from pybossa.pro_features import ProFeatureHandler

    feature_handler = ProFeatureHandler(current_app.config.get('PRO_FEATURES'))
    only_pros = feature_handler.only_for_pro('project_weekly_report')
    only_pros_sql = 'AND "user".pro=true' if only_pros else ''
    send_emails_date = current_app.config.get('WEEKLY_UPDATE_STATS')
    today = datetime.today().strftime('%A').lower()
    timeout = current_app.config.get('TIMEOUT')
    if today.lower() == send_emails_date.lower():
        sql = text('''
                   SELECT project.id
                   FROM project, "user", task
                   WHERE "user".id=project.owner_id %s
                   AND "user".subscribed=true
                   AND "user".restrict=false
                   AND task.project_id=project.id
                   AND task.state!='completed'
                   UNION
                   SELECT project.id
                   FROM project
                   WHERE project.featured=true;
                   ''' % only_pros_sql)
        results = db.slave_session.execute(sql)
        for row in results:
            job = dict(name=send_weekly_stats_project,
                       args=[row.id],
                       kwargs={},
                       timeout=timeout,
                       queue='low')
            yield job


def send_weekly_stats_project(project_id):
    from pybossa.cache.project_stats import update_stats, get_stats
    from pybossa.core import project_repo
    from datetime import datetime
    project = project_repo.get(project_id)
    if project.owner.subscribed is False or project.owner.restrict:
        return "Owner does not want updates by email"
    update_stats(project_id)
    dates_stats, hours_stats, users_stats = get_stats(project_id,
                                                      period='1 week')
    subject = "Weekly Update: %s" % project.name

    timeout = current_app.config.get('TIMEOUT')

    # Max number of completed tasks
    n_completed_tasks = 0
    xy = list(zip(*dates_stats[3]['values']))
    n_completed_tasks = max(xy[1])
    # Most active day
    xy = list(zip(*dates_stats[0]['values']))
    active_day = [xy[0][xy[1].index(max(xy[1]))], max(xy[1])]
    active_day[0] = datetime.fromtimestamp(active_day[0]/1000).strftime('%A')
    body = render_template('/account/email/weeklystats.md',
                           project=project,
                           dates_stats=dates_stats,
                           hours_stats=hours_stats,
                           users_stats=users_stats,
                           n_completed_tasks=n_completed_tasks,
                           active_day=active_day,
                           config=current_app.config)
    html = render_template('/account/email/weeklystats.html',
                           project=project,
                           dates_stats=dates_stats,
                           hours_stats=hours_stats,
                           users_stats=users_stats,
                           active_day=active_day,
                           n_completed_tasks=n_completed_tasks,
                           config=current_app.config)
    mail_dict = dict(recipients=[project.owner.email_addr],
                     subject=subject,
                     body=body,
                     html=html)

    job = dict(name=send_mail,
               args=[mail_dict],
               kwargs={},
               timeout=timeout,
               queue='high')
    enqueue_job(job)


def news():
    """Get news from different ATOM RSS feeds."""
    import feedparser
    from pybossa.core import sentinel
    from pybossa.news import get_news, notify_news_admins, FEED_KEY
    try:
        import pickle as pickle
    except ImportError:  # pragma: no cover
        import pickle
    urls = ['https://github.com/Scifabric/pybossa/releases.atom',
            'http://scifabric.com/blog/all.atom.xml']
    score = 0
    notify = False
    if current_app.config.get('NEWS_URL'):
        urls += current_app.config.get('NEWS_URL')
    for url in urls:
        d = feedparser.parse(url)
        tmp = get_news(score)
        if (d.entries and (len(tmp) == 0)
           or (tmp[0]['updated'] != d.entries[0]['updated'])):
            mapping = dict()
            mapping[pickle.dumps(d.entries[0])] = float(score)
            sentinel.master.zadd(FEED_KEY, mapping)
            notify = True
        score += 1
    if notify:
        notify_news_admins()

def check_failed():
    """Check the jobs that have failed and requeue them."""
    from rq import requeue_job
    from rq.registry import FailedJobRegistry
    from pybossa.core import sentinel

    # Per https://github.com/rq/rq/blob/master/CHANGES.md
    # get_failed_queue has been removed
    fq = FailedJobRegistry()
    job_ids = fq.get_job_ids()
    count = len(job_ids)
    FAILED_JOBS_RETRIES = current_app.config.get('FAILED_JOBS_RETRIES')
    for job_id in job_ids:
        KEY = 'pybossa:job:failed:%s' % job_id
        job = fq.fetch_job(job_id)
        if sentinel.slave.exists(KEY):
            sentinel.master.incr(KEY)
        else:
            ttl = current_app.config.get('FAILED_JOBS_MAILS')*24*60*60
            sentinel.master.setex(KEY, ttl, 1)
        if int(sentinel.slave.get(KEY)) < FAILED_JOBS_RETRIES:
            requeue_job(job_id, sentinel.master)
        else:
            KEY = 'pybossa:job:failed:mailed:%s' % job_id
            if (not sentinel.slave.exists(KEY) and
                    current_app.config.get('ADMINS')):
                subject = "JOB: %s has failed more than 3 times" % job_id
                body = "Please, review the background jobs of your server."
                body += "\n This is the trace error\n\n"
                body += "------------------------------\n\n"
                body += job.exc_info
                mail_dict = dict(recipients=current_app.config.get('ADMINS'),
                                 subject=subject, body=body)
                send_mail(mail_dict)
                ttl = current_app.config.get('FAILED_JOBS_MAILS')*24*60*60
                sentinel.master.setex(KEY, ttl, 1)
    if count > 0:
        return "JOBS: %s You have failed the system." % job_ids
    else:
        return "You have not failed the system"


def mail_project_report(info, email_addr):
    from pybossa.core import project_csv_exporter

    recipients = email_addr if isinstance(email_addr, list) else [email_addr]
    current_app.logger.info('Scheduling mail_project_report job {}'.format(str(info)))
    try:
        zipfile = None
        filename = project_csv_exporter.zip_name(info)
        subject = '{} project report'.format(current_app.config['BRAND'])
        body = 'Hello,\n\n{}\n\nThe {} team.'

        zipfile = project_csv_exporter.generate_zip_files(info)
        if email_service.enabled:
            current_app.logger.info("Uploading email attachment to s3 for project report. user email %s", email_addr)
            expiration_date = (datetime.now() + timedelta(days=90)).strftime('%a, %d %b %Y %H:%M:%S GMT')
            content = None
            with open(zipfile, mode='rb') as fp:  # open zipfile in binary mode
                content = fp.read()
            if not content:
                raise ValueError("No content in zipfile: {}".format(zipfile))

            url = upload_email_attachment(content, filename, email_addr)
            msg = f'<p>You can download your file <a href="{url}">here</a> until {expiration_date}.</p>'
            body = body.format(msg, current_app.config.get('BRAND'))
            mail_dict = dict(recipients=recipients,
                        subject=subject,
                        body=body)
            current_app.logger.info("Project report for user %s generated email with report link %s", email_addr, url)
        else:
            msg = 'Your exported data is attached.'
            body = body.format(msg, current_app.config.get('BRAND'))
            mail_dict = dict(recipients=recipients,
                            subject=subject,
                            body=body)

            attachment = None
            with open(zipfile, mode='rb') as fp:  # open zipfile in binary mode
                attachment = Attachment(filename, "application/zip",
                                        fp.read())
            if not attachment:
                raise ValueError("No content in zipfile: {}".format(zipfile))
            mail_dict['attachments'] = [attachment]
    except Exception:
        current_app.logger.exception('Error in mail_project_report')
        subject = 'Error in {} project report'.format(current_app.config['BRAND'])
        msg = 'An error occurred while exporting your report.'

        body = 'Hello,\n\n{}\n\nThe {} team.'
        body = body.format(msg, current_app.config.get('BRAND'))
        mail_dict = dict(recipients=recipients,
                         subject=subject,
                         body=body)
        raise
    finally:
        if zipfile:
            os.unlink(zipfile)
        if email_service.enabled:
            email_service.send(mail_dict)
        else:
            send_mail(mail_dict)


def delete_account(user_id, admin_addr, **kwargs):
    """Delete user account from the system."""
    from pybossa.core import (user_repo, uploader)
    user = user_repo.get(user_id)

    container = "user_%s" % user.id
    if user.info.get('avatar'):
        uploader.delete_file(user.info['avatar'], container)

    email = user.email_addr
    if current_app.config.get('MAILCHIMP_API_KEY'):
        from pybossa.core import newsletter
        newsletter.init_app(current_app)
        mailchimp_deleted = newsletter.delete_user(email)
    else:
        mailchimp_deleted = True
    brand = current_app.config.get('BRAND')
    user_repo.delete_data(user)
    subject = '[%s]: Your account has been deleted' % brand
    body = """Hi,\n Your account and personal data has been deleted from %s.""" % brand
    if not mailchimp_deleted:
        body += '\nWe could not delete your Mailchimp account, please contact us to fix this issue.'
    if current_app.config.get('DISQUS_SECRET_KEY'):
        body += '\nDisqus does not provide an API method to delete your account. You will have to do it by hand yourself in the disqus.com site.'
    recipients = [email]
    if current_app.config.get('ADMINS'):
        for em in current_app.config.get('ADMINS'):
            recipients.append(em)
    bcc = [admin_addr]
    mail_dict = dict(recipients=recipients, bcc=bcc, subject=subject, body=body)
    send_mail(mail_dict, mail_all=True)


def export_userdata(user_id, admin_addr, **kwargs):
    from pybossa.core import (user_repo)
    from flask import current_app
    json_exporter = JsonExporter()
    user = user_repo.get(user_id)
    user_data = user.dictize()
    del user_data['passwd_hash']

    buffer = BytesIO()  # ZipFile expects Bytes
    with ZipFile(buffer, 'w') as zf:
        zf.writestr('personal_data.json', json.dumps(user_data))
    buffer.seek(0)
    attachments = [Attachment('personal_data.zip', 'application/zip', buffer.read())]
    body = render_template('/account/email/exportdata.md',
                           user=user.dictize(),
                           personal_data_link=None,
                           config=current_app.config)

    html = render_template('/account/email/exportdata.html',
                           user=user.dictize(),
                           personal_data_link=None,
                           config=current_app.config)
    subject = 'Your personal data'
    bcc = [admin_addr]
    mail_dict = dict(recipients=[user.email_addr],
                     bcc=bcc,
                     subject=subject,
                     body=body,
                     html=html,
                     attachments=attachments)
    send_mail(mail_dict)


def delete_file(fname, container):
    """Delete file."""
    from pybossa.core import uploader
    return uploader.delete_file(fname, container)

def load_usage_dashboard_data(days):
    timed_stats_funcs = [
        (site_stats.number_of_created_jobs, "Projects"),
        (site_stats.n_tasks_site, "Tasks"),
        (site_stats.n_task_runs_site, "Taskruns"),
    ]

    # total tasks, taskruns, projects over a specified amount of time.
    stats = OrderedDict()
    for func, title in timed_stats_funcs:
        stats[title] = [(func(days), None, None)]

    # component usage
    for name, tag in current_app.config.get("USAGE_DASHBOARD_COMPONENTS", {}).items():
        stats[name] = site_stats.n_projects_using_component(days=days, component=tag)

    return stats

def load_management_dashboard_data():
    # charts
    project_chart = site_stats.project_chart()  # < 1s
    category_chart = site_stats.category_chart()  # < 1s
    task_chart = site_stats.task_chart()  # 110s in QA
    submission_chart = site_stats.submission_chart()  # 9s in QA

    # General platform usage
    timed_stats_funcs = [
        site_stats.number_of_active_jobs,  # 1s
        site_stats.number_of_created_jobs,  # 1s
        site_stats.number_of_created_tasks,  # 90s(1.5,2.5,3s,81s) in QA with new index
        site_stats.number_of_completed_tasks,  # 300s(6s,94s,82s,102s) in QA
        site_stats.avg_time_to_complete_task,  # 24s(4s,4s,4s,12s) in QA
        site_stats.number_of_active_users,  # 35s(4s,4s,5s,11s,11s) in QA
        site_stats.categories_with_new_projects  # 1s
    ]

    # Work on platform
    current_stats_funcs = [
        site_stats.avg_task_per_job,  # < 1s
        site_stats.tasks_per_category  # < 1s
    ]

    timed_stats = OrderedDict()
    for func in timed_stats_funcs:
        timed_stats[func.__doc__] = OrderedDict()
        for days in [30, 60, 90, 350, 'all']:
            timed_stats[func.__doc__][days] = func(days)

    current_stats = OrderedDict((func.__doc__, func())
                                for func in current_stats_funcs)
    return project_chart, category_chart, task_chart, submission_chart, timed_stats, current_stats


def get_management_dashboard_stats(user_email):
    """Rebuild management dashboard stats, notify user about its availability"""
    load_management_dashboard_data()

    subject = 'Management Dashboard Statistics'
    msg = 'Management dashboard statistics is now available. It can be accessed by refreshing management dashboard page.'
    body = ('Hello,\n\n{}\nThe {} team.'
            .format(msg, current_app.config.get('BRAND')))
    mail_dict = dict(recipients=[user_email], subject=subject, body=body)
    send_mail(mail_dict)


def check_and_send_task_notifications(project_id, conn=None):
    from pybossa.core import project_repo

    project = project_repo.get(project_id)
    if not project:
        return

    reminder = project.info.get('progress_reminder', {})
    target_remaining = reminder.get("target_remaining")
    webhook = reminder.get('webhook')
    email_already_sent = reminder.get("sent") or False
    if target_remaining is None:
        return

    n_remaining_tasks = n_available_tasks(project.id)

    update_reminder = False
    if n_remaining_tasks > target_remaining and email_already_sent:
        current_app.logger.info('Project {}, the number of tasks in queue: {} \
                                exceeds target remaining: {}, \
                                resetting the send notification flag to True'
                                .format(project_id, n_remaining_tasks, target_remaining))
        reminder['sent'] = False
        update_reminder = True

    if n_remaining_tasks <= target_remaining and not email_already_sent:
        # incomplete tasks drop to or below, and email not sent yet, send email
        current_app.logger.info('Project {} the number of tasks in queue: {}, \
                                drops equal to or below target remaining: {}, \
                                sending task notification to owners: {}'
                                .format(project_id, n_remaining_tasks, target_remaining, project.owners_ids))
        email_addr = [cached_users.get_user_email(user_id)
                        for user_id in project.owners_ids]
        info = dict(project_name=project.name,
                    n_available_tasks=n_remaining_tasks)
        notify_task_progress(info, email_addr)

        reminder['sent'] = True
        update_reminder = True

        if webhook:
            current_app.logger.info('Project {} the number of tasks in queue: {}, \
                                drops equal to or below target remaining: {}, hitting webhook url: {}'
                                .format(project_id, n_remaining_tasks, target_remaining, webhook))
            try:
                headers = {'Content-type': 'application/json', 'Accept': 'text/plain'}
                data = dict(project_id=project_id,
                            project_name=project.name,
                            remianing_tasks=n_remaining_tasks,
                            target_remaining=target_remaining)
                webhook_response = requests.post(webhook, data=json.dumps(data), headers=headers)

                if webhook_response.status_code >= 400:
                    reminder['webhook'] = ''
                    # send email to project owners
                    subject = 'Webhook failed from {}'.format(project_id)
                    body = '\n'.join(
                        ['Hello,\n',
                        'The webhook {} returns {}, please make sure the webhook is valid.',
                        'Current webhook will be disabled, please re-activate it in task notification configuration.',
                        'Thank you,\n',
                        'The {} team.']).format(webhook, webhook_response.status_code, current_app.config.get('BRAND'))
                    mail_dict = dict(recipients=email_addr, subject=subject, body=body)
                    send_mail(mail_dict)
                    raise Exception('webhook response error, returned {}'.format(webhook_response.status_code))
                else:
                    current_app.logger.info('Webhook {} posted'.format(webhook))
            except Exception as e:
                current_app.logger.exception('An error occured while posting to project {} webhook {}, {}'
                                           .format(project_id, webhook, str(e)))

    if update_reminder:
        project.info['progress_reminder'] = reminder
        if conn is not None:
            # Listener process is updating the task notification.
            sql = text(''' UPDATE project SET info=:info WHERE id=:id''')
            conn.execute(sql, dict(info=json.dumps(project.info), id=project_id))
        else:
            # User is updating the task notification from the project settings.
            project_repo.save(project)


def export_all_users(fmt, email_addr):
    exportable_attributes = ('id', 'name', 'fullname', 'email_addr', 'locale',
                             'created', 'admin', 'subadmin', 'enabled', 'languages',
                             'locations', 'work_hours_from', 'work_hours_to',
                             'timezone', 'type_of_user', 'additional_comments',
                             'total_projects_contributed', 'completed_task_runs',
                             'percentage_tasks_completed', 'first_submission_date',
                             'last_submission_date', 'avg_time_per_task', 'consent',
                             'restrict')

    def respond_json():
        return gen_json()

    def gen_json():
        users = get_users_for_report()
        jdata = json.dumps(users)
        return jdata

    def respond_csv():
        users = get_users_for_report()
        df = pd.DataFrame.from_dict(users)
        user_csv = df.to_csv(columns=exportable_attributes, index=False)
        return user_csv

    recipients = email_addr if isinstance(email_addr, list) else [email_addr]
    current_app.logger.info('Scheduling export_all_users job send to {} admins/users'
                            .format(len(recipients)))

    try:
        data = {"json": respond_json, "csv": respond_csv}[fmt]()
        if email_service.enabled:
            current_app.logger.info("Uploading email attachment to s3 for export users report. user email %s", email_addr)
            expiration_date = (datetime.now() + timedelta(days=90)).strftime('%a, %d %b %Y %H:%M:%S GMT')
            filename = 'user_export.{}'.format(fmt)
            url = upload_email_attachment(data, filename, email_addr)
            body = f'<p>You can download your file <a href="{url}">here</a> until {expiration_date}.</p>'
            mail_dict = dict(recipients=recipients,
                        subject="User Export",
                        body=body)
            current_app.logger.info("Export users for user %s generated email with report link %s", email_addr, url)
        else:
            mimetype = {"csv": "text/csv", "zip": "application/zip", "json": "application/json"}
            attachment = Attachment(
                'user_export.{}'.format(fmt),
                mimetype.get(fmt, "application/octet-stream"),
                data
            )
            mail_dict = {
                'recipients': recipients,
                'subject': 'User Export',
                'body': 'Your exported data is attached.',
                'attachments': [attachment]
            }
    except Exception as e:
        mail_dict = {
            'recipients': [email_addr],
            'subject': 'User Export Failed',
            'body': 'User export failed, {}'.format(str(e))
        }
        raise
    finally:
        if email_service.enabled:
            email_service.send(mail_dict)
        else:
            send_mail(mail_dict)


# TODO: uncomment, reuse this under future PR
# def get_completed_tasks_cleaup_jobs(queue="weekly"):
#     """Return job that will perform cleanup of completed tasks."""
#     timeout = current_app.config.get('TIMEOUT')
#     job = dict(name=perform_completed_tasks_cleanup,
#                 args=[],
#                 kwargs={},
#                 timeout=timeout,
#                 queue=queue)
#     yield job


def perform_completed_tasks_cleanup():
    from sqlalchemy.sql import text
    from pybossa.core import db
    from pybossa.purge_data import purge_task_data

    valid_days = [days[0] for days in current_app.config.get('COMPLETED_TASK_CLEANUP_DAYS', [(None, None)]) if days[0]]
    if not valid_days:
        current_app.logger.info("Skipping perform completed tasks cleanup. Missing configuration COMPLETED_TASK_CLEANUP_DAYS.")
        return

    # identify projects that are set for automated completed tasks cleanup
    projects = []
    sql = text('''SELECT id as project_id, info->>'completed_tasks_cleanup_days' as cleanup_days FROM project
               WHERE info->>'completed_tasks_cleanup_days' IS NOT NULL
               ;''')
    results = db.slave_session.execute(sql)
    for row in results:
        project_id = row.project_id
        try:
            cleanup_days = int(row.cleanup_days)
        except ValueError:
            cleanup_days = -1
        if cleanup_days not in valid_days:
            current_app.logger.info(
                f"Skipping project cleanup days due to invalid cleanup days,"
                f"project id {project_id}, completed_tasks_cleanup_days {row.cleanup_days}, valid days {valid_days}"
            )
        else:
            projects.append((project_id, cleanup_days))

    for project in projects:
        project_id, cleanup_days = project
        # identify tasks that are set for automated completed tasks cleanup
        sql = text('''SELECT id AS task_id FROM task
                    WHERE  project_id=:project_id AND
                    state=:state AND
                    TO_DATE(created, 'YYYY-MM-DD"T"HH24:MI:SS.US') <= NOW() - ':duration days' :: INTERVAL
                    ORDER BY created;
                ;''')
        params = dict(project_id=project_id, state="completed", duration=cleanup_days)
        results = db.slave_session.execute(sql, params)
        total_tasks = results.rowcount if results else 0
        current_app.logger.info(f"Performing cleanup of {total_tasks} completed tasks for project {project_id} that are older than {cleanup_days} days or more.")
        for row in results:
            purge_task_data(row.task_id, project_id)
        current_app.logger.info(f"Finished cleanup of completed tasks for project {project_id}")
