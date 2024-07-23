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
"""
PYBOSSA api module for exposing domain objects via an API.

This package adds GET, POST, PUT and DELETE methods for:
    * projects,
    * categories,
    * tasks,
    * task_runs,
    * users,
    * global_stats,
"""

from functools import partial
import json
import jwt
from flask import Blueprint, request, abort, Response, make_response
from flask import current_app
from flask_login import current_user, login_required
from time import time
from datetime import datetime, timedelta
from werkzeug.exceptions import NotFound
from pybossa.util import (
    jsonpify,
    get_user_id_or_ip,
    fuzzyboolean,
    PARTIAL_ANSWER_KEY,
    SavedTaskPositionEnum,
    PARTIAL_ANSWER_POSITION_KEY,
    get_user_saved_partial_tasks,
)
from pybossa.util import get_disqus_sso_payload, grant_access_with_api_key
import dateutil.parser
import pybossa.model as model
from pybossa.core import csrf, ratelimits, sentinel, anonymizer
from pybossa.ratelimit import ratelimit
from pybossa.cache.projects import n_tasks, n_completed_tasks
import pybossa.sched as sched
from pybossa.util import sign_task, can_update_user_info
from pybossa.error import ErrorStatus
from .global_stats import GlobalStatsAPI
from .task import TaskAPI
from .task_run import TaskRunAPI, preprocess_task_run
from .project import ProjectAPI
from .auditlog import AuditlogAPI
from .announcement import AnnouncementAPI
from .blogpost import BlogpostAPI
from .category import CategoryAPI
from .favorites import FavoritesAPI
from pybossa.api.performance_stats import PerformanceStatsAPI
from .user import UserAPI
from .token import TokenAPI
from .result import ResultAPI
from rq import Queue
from .project_stats import ProjectStatsAPI
from .helpingmaterial import HelpingMaterialAPI
from pybossa.core import auditlog_repo, project_repo, task_repo, user_repo
from pybossa.contributions_guard import ContributionsGuard
from pybossa.auth import jwt_authorize_project
from werkzeug.exceptions import MethodNotAllowed, Forbidden
from .completed_task import CompletedTaskAPI
from .completed_task_run import CompletedTaskRunAPI
from pybossa.cache.helpers import (
    n_available_tasks,
    n_available_tasks_for_user,
    n_unexpired_gold_tasks,
)
from pybossa.sched import (
    get_scheduler_and_timeout,
    has_lock,
    release_lock,
    Schedulers,
    fetch_lock_for_user,
    release_reserve_task_lock_by_id,
)
from pybossa.jobs import send_mail
from pybossa.api.project_by_name import ProjectByNameAPI, project_name_to_oid
from pybossa.api.project_details import ProjectDetailsAPI
from pybossa.api.project_locks import ProjectLocksAPI
from pybossa.api.pwd_manager import get_pwd_manager
from pybossa.data_access import data_access_levels
from pybossa.task_creator_helper import set_gold_answers
from pybossa.auth.task import TaskAuth
from pybossa.service_validators import ServiceValidators
import requests
from sqlalchemy.sql import text
from sqlalchemy.orm.attributes import flag_modified
from pybossa.core import db
from pybossa.cache import users as cached_users, ONE_MONTH
from pybossa.cache.task_browse_helpers import get_searchable_columns
from pybossa.cache.users import get_user_pref_metadata
from pybossa.view.projects import get_locked_tasks
from pybossa.redis_lock import EXPIRE_LOCK_DELAY
from pybossa.api.bulktasks import BulkTasksAPI

task_fields = [
    "id",
    "state",
    "n_answers",
    "created",
    "calibration",
]

blueprint = Blueprint("api", __name__)

error = ErrorStatus()
mail_queue = Queue("email", connection=sentinel.master)


@blueprint.route("/")
@ratelimit(limit=ratelimits.get("LIMIT"), per=ratelimits.get("PER"))
def index():  # pragma: no cover
    """Return dummy text for welcome page."""
    return "The %s API" % current_app.config.get("BRAND")


@blueprint.before_request
def _api_authentication_with_api_key():
    """Allow API access with valid api_key."""
    secure_app_access = current_app.config.get("SECURE_APP_ACCESS", False)
    if secure_app_access:
        grant_access_with_api_key(secure_app_access)


