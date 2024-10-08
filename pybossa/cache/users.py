# -*- coding: utf8 -*-
# This file is part of PYBOSSA.
#
# Copyright (C) 2017 Scifabric LTD.
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
"""Cache module for users."""
from sqlalchemy.sql import text
from sqlalchemy.exc import ProgrammingError
from pybossa.core import db, timeouts
from pybossa.cache import cache, memoize, delete_memoized, FIVE_MINUTES, \
    ONE_DAY, ONE_WEEK, memoize_with_l2_cache
from pybossa.util import pretty_date, exists_materialized_view
from pybossa.model.user import User
from pybossa.cache.projects import overall_progress, n_tasks, n_volunteers
from pybossa.cache.projects import n_total_tasks
from pybossa.model.project import Project
from pybossa.leaderboard.data import get_leaderboard as gl
from pybossa.leaderboard.jobs import leaderboard as lb
import json
from pybossa.util import get_user_pref_db_clause, get_user_filter_db_clause, map_locations
from pybossa.data_access import data_access_levels
from pybossa.util import get_taskrun_date_range_sql_clause_params
from flask import current_app

session = db.slave_session


@memoize_with_l2_cache(timeout=timeouts.get('USER_TIMEOUT'))
def get_leaderboard(n, user_id=None, window=0, info=None):
    """Return the top n users with their rank."""
    try:
        return gl(top_users=n, user_id=user_id, window=window, info=info)
    except ProgrammingError:
        db.session.rollback()
        lb(info=info)
        return gl(top_users=n, user_id=user_id, window=window, info=info)


@memoize(timeout=timeouts.get('USER_TIMEOUT'))
def n_projects_contributed(user_id):
    """Return number of projects user has contributed to."""
    sql = text('''
                WITH projects_contributed AS
                    (SELECT DISTINCT project_id FROM task_run
                    WHERE user_id =:user_id)
                SELECT COUNT(*) AS total_projects_contributed
                FROM projects_contributed;
                ''')
    results = session.execute(sql, dict(user_id=user_id))
    total_projects_contributed = 0
    for row in results:
        total_projects_contributed = row.total_projects_contributed
    return total_projects_contributed


@memoize(timeout=timeouts.get('USER_TIMEOUT'))
def get_user_summary(name, current_user=None):
    """Return user summary."""
    sql = text('''
               SELECT "user".id, "user".name, "user".fullname, "user".created,
               "user".api_key, "user".twitter_user_id, "user".facebook_user_id,
               "user".google_user_id, "user".info, "user".admin,
               "user".locale,
               "user".email_addr, COUNT(task_run.user_id) AS n_answers,
               "user".valid_email, "user".confirmation_email_sent,
               max(task_run.finish_time) AS last_task_submission_on,
               "user".restrict
               FROM "user"
               LEFT OUTER JOIN task_run ON "user".id=task_run.user_id
               WHERE "user".name=:name
               GROUP BY "user".id;
               ''')
    results = session.execute(sql, dict(name=name))
    user = dict()
    for row in results:
        user = dict(id=row.id, name=row.name, fullname=row.fullname,
                    created=row.created, api_key=row.api_key,
                    twitter_user_id=row.twitter_user_id,
                    google_user_id=row.google_user_id,
                    facebook_user_id=row.facebook_user_id,
                    info=row.info, admin=row.admin,
                    locale=row.locale,
                    email_addr=row.email_addr, n_answers=row.n_answers,
                    valid_email=row.valid_email,
                    confirmation_email_sent=row.confirmation_email_sent,
                    registered_ago=pretty_date(row.created),
                    last_task_submission_on=row.last_task_submission_on,
                    restrict=row.restrict)
    if user:
        rank_score = rank_and_score(user['id'])
        user['rank'] = rank_score['rank']
        user['score'] = rank_score['score']
        user['total'] = get_total_users()
        if user['restrict']:
            if (current_user and
                current_user.is_authenticated and
               (current_user.id == user['id'])):
                return user
            else:
                current_app.logger.info("""
                    Method get_user_summary(): User restricted. Returning None as user is not current_user
                    for user name %s, user id %s, user restrict %s, current user id %s, current user name %s,
                    current user authenticated %s, is_current_user == user %s""",
                    name, user.get('id'), user.get('restrict'), current_user.id if current_user else None,
                    current_user.name if current_user else None, current_user.is_authenticated if current_user else False,
                    current_user.id == user.get('id') if current_user else False)
                return None
        else:
            return user
    else:
        current_app.logger.info("Method get_user_summary(): user is None for user name %s, current user id %s, current user name %s",
            name, current_user.id if current_user else None, current_user.name if current_user else None)
        return None