def register_api(view, endpoint, url, pk="id", pk_type="int"):
    """Register API endpoints.

    Registers new end points for the API using classes.

    """
    view_func = view.as_view(endpoint)
    csrf.exempt(view_func)
    blueprint.add_url_rule(
        url,
        endpoint=endpoint,
        view_func=view_func,
        defaults={pk: None},
        methods=["GET", "OPTIONS"],
    )
    blueprint.add_url_rule(
        url, endpoint=endpoint, view_func=view_func, methods=["POST", "OPTIONS"]
    )
    blueprint.add_url_rule(
        "%s/<%s:%s>" % (url, pk_type, pk),
        endpoint=endpoint + "_" + pk,
        view_func=view_func,
        methods=["GET", "PUT", "DELETE", "OPTIONS"],
    )


register_api(ProjectAPI, 'api_project', '/project', pk='oid', pk_type='int')
register_api(ProjectStatsAPI, 'api_projectstats', '/projectstats', pk='oid', pk_type='int')
register_api(CategoryAPI, 'api_category', '/category', pk='oid', pk_type='int')
register_api(TaskAPI, 'api_task', '/task', pk='oid', pk_type='int')
register_api(AuditlogAPI, 'api_auditlog', '/auditlog', pk='oid', pk_type='int')
register_api(TaskRunAPI, 'api_taskrun', '/taskrun', pk='oid', pk_type='int')
register_api(ResultAPI, 'api_result', '/result', pk='oid', pk_type='int')
register_api(UserAPI, 'api_user', '/user', pk='oid', pk_type='int')
register_api(AnnouncementAPI, 'api_announcement', '/announcement', pk='oid', pk_type='int')
register_api(BlogpostAPI, 'api_blogpost', '/blogpost', pk='oid', pk_type='int')
register_api(HelpingMaterialAPI, 'api_helpingmaterial',
             '/helpingmaterial', pk='oid', pk_type='int')
register_api(GlobalStatsAPI, 'api_globalstats', '/globalstats',
             pk='oid', pk_type='int')
register_api(FavoritesAPI, 'api_favorites', '/favorites',
             pk='oid', pk_type='int')
register_api(TokenAPI, 'api_token', '/token', pk='token', pk_type='string')
register_api(CompletedTaskAPI, 'api_completedtask', '/completedtask', pk='oid', pk_type='int')
register_api(CompletedTaskRunAPI, 'api_completedtaskrun', '/completedtaskrun', pk='oid', pk_type='int')
register_api(ProjectByNameAPI, 'api_projectbyname', '/projectbyname', pk='key', pk_type='string')
register_api(ProjectDetailsAPI, 'api_projectdetails', '/projectdetails', pk='oid', pk_type='int')
register_api(ProjectLocksAPI, 'api_projectlocks', '/locks', pk='oid', pk_type='int')
register_api(PerformanceStatsAPI, 'api_performancestats', '/performancestats', pk='oid', pk_type='int')
register_api(BulkTasksAPI, 'api_bulktasks', '/bulktasks', pk='oid', pk_type='int')


def add_task_signature(tasks):
    if current_app.config.get("ENABLE_ENCRYPTION"):
        for task in tasks:
            sign_task(task)


@jsonpify
@blueprint.route("/project/<project_id>/newtask")
@blueprint.route("/project/<project_id>/newtask/<int:task_id>")
@ratelimit(limit=ratelimits.get("LIMIT"), per=ratelimits.get("PER"))
def new_task(project_id, task_id=None):
    """Return a new task for a project."""
    # Check the value of saved_task_position from Redis:
    saved_task_position = None
    if not current_user.is_anonymous:
        position_key = PARTIAL_ANSWER_POSITION_KEY.format(
            project_id=project_id, user_id=current_user.id
        )
        saved_task_position = sentinel.master.get(position_key)
        if saved_task_position:
            try:
                saved_task_position = SavedTaskPositionEnum(
                    saved_task_position.decode("utf-8")
                )
            except ValueError as e:
                pass

    # Check if the request has an arg:
    try:
        tasks, timeout, cookie_handler = _retrieve_new_task(
            project_id, task_id, saved_task_position
        )

        if type(tasks) is Response:
            return tasks

        user_id_or_ip = get_user_id_or_ip()
        # If there is a task for the user, return it
        if tasks is not None:
            guard = ContributionsGuard(sentinel.master, timeout=timeout)
            for task in tasks:
                guard.stamp(task, user_id_or_ip)
                if not guard.check_task_presented_timestamp(task, user_id_or_ip):
                    guard.stamp_presented_time(task, user_id_or_ip)
                else:
                    # user returning back for the same task
                    # original presented time has not expired yet
                    # to continue original presented time, extend expiry
                    guard.extend_task_presented_timestamp_expiry(task, user_id_or_ip)

            data = [TaskAuth.dictize_with_access_control(task) for task in tasks]
            add_task_signature(data)
            if len(data) == 0:
                response = make_response(json.dumps({}))
            elif len(data) == 1:
                response = make_response(json.dumps(data[0]))
            else:
                response = make_response(json.dumps(data))
            response.mimetype = "application/json"
            cookie_handler(response)
            return response
        return Response(json.dumps({}), mimetype="application/json")
    except Exception as e:
        return error.format_exception(e, target="project", action="GET")


def _retrieve_new_task(project_id, task_id=None, saved_task_position=None):
    project = project_repo.get(project_id)
    if project is None or not (
        project.published or current_user.admin or current_user.id in project.owners_ids
    ):
        raise NotFound

    if current_user.is_anonymous:
        info = dict(error="This project does not allow anonymous contributors")
        error = [model.task.Task(info=info)]
        return error, None, lambda x: x

    if current_user.get_quiz_failed(project):
        # User is blocked from project so don't return a task
        return None, None, None

    # check cookie
    pwd_manager = get_pwd_manager(project)
    user_id_or_ip = get_user_id_or_ip()
    if pwd_manager.password_needed(project, user_id_or_ip):
        raise Forbidden("No project password provided")

    if request.args.get("external_uid"):
        resp = jwt_authorize_project(project, request.headers.get("Authorization"))
        if resp != True:
            return resp, lambda x: x

    if request.args.get("limit"):
        limit = int(request.args.get("limit"))
    else:
        limit = 1

    if limit > 100:
        limit = 100

    if request.args.get("offset"):
        offset = int(request.args.get("offset"))
    else:
        offset = 0

    if request.args.get("orderby"):
        orderby = request.args.get("orderby")
    else:
        orderby = "id"

    if request.args.get("desc"):
        desc = fuzzyboolean(request.args.get("desc"))
    else:
        desc = False

    user_id = None if current_user.is_anonymous else current_user.id
    user_ip = (
        anonymizer.ip(request.remote_addr or "127.0.0.1")
        if current_user.is_anonymous
        else None
    )
    external_uid = request.args.get("external_uid")
    sched_rand_within_priority = project.info.get("sched_rand_within_priority", False)

    user = user_repo.get(user_id)
    if (
        project.published
        and user_id != project.owner_id
        and user_id not in project.owners_ids
        and user.get_quiz_not_started(project)
        and user.get_quiz_enabled(project)
        and not task_repo.get_user_has_task_run_for_project(project_id, user_id)
    ):
        user.set_quiz_status(project, "in_progress")

    # We always update the user even if we didn't change the quiz status.
    # The reason for that is the user.<?quiz?> methods take a snapshot of the project's quiz
    # config the first time it is accessed for a user and save that snapshot
    # with the user. So we want to commit that snapshot if this is the first access.
    user_repo.update(user)

    # Allow scheduling a gold-only task if quiz mode is enabled for the user and the project.
    quiz_mode_enabled = (
        user.get_quiz_in_progress(project) and project.info["quiz"]["enabled"]
    )

    task = sched.new_task(
        project.id,
        project.info.get("sched"),
        user_id,
        user_ip,
        external_uid,
        offset,
        limit,
        orderby=orderby,
        desc=desc,
        rand_within_priority=sched_rand_within_priority,
        gold_only=quiz_mode_enabled,
        task_id=task_id,
        saved_task_position=saved_task_position,
    )

    handler = partial(pwd_manager.update_response, project=project, user=user_id_or_ip)
    return task, project.info.get("timeout"), handler


def _guidelines_updated(project_id, user_id):
    """Function to determine if guidelines has been
    updated since last submission"""

    query_attrs_log = dict(
        project_id=project_id, attribute="task_guidelines", desc=True
    )
    query_attrs_task_run = dict(project_id=project_id, user_id=user_id)

    guidelines_log = auditlog_repo.filter_by(limit=1, **query_attrs_log)
    last_guidelines_update = (
        dateutil.parser.parse(guidelines_log[0].created) if guidelines_log else None
    )
    task_runs = task_repo.filter_task_runs_by(
        limit=1, desc=True, **query_attrs_task_run
    )
    last_task_run_time = (
        dateutil.parser.parse(task_runs[0].created) if task_runs else None
    )

    return (
        last_task_run_time < last_guidelines_update
        if last_task_run_time and last_guidelines_update
        else False
    )