@memoize(timeout=timeouts.get('USER_TIMEOUT'))
def public_get_user_summary(name):
    """Sanitize user summary for public usage"""
    private_user = get_user_summary(name)
    public_user = None
    if private_user is not None:
        u = User()
        public_user = u.to_public_json(data=private_user)
    if not public_user:
        current_app.logger.info("Method public_get_user_summary(): public_user is None for user name %s. private_user None = %s",
            name, private_user == None)
    return public_user


@memoize(timeout=timeouts.get('USER_TIMEOUT'))
def rank_and_score(user_id):
    """Return rank and score for a user."""
    if exists_materialized_view(db, 'users_rank') is False:
        lb()
    sql = text('''SELECT * from users_rank WHERE id=:user_id''')
    results = session.execute(sql, dict(user_id=user_id))
    rank_and_score = dict(rank=None, score=None)
    for row in results:
        rank_and_score['rank'] = row.rank
        rank_and_score['score'] = row.score
    return rank_and_score


def projects_contributed(user_id, order_by='name'):
    """Return projects that user_id has contributed to."""
    sql = text('''
               WITH projects_contributed as
                    (SELECT project_id, MAX(finish_time) as last_contribution  FROM task_run
                     WHERE user_id=:user_id GROUP BY project_id)
               SELECT project.id, project.name as name, project.short_name, project.owner_id,
               project.description, project.info, project.owners_ids
               FROM project, projects_contributed
               WHERE project.id=projects_contributed.project_id ORDER BY {} DESC;
               '''.format(order_by))
    results = session.execute(sql, dict(user_id=user_id))
    projects_contributed = []
    for row in results:
        project = dict(id=row.id, name=row.name, short_name=row.short_name,
                       owner_id=row.owner_id,
                       owners_ids=row.owners_ids,
                       description=row.description,
                       overall_progress=overall_progress(row.id),
                       n_tasks=n_tasks(row.id),
                       n_volunteers=n_volunteers(row.id),
                       info=row.info)
        projects_contributed.append(project)
    return projects_contributed


@memoize(timeout=timeouts.get('USER_TIMEOUT'))
def projects_contributed_cached(user_id, order_by='name'):
    """Return projects contributed too (cached version)."""
    return projects_contributed(user_id, order_by=order_by)


def public_projects_contributed(user_id):
    """Return projects that user_id has contributed to. Public information only"""
    unsanitized_projects = projects_contributed(user_id)
    public_projects = []
    if unsanitized_projects:
        p = Project()
        for project in unsanitized_projects:
            public_project = p.to_public_json(data=project)
            public_projects.append(public_project)
    return public_projects


@memoize(timeout=timeouts.get('USER_TIMEOUT'))
def public_projects_contributed_cached(user_id):
    """Return projects contributed too (cached version)."""
    return public_projects_contributed(user_id)


allowed_project_columns = {
    "created_on": "created",
    "project_name": "name"
}


def published_projects(user_id, args=None):
    """Return published projects for user_id."""
    if args is None:
        args = dict(column=None, order=None)
    sort_args = dict(column=args.get("column"), order=args.get("order"))
    if sort_args.get("order") not in ("asc", "desc"):
        sort_args["order"] = "desc"
    sort_args["column"] = allowed_project_columns.get(sort_args["column"], "created")

    sql = text('''
               SELECT project.id, project.name, project.short_name, project.description,
               project.owner_id,
               project.owners_ids,
               project.info
               FROM project
               WHERE project.published=true
               AND :user_id = ANY (project.owners_ids::int[])
               order by {column} {order};
               '''.format(**sort_args))
    projects_published = []
    results = session.execute(sql, dict(user_id=user_id))
    for row in results:
        project = dict(id=row.id, name=row.name, short_name=row.short_name,
                       owner_id=row.owner_id,
                       owners_ids=row.owners_ids,
                       description=row.description,
                       overall_progress=overall_progress(row.id),
                       n_tasks=n_tasks(row.id),
                       n_volunteers=n_volunteers(row.id),
                       info=row.info)
        projects_published.append(project)
    return projects_published


@memoize(timeout=timeouts.get('USER_TIMEOUT'))
def published_projects_cached(user_id):
    """Return published projects (cached version)."""
    return published_projects(user_id)