@jsonpify
@blueprint.route("/app/<short_name>/userprogress")
@blueprint.route("/project/<short_name>/userprogress")
@blueprint.route("/app/<int:project_id>/userprogress")
@blueprint.route("/project/<int:project_id>/userprogress")
@ratelimit(limit=ratelimits.get("LIMIT"), per=ratelimits.get("PER"))
def user_progress(project_id=None, short_name=None):
    """API endpoint for user progress.

    Return a JSON object with four fields regarding the tasks for the user:
        { 'done': 10,
          'total: 100,
          'remaining': 90,
          'remaining_for_user': 45
        }
       This will mean that the user has done 10% of the available tasks for the
       project, 90 tasks are yet to be submitted and the user can access 45 of
       them based on user preferences.

    """
    if current_user.is_anonymous:
        return abort(401)
    if project_id or short_name:
        if short_name:
            project = project_repo.get_by_shortname(short_name)
        elif project_id:
            project = project_repo.get(project_id)

        if project:
            # For now, keep this version, but wait until redis cache is
            # used here for task_runs too
            query_attrs = dict(project_id=project.id, user_id=current_user.id)
            guidelines_updated = _guidelines_updated(project.id, current_user.id)
            taskrun_count = task_repo.count_task_runs_with(**query_attrs)
            num_available_tasks = n_available_tasks(project.id, include_gold_task=True)
            num_available_tasks_for_user = n_available_tasks_for_user(
                project, current_user.id
            )
            response = dict(
                done=taskrun_count,
                total=n_tasks(project.id),
                completed=n_completed_tasks(project.id),
                remaining=num_available_tasks,
                locked=len({task["task_id"] for task in get_locked_tasks(project)}),
                remaining_for_user=num_available_tasks_for_user,
                quiz=current_user.get_quiz_for_project(project),
                guidelines_updated=guidelines_updated,
            )
            if current_user.admin or (
                current_user.subadmin and current_user.id in project.owners_ids
            ):
                num_gold_tasks = n_unexpired_gold_tasks(project.id)
                response["available_gold_tasks"] = num_gold_tasks
            return Response(json.dumps(response), mimetype="application/json")
        else:
            return abort(404)
    else:  # pragma: no cover
        return abort(404)


@jsonpify
@blueprint.route("/app/<short_name>/taskprogress")
@blueprint.route("/project/<short_name>/taskprogress")
@blueprint.route("/app/<int:project_id>/taskprogress")
@blueprint.route("/project/<int:project_id>/taskprogress")
@ratelimit(limit=ratelimits.get("LIMIT"), per=ratelimits.get("PER"))
def task_progress(project_id=None, short_name=None):
    """API endpoint for task progress.

    Returns a JSON object continaing the number of tasks which meet the user defined filter constraints
    """
    if current_user.is_anonymous:
        return abort(401)
    if not (project_id or short_name):
        return abort(404)
    if short_name:
        project = project_repo.get_by_shortname(short_name)
    elif project_id:
        project = project_repo.get(project_id)
    filter_fields = request.args
    if not project:
        return abort(404)

    sql_text = "SELECT COUNT(*) FROM task WHERE project_id=" + str(project.id)
    task_info_fields = get_searchable_columns(project.id)

    # create sql query from filter fields received on request.args
    for key in filter_fields.keys():
        if key in task_fields:
            sql_text += " AND {0}=:{1}".format(key, key)
        elif key in task_info_fields:
            # include support for empty string and null in URL
            if filter_fields[key].lower() in ["null", ""]:
                sql_text += " AND info ->> '{0}' is Null".format(key)
            else:
                sql_text += " AND info ->> '{0}'=:{1}".format(key, key)
        else:
            raise Exception(
                "invalid key: the field that you are filtering by does not exist"
            )
    sql_text += ";"
    sql_query = text(sql_text)
    results = db.slave_session.execute(sql_query, filter_fields)
    timeout = current_app.config.get("TIMEOUT")

    # results are stored as a sqlalchemy resultProxy
    num_tasks = results.first()[0]
    task_count_dict = dict(task_count=num_tasks)
    return Response(json.dumps(task_count_dict), mimetype="application/json")


@jsonpify
@login_required
@blueprint.route("/preferences/<user_name>", methods=["GET"])
@ratelimit(limit=ratelimits.get("LIMIT"), per=ratelimits.get("PER"))
def get_user_preferences(user_name):
    """API endpoint for loading account user preferences.
    Returns a JSON object containing the user account preferences.
    """
    user = user_repo.get_by_name(user_name)
    if not user:
        return abort(404)

    try:
        (can_update, disabled_fields, hidden_fields) = can_update_user_info(
            current_user, user
        )
    except Exception:
        return abort(404)

    if not can_update or hidden_fields:
        return abort(403)

    user_preferences = get_user_pref_metadata(user_name)

    return Response(json.dumps(user_preferences), mimetype="application/json")


@jsonpify
@login_required
@csrf.exempt
@blueprint.route("/preferences/<user_name>", methods=["POST"])
@ratelimit(limit=ratelimits.get("LIMIT"), per=ratelimits.get("PER"))
def update_user_preferences(user_name):
    """API endpoint for updating account user preferences.
    Returns a JSON object containing the updated user account preferences.
    """
    user = user_repo.get_by_name(user_name)
    if not user:
        return abort(404)

    try:
        (can_update, disabled_fields, hidden_fields) = can_update_user_info(
            current_user, user
        )
    except Exception:
        return abort(404)

    if not can_update or disabled_fields:
        return abort(403)

    payload = (
        json.loads(request.form["request_json"])
        if "request_json" in request.form
        else request.json
    )

    # User must post a payload or empty json object {}.
    if not payload and payload != {}:
        return abort(400)

    user_preferences = None
    if user:
        # Add a metadata section if not found.
        if "metadata" not in user.info:
            user.info["metadata"] = {}

        # Update user preferences value.
        user.info.get("metadata", {})["profile"] = (
            json.dumps(payload) if payload else ""
        )

        # Set dirty flag on user.info['metadata']['profile']
        flag_modified(user, "info")

        # Save user preferences.
        user_repo.update(user)

        # Clear user in cache.
        cached_users.delete_user_pref_metadata(user)

        # Return updated metadata and user preferences.
        user_preferences = user.info.get("metadata", {})

    return Response(json.dumps(user_preferences), mimetype="application/json")


@jsonpify
@blueprint.route("/auth/project/<short_name>/token")
@ratelimit(limit=ratelimits.get("LIMIT"), per=ratelimits.get("PER"))
def auth_jwt_project(short_name):
    """Create a JWT for a project via its secret KEY."""
    project_secret_key = None
    if "Authorization" in request.headers:
        project_secret_key = request.headers.get("Authorization")
    if project_secret_key:
        project = project_repo.get_by_shortname(short_name)
        if project and project.secret_key == project_secret_key:
            token = jwt.encode(
                {"short_name": short_name, "project_id": project.id},
                project.secret_key,
                algorithm="HS256",
            )
            return token
        else:
            return abort(404)
    else:
        return abort(403)


@jsonpify
@blueprint.route("/disqus/sso")
@ratelimit(limit=ratelimits.get("LIMIT"), per=ratelimits.get("PER"))
def get_disqus_sso_api():
    """Return remote_auth_s3 and api_key for disqus SSO."""
    try:
        if current_user.is_authenticated:
            message, timestamp, sig, pub_key = get_disqus_sso_payload(current_user)
        else:
            message, timestamp, sig, pub_key = get_disqus_sso_payload(None)

        if message and timestamp and sig and pub_key:
            remote_auth_s3 = "%s %s %s" % (message, sig, timestamp)
            tmp = dict(remote_auth_s3=remote_auth_s3, api_key=pub_key)
            return Response(json.dumps(tmp), mimetype="application/json")
        else:
            raise MethodNotAllowed
    except MethodNotAllowed as e:
        e.message = "Disqus keys are missing"
        return error.format_exception(e, target="DISQUS_SSO", action="GET")


@jsonpify
@csrf.exempt
@blueprint.route("/task/<int:task_id>/canceltask", methods=["POST"])
@ratelimit(limit=ratelimits.get("LIMIT"), per=ratelimits.get("PER"))
def cancel_task(task_id=None):
    """Unlock task upon cancel so that same task can be presented again."""
    if not current_user.is_authenticated:
        return abort(401)

    data = request.json
    projectname = data.get("projectname", None)
    project = project_repo.get_by_shortname(projectname)
    if not project:
        return abort(400)

    user_id = current_user.id
    scheduler, timeout = get_scheduler_and_timeout(project)
    if scheduler in (Schedulers.locked, Schedulers.user_pref, Schedulers.task_queue):
        task_locked_by_user = has_lock(task_id, user_id, timeout)
        if task_locked_by_user:
            release_lock(task_id, user_id, timeout)
            current_app.logger.info(
                "Project {} - user {} cancelled task {}".format(
                    project.id, current_user.id, task_id
                )
            )
            release_reserve_task_lock_by_id(
                project.id,
                task_id,
                current_user.id,
                timeout,
                expiry=EXPIRE_LOCK_DELAY,
                release_all_task=True,
            )

    return Response(json.dumps({"success": True}), 200, mimetype="application/json")