def public_published_projects(user_id):
    """Return projects that user_id has contributed to. Public information only"""
    unsanitized_projects = published_projects(user_id)
    public_projects = []
    if unsanitized_projects:
        p = Project()
        for project in unsanitized_projects:
            public_project = p.to_public_json(data=project)
            public_projects.append(public_project)
    return public_projects


@memoize(timeout=timeouts.get('USER_TIMEOUT'))
def public_published_projects_cached(user_id):
    """Return published projects (cached version)."""
    return public_published_projects(user_id)


def draft_projects(user_id):
    """Return draft projects for user_id."""
    sql = text('''
               SELECT project.id, project.name, project.short_name, project.description,
               project.owner_id,
               project.owners_ids,
               project.info
               FROM project
               WHERE project.published=false
               AND :user_id = ANY (project.owners_ids::int[]);
               ''')
    projects_draft = []
    results = session.execute(sql, dict(user_id=user_id))
    for row in results:
        project = dict(id=row.id, name=row.name, short_name=row.short_name,
                       owner_id=row.owner_id,
                       owners_ids=row.owners_ids,
                       description=row.description,
                       overall_progress=overall_progress(row.id),
                       n_tasks=n_tasks(row.id),
                       n_volunteers=n_volunteers(row.id),
                       info=row.info)
        projects_draft.append(project)
    return projects_draft


@memoize(timeout=timeouts.get('USER_TIMEOUT'))
def draft_projects_cached(user_id):
    """Return draft projects (cached version)."""
    return draft_projects(user_id)


@cache(timeout=timeouts.get('USER_TOTAL_TIMEOUT'),
       key_prefix="site_total_users")
def get_total_users():
    """Return total number of users in the server."""
    count = User.query.filter(User.enabled == True).count()
    return count


@memoize(timeout=timeouts.get('USER_TIMEOUT'))
def get_users_page(page, per_page=24):
    """Return users with a paginator."""
    offset = (page - 1) * per_page
    sql = text('''SELECT "user".id, "user".name,
               "user".fullname, "user".email_addr,
               "user".created, "user".info, COUNT(task_run.id) AS task_runs
               FROM task_run, "user"
               WHERE "user".id=task_run.user_id GROUP BY "user".id
               ORDER BY "user".created DESC LIMIT :limit OFFSET :offset''')
    results = session.execute(sql, dict(limit=per_page, offset=offset))
    accounts = []

    u = User()

    for row in results:
        user = dict(id=row.id, name=row.name, fullname=row.fullname,
                    email_addr=row.email_addr, created=row.created,
                    task_runs=row.task_runs, info=row.info,
                    registered_ago=pretty_date(row.created))
        tmp = u.to_public_json(data=user)
        accounts.append(tmp)
    return accounts


def delete_user_summary_id(oid):
    """Delete from cache the user summary."""
    user = db.session.query(User).get(oid)
    delete_memoized(get_user_summary, user.name)


def delete_user_summary(name):
    """Delete from cache the user summary."""
    delete_memoized(get_user_summary, name)


@memoize(timeout=timeouts.get('APP_TIMEOUT'))
def get_user_pref_metadata(name):
    sql = text("""
    SELECT info->'metadata', user_pref, info->'data_access' FROM "user" WHERE name=:name;
    """)
    cursor = session.execute(sql, dict(name=name))
    row = cursor.fetchone()
    upref_mdata = row[0] or {}
    upref_mdata.update(row[1] or {})
    if data_access_levels:
        upref_mdata['data_access'] = row[2] or []

    if 'locations' in upref_mdata:
        map_locations_upref_mdata(upref_mdata)
    return upref_mdata


def map_locations_upref_mdata(upref_mdata):
    mapped = map_locations(upref_mdata['locations'])

    upref_mdata['country_codes'] = mapped['country_codes']
    upref_mdata['country_names'] = mapped['country_names']
    upref_mdata['locations'] = mapped['locations']


def delete_user_pref_metadata(user):
    delete_memoized(get_user_pref_metadata, user.name)
    delete_memoized(get_user_by_id, user.id)


@memoize(timeout=timeouts.get('APP_TIMEOUT'))
def get_taskbrowse_bookmarks(name):
    sql = text("""
    SELECT info->'taskbrowse_bookmarks' FROM "user" WHERE name=:name;
    """)
    cursor = session.execute(sql, dict(name=name))
    row = cursor.fetchone()
    taskbrowse_bookmarks = row[0] or {}
    return taskbrowse_bookmarks