@jsonpify
@csrf.exempt
@login_required
@blueprint.route("/task/<int:task_id>/release_category_locks", methods=["POST"])
@ratelimit(limit=ratelimits.get("LIMIT"), per=ratelimits.get("PER"))
def release_category_locks(task_id=None):
    """Unlock all category (reservation) locks reserved by this user"""
    if not current_user.is_authenticated:
        return abort(401)

    project_name = request.json.get("projectname", None)
    project = project_repo.get_by_shortname(project_name)
    if not project:
        return abort(400)

    scheduler, timeout = get_scheduler_and_timeout(project)
    if scheduler == Schedulers.task_queue:
        release_reserve_task_lock_by_id(
            project.id,
            task_id,
            current_user.id,
            timeout,
            expiry=EXPIRE_LOCK_DELAY,
            release_all_task=True,
        )

    return Response(json.dumps({"success": True}), 200, mimetype="application/json")


@jsonpify
@blueprint.route("/task/<int:task_id>/lock", methods=["GET"])
@ratelimit(limit=ratelimits.get("LIMIT"), per=ratelimits.get("PER"))
def fetch_lock(task_id):
    """Fetch the time (in seconds) until the current user's
    lock on a task expires.
    """
    if not current_user.is_authenticated:
        return abort(401)

    task = task_repo.get_task(task_id)
    if not task:
        return abort(400)

    project = project_repo.get(task.project_id)
    if not project:
        return abort(400)

    _, ttl = fetch_lock_for_user(task.project_id, task.id, current_user.id)
    if not ttl:
        return abort(404)

    timeout = project.info.get("timeout", ContributionsGuard.STAMP_TTL)

    seconds_to_expire = float(ttl) - time()
    lock_time = datetime.utcnow() - timedelta(seconds=timeout - seconds_to_expire)

    res = json.dumps(
        {
            "success": True,
            "expires": seconds_to_expire,
            "lockTime": lock_time.isoformat(),
        }
    )

    return Response(res, 200, mimetype="application/json")


@jsonpify
@csrf.exempt
@blueprint.route("/project/<int:project_id>/taskgold", methods=["GET", "POST"])
@ratelimit(limit=ratelimits.get("LIMIT"), per=ratelimits.get("PER"))
def task_gold(project_id=None):
    """Make task gold"""
    try:
        if not current_user.is_authenticated:
            return abort(401)

        project = project_repo.get(project_id)

        # Allow project owner, sub-admin co-owners, and admins to update Gold tasks.
        is_gold_access = (
            current_user.subadmin and current_user.id in project.owners_ids
        ) or current_user.admin
        if project is None or not is_gold_access:
            raise Forbidden
        if request.method == "POST":
            task_data = (
                json.loads(request.form["request_json"])
                if "request_json" in request.form
                else request.json
            )
            task_id = task_data["task_id"]
            task = task_repo.get_task(task_id)
            if task.project_id != project_id:
                raise Forbidden
            preprocess_task_run(project_id, task_id, task_data)
            info = task_data["info"]
            set_gold_answers(task, info)
            task_repo.update(task)

            response_body = json.dumps({"success": True})
        else:
            task = sched.select_task_for_gold_mode(project, current_user.id)
            if task:
                task = task.dictize()
                sign_task(task)
            response_body = json.dumps(task)
        return Response(response_body, 200, mimetype="application/json")
    except Exception as e:
        return error.format_exception(e, target="taskgold", action=request.method)


@jsonpify
@login_required
@csrf.exempt
@blueprint.route(
    "/task/<task_id>/services/<service_name>/<major_version>/<minor_version>",
    methods=["POST"],
)
@ratelimit(limit=ratelimits.get("LIMIT"), per=ratelimits.get("PER"))
def get_service_request(task_id, service_name, major_version, minor_version):
    """Proxy service call"""
    proxy_service_config = current_app.config.get("PROXY_SERVICE_CONFIG", None)
    task = task_repo.get_task(task_id)
    project = project_repo.get(task.project_id)

    if not (
        task
        and proxy_service_config
        and service_name
        and major_version
        and minor_version
    ):
        return abort(400)

    timeout = project.info.get("timeout", ContributionsGuard.STAMP_TTL)
    task_locked_by_user = has_lock(task.id, current_user.id, timeout)
    payload = request.json if isinstance(request.json, dict) else None
    can_create_gold_tasks = (current_user.subadmin and current_user.id in project.owners_ids) or current_user.admin
    mode = request.args.get('mode')

    if payload and (task_locked_by_user or (mode == "gold" and can_create_gold_tasks)):
        service = _get_valid_service(task_id, service_name, payload, proxy_service_config)
        if isinstance(service, dict):
            url = '{}/{}/{}/{}'.format(proxy_service_config['uri'], service_name, major_version, minor_version)
            headers = service.get('headers')
            ssl_cert = current_app.config.get('SSL_CERT_PATH', True)
            ret = requests.post(url, headers=headers, json=payload['data'], verify=ssl_cert)
            return Response(ret.content, 200, mimetype="application/json")

    current_app.logger.info(
        "Task id {} with lock-status {} by user {} with this payload {} failed.".format(
            task_id, task_locked_by_user, current_user.id, payload
        )
    )
    return abort(403)


def _get_valid_service(task_id, service_name, payload, proxy_service_config):
    service_data = payload.get("data", None)
    service_request = (
        list(service_data.keys())[0]
        if isinstance(service_data, dict) and len(list(service_data.keys())) == 1
        else None
    )
    service = proxy_service_config["services"].get(service_name, None)

    if service and service_request in service["requests"]:
        service_validator = ServiceValidators(service)
        if service_validator.run_validators(service_request, payload):
            return service

    current_app.logger.info(
        "Task {} loaded for user {} failed calling {} service with payload {}".format(
            task_id, current_user.id, service_name, payload
        )
    )

    return abort(403, "The request data failed validation")


@jsonpify
@login_required
@csrf.exempt
@blueprint.route("/task/<int:task_id>/assign", methods=["POST"])
@ratelimit(limit=ratelimits.get("LIMIT"), per=ratelimits.get("PER"))
def assign_task(task_id=None):
    """Assign/Un-assign task to users for locked, user_pref and task_queue schedulers."""
    projectname = request.json.get("projectname", None)
    unassgin = request.json.get("unassgin", False)
    action = "un-assign" if unassgin else "assign"

    a_project = project_repo.get_by_shortname(projectname)
    if not a_project:
        return abort(400, f"Invalid project name {projectname}")

    _, ttl = fetch_lock_for_user(a_project.id, task_id, current_user.id)
    if not ttl:
        current_app.logger.warn(
            "User %s requested for %sing task %s that has not been locked by the user.",
            current_user.fullname,
            action,
            task_id,
        )
        return abort(403, f"A lock is required for {action} a task to a user.")

    # only assign/un-assign the user to the task for user_pref and task_queue scheduler
    scheduler, _ = get_scheduler_and_timeout(a_project)
    if scheduler not in (Schedulers.user_pref, Schedulers.task_queue):
        current_app.logger.warn(
            "Task scheduler for project is set to %s. Cannot %s users %s for task %s",
            scheduler,
            action,
            current_user.fullname,
            task_id,
        )
        return abort(
            403, f"Project scheduler not configured for {action}ing a task to a user."
        )

    t = task_repo.get_task_by(project_id=a_project.id, id=int(task_id))
    user_pref = t.user_pref or {}
    assign_user = user_pref.get("assign_user", [])

    user_email = current_user.email_addr

    if unassgin:  # un-assign the user
        if user_email in assign_user:
            assign_user.remove(user_email)

            if assign_user:
                user_pref["assign_user"] = assign_user
            else:  # assign_user list is empty, delete the key "assign_user"
                del user_pref["assign_user"]

            t.user_pref = user_pref
            flag_modified(t, "user_pref")
            task_repo.update(t)
            current_app.logger.info(
                "User %s un-assigned from task %s", current_user.fullname, task_id
            )
    else:  # assign the user
        if user_email not in assign_user:
            assign_user.append(user_email)
            user_pref["assign_user"] = assign_user
            t.user_pref = user_pref
            flag_modified(t, "user_pref")
            task_repo.update(t)
            current_app.logger.info(
                "User %s assigned to task %s", current_user.fullname, task_id
            )

    return Response(json.dumps({"success": True}), 200, mimetype="application/json")


@jsonpify
@login_required
@csrf.exempt
@blueprint.route(
    "/project/<short_name>/task/<int:task_id>/partial_answer",
    methods=["POST", "GET", "DELETE"],
)
@ratelimit(limit=ratelimits.get("LIMIT"), per=ratelimits.get("PER"))
def partial_answer(task_id=None, short_name=None):
    """Save/Get/Delete partial answer to Redis - this API might be called heavily.
    Try to avoid PostgreSQL DB calls as much as possible"""

    # A DB call but with cache
    project_id = project_name_to_oid(short_name)

    if not project_id:
        return abort(400, f"Invalid project name {short_name}")

    response = {"success": True}
    try:
        partial_answer_key = PARTIAL_ANSWER_KEY.format(
            project_id=project_id, user_id=current_user.id, task_id=task_id
        )
        if request.method == "POST":
            task_id_map = get_user_saved_partial_tasks(
                sentinel, project_id, current_user.id, task_repo
            )
            max_saved_answers = current_app.config.get("MAX_SAVED_ANSWERS", 30)
            if len(task_id_map) >= max_saved_answers:
                return abort(
                    400, f"Saved Tasks Limit Reached. Task Saved to Browser Only."
                )

            ttl = ONE_MONTH
            answer = json.dumps(request.json)
            sentinel.master.setex(partial_answer_key, ttl, answer)
        elif request.method == "GET":
            data = sentinel.master.get(partial_answer_key)
            response["data"] = json.loads(data.decode("utf-8")) if data else ""
        elif request.method == "DELETE":
            sentinel.master.delete(partial_answer_key)
    except Exception as e:
        return error.format_exception(e, target="partial_answer", action=request.method)
    return Response(json.dumps(response), status=200, mimetype="application/json")