def delete_taskbrowse_bookmarks(user):
    delete_memoized(get_taskbrowse_bookmarks, user.name)
    delete_memoized(get_user_by_id, user.id)


def get_user_preferences(user_id):
    user = get_user_by_id(user_id)
    user_pref = user.user_pref or {} if user else {}
    user_email = user.email_addr if user else None
    if 'locations' in user_pref:
        map_locations_upref_mdata(user_pref)
    return get_user_pref_db_clause(user_pref, user_email)


def get_user_filters(user_id):
    user_profile = get_user_profile_metadata(user_id)
    user_profile = json.loads(user_profile) if user_profile else {}
    return get_user_filter_db_clause(user_profile)


@memoize(timeout=ONE_DAY)
def get_user_by_id(user_id):
    assert user_id is not None or user_id > 0
    user = User.query.get(user_id)
    return user


def get_user_profile_metadata(user_id):
    user = get_user_by_id(user_id)
    info = user.info or {} if user else {}
    return info.get("metadata", {}).get('profile')


def get_user_email(user_id):
    user = get_user_by_id(user_id)
    return user.email_addr if user else None


@memoize(timeout=timeouts.get('USER_TIMEOUT'))
def get_users_for_report():
    """Return information for all users to generate report."""
    sql = text("""
        SELECT u.id AS u_id,
            name, fullname, email_addr, u.created, admin, enabled, locale,
            subadmin, consent, restrict,
            user_pref->'languages' AS languages,
            user_pref->'locations' AS locations,
            u.info->'metadata'->'work_hours_from' AS work_hours_from,
            u.info->'metadata'->'work_hours_to' AS work_hours_to,
            u.info->'metadata'->'timezone' AS timezone,
            u.info->'metadata'->'user_type' AS type_of_user,
            u.info->'metadata'->'review' AS additional_comments,
            count(t.id) AS completed_task_runs,
            min(finish_time) AS first_submission_date,
            max(finish_time) AS last_submission_date,
            coalesce(
                AVG(to_timestamp(finish_time, 'YYYY-MM-DD"T"HH24-MI-SS.US') - to_timestamp(t.created, 'YYYY-MM-DD"T"HH24-MI-SS.US')),
                interval '0s') AS avg_time_per_task
        FROM "user" u LEFT JOIN task_run t ON u.id = t.user_id
        WHERE u.restrict=False AND u.email_addr NOT LIKE 'del-%@del.com'
        GROUP BY u.id;
    """)
    results = session.execute(sql)
    users_report = [ dict(id=row.u_id, name=row.name, fullname=row.fullname,
                    email_addr=row.email_addr, created=row.created, locale=row.locale,
                    admin=row.admin, subadmin=row.subadmin, enabled=row.enabled, languages=row.languages,
                    locations=row.locations, work_hours_from=row.work_hours_from,
                    work_hours_to=row.work_hours_to, timezone=row.timezone,
                    additional_comments=row.additional_comments,
                    type_of_user=row.type_of_user, first_submission_date=row.first_submission_date,
                    last_submission_date=row.last_submission_date,
                    completed_task_runs=row.completed_task_runs, avg_time_per_task=str(round(row.avg_time_per_task.total_seconds() / 60, 2)),
                    total_projects_contributed=n_projects_contributed(row.u_id),
                    percentage_tasks_completed=round(float(row.completed_task_runs) * 100 / n_total_tasks(), 2) if n_total_tasks() else 0,
                    consent=row.consent, restrict=row.restrict)
                    for row in results]
    return users_report