@jsonpify
@login_required
@blueprint.route("/project/<short_name>/has_partial_answer")
@ratelimit(limit=ratelimits.get("LIMIT"), per=ratelimits.get("PER"))
def user_has_partial_answer(short_name=None):
    """Check whether the user has any saved partial answer for the project
    by checking the Redis sorted set if values are within the non-expiration range
    """
    if not current_user.is_authenticated:
        return abort(401)

    project_id = project_name_to_oid(short_name)
    task_id_map = get_user_saved_partial_tasks(
        sentinel, project_id, current_user.id, task_repo
    )
    response = {"has_answer": bool(task_id_map)}
    return Response(json.dumps(response), status=200, mimetype="application/json")


@jsonpify
@csrf.exempt
@blueprint.route("/llm", defaults={"model_name": None}, methods=["POST"])
@blueprint.route("/llm/<model_name>", methods=["POST"])
@ratelimit(limit=ratelimits.get("LIMIT"), per=ratelimits.get("PER"))
def large_language_model(model_name):
    """Large language model endpoint
    The JSON data in the POST request can be one of the following:
    {
        "instances": [
            {
                "context": "Identify the company name: Microsoft will release Windows 20 next year.",
                "temperature": 1.0,
                "seed": 12345,
                "repetition_penalty": 1.05
            }
        ]
    }
    or
    {
        "prompts": "Identify the company name: Microsoft will release Windows 20 next year."
    }
    """
    if model_name is None:
        model_name = "mixtral-8x7b-instruct"
    endpoints = current_app.config.get("LLM_ENDPOINTS")
    model_endpoint = endpoints.get(model_name.lower())

    if not model_endpoint:
        return abort(400, f"{model_name} LLM is unsupported on this platform.")

    proxies = current_app.config.get("LLM_PROXIES")

    try:
        data = request.get_json(force=True)
    except:
        return abort(400, "Invalid JSON data")

    if "prompts" not in data and "instances" not in data:
        return abort(400, "The JSON should have either 'prompts' or 'instances'")

    if "prompts" in data:
        prompts = data.get("prompts")
        if not prompts:
            return abort(400, "prompts should not be empty")
        if isinstance(prompts, list):
            prompts = prompts[0]  # Batch request temporarily NOT supported
        if not isinstance(prompts, str):
            return abort(400, f"prompts should be a string or a list of strings")
        data = {
            "instances": [
                {
                    "context": prompts + " ",
                    "temperature": 1.0,
                    "seed": 12345,
                    "repetition_penalty": 1.05,
                }
            ]
        }

    body = {
        "inference_endpoint": model_endpoint,
        "payload": data,
        "access_token": current_app.config.get("AUTOLAB_ACCESS_TOKEN"),
        "user_uuid": current_user.id,
    }
    r = requests.post(
        url=current_app.config.get("INFERENCE_ENDPOINT"), json=body, proxies=proxies
    )
    out = json.loads(r.text)
    predictions = out["inference_response"]["predictions"][0]["output"]
    response = {"Model: ": model_name, "predictions: ": predictions}

    return Response(
        json.dumps(response), status=r.status_code, mimetype="application/json"
    )


@jsonpify
@blueprint.route("/project/<project_id>/gold_annotations")
@ratelimit(limit=ratelimits.get("LIMIT"), per=ratelimits.get("PER"))
def get_gold_annotations(project_id):
    """Obtain all gold tasks under a given project along with consensus built on their annotations"""

    if not current_user.is_authenticated:
        return abort(401)

    project = project_repo.get(project_id)
    if not current_user.admin and not (
        current_user.subadmin and current_user.id in project.owners_ids
    ):
        return abort(403)

    tasks = project_repo.get_gold_annotations(project_id)
    return Response(json.dumps(tasks), status=200, mimetype="application/json")