@memoize(timeout=timeouts.get('APP_TIMEOUT'))
def get_project_report_userdata(project_id, start_date, end_date):
    """Return users details who contributed to a particular project."""
    date_clause, sql_params = get_taskrun_date_range_sql_clause_params(start_date, end_date)
    sql_params["project_id"] = project_id
    sql_params["total_tasks"] = n_tasks(project_id)
    sql = text(
            '''
            SELECT id as u_id, name, fullname, email_addr, admin, subadmin, enabled,
            user_pref->'languages' AS languages, user_pref->'locations' AS locations,
            info->'metadata'->'work_hours_from' AS work_hours_from, info->'metadata'->'work_hours_to' AS work_hours_to,
            info->'metadata'->'timezone' AS timezone, info->'metadata'->'user_type' AS type_of_user,
            info->'metadata'->'review' AS additional_comments,
            (SELECT count(id) FROM task_run WHERE user_id = u.id AND project_id=:project_id''' + date_clause +''') AS completed_tasks,
            ((SELECT count(id) FROM task_run WHERE user_id = u.id AND project_id =:project_id''' + date_clause +''') * 100 / :total_tasks) AS percent_completed_tasks,
            (SELECT min(finish_time) FROM task_run WHERE user_id = u.id AND project_id=:project_id''' + date_clause +''') AS first_submission_date,
            (SELECT max(finish_time) FROM task_run WHERE user_id = u.id AND project_id=:project_id''' + date_clause +''') AS last_submission_date,
            (SELECT coalesce(AVG(to_timestamp(finish_time, 'YYYY-MM-DD"T"HH24-MI-SS.US') -
            to_timestamp(created, 'YYYY-MM-DD"T"HH24-MI-SS.US')), interval '0s')
            FROM task_run WHERE user_id = u.id AND project_id=:project_id''' + date_clause +''') AS avg_time_per_task
            FROM "user" u WHERE id IN
            (SELECT DISTINCT user_id FROM task_run GROUP BY project_id, user_id HAVING project_id=:project_id);
            ''')
    results = session.execute(sql, sql_params)
    users_report = [
        [row.u_id, row.name, row.fullname, row.email_addr,
         row.admin, row.subadmin, row.enabled, row.languages,
         row.locations, row.work_hours_from, row.work_hours_to,
         row.timezone, row.type_of_user, row.additional_comments,
         row.completed_tasks, row.percent_completed_tasks,
         row.first_submission_date, row.last_submission_date,
         round(row.avg_time_per_task.total_seconds() / 60, 2)]
         for row in results]
    return users_report


@memoize(timeout=ONE_WEEK)
def get_user_info(user_id):
    sql = text('''select name, email_addr from "user" where
                  id=:user_id''')
    user = session.execute(sql, dict(user_id=user_id)).first()
    return dict(user) if user else None


@memoize(timeout=timeouts.get('USER_TIMEOUT'))
def get_announcements_by_level_cached(level):
    sql = text('''
        SELECT id, title, body
        FROM announcement
        WHERE (published = TRUE AND ((info->>'level')::int >= :level))''')
    results = session.execute(sql, dict(level=level))
    return [dict(row) for row in results]


def get_announcements_cached(user, announcement_levels):
    if not (announcement_levels and user and user.is_authenticated):
        return []
    level = announcement_levels['user']['level']
    if user.admin:
        level = announcement_levels['admin']['level']
    elif user.subadmin:
        level = announcement_levels['subadmin']['level']
    return get_announcements_by_level_cached(level)


def get_users_for_data_access(data_access):
    from pybossa.data_access import get_user_data_access_db_clause

    sql = '''select id::text, fullname, email_addr, enabled from "user"'''
    clause = get_user_data_access_db_clause(data_access)
    sql = sql +  '''where {}'''.format(clause) if clause else sql
    results = session.execute(sql).fetchall()
    return [dict(row) for row in results]


def get_users_access_levels(users):

    if not users:
        return []

    all(int(u) for u in users)
    users = ', '.join(map(str, users))
    sql = text('''select id, info->'data_access' as data_access from "user"
        where id in({})'''.format(users))
    results = session.execute(sql).fetchall()
    return [dict(row) for row in results]


def delete_published_projects(user_id):
    """Delete from cache the users (un)published project."""
    delete_memoized(draft_projects_cached, user_id)
    delete_memoized(published_projects_cached, user_id)


@memoize(timeout=FIVE_MINUTES)
def get_tasks_completed_between(user_id, beginning_time_utc, end_time_utc=None):
    timestamp_tmpl = 'TO_TIMESTAMP({}, \'YYYY-MM-DD"T"HH24:MI:SS.US\')'
    created_timestamp = timestamp_tmpl.format('created')
    end_time_fragment = ''
    if end_time_utc:
        end_timestamp = timestamp_tmpl.format('\'{}\''.format(end_time_utc))
        end_time_fragment = 'AND {} <= {}'.format(created_timestamp, end_timestamp)
    beginning_timestamp = timestamp_tmpl.format('\'{}\''.format(beginning_time_utc))
    sql = text('''
        SELECT id, created
        FROM "task_run"
        WHERE user_id = {} AND {} >= {} {}
    '''.format(str(user_id), created_timestamp, beginning_timestamp, end_time_fragment))
    results = session.execute(sql)
    return [dict(row) for row in results]
