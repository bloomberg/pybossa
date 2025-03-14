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

from sqlalchemy.exc import IntegrityError
from sqlalchemy import cast, Date

from pybossa.repositories import Repository
from pybossa.model.task import Task
from pybossa.model.task_run import TaskRun
from pybossa.model import make_timestamp
from pybossa.model.user import User
from pybossa.exc import WrongObjectError, DBIntegrityError
from pybossa.cache import projects as cached_projects
from pybossa.core import uploader
from sqlalchemy import text
from pybossa.cache.task_browse_helpers import get_task_filters
import json
from datetime import datetime, timedelta
from flask import current_app
from sqlalchemy import or_
from sqlalchemy.sql import case as sqlalchemy_case
from pybossa.task_creator_helper import get_task_expiration
import time


class TaskRepository(Repository):
    MIN_REDUNDANCY = 1
    MAX_REDUNDANCY = 1000
    SAVE_ACTION = 'saved'
    UPDATE_ACTION = 'updated'

    # Methods for queries on Task objects
    def get_task(self, id):
        # bytes to unicode string
        if type(id) == bytes:
            id = id.decode()
        return self.db.session.query(Task).get(id)

    def get_task_by(self, **attributes):
        filters, _, _, _ = self.generate_query_from_keywords(Task, **attributes)
        return self.db.session.query(Task).filter(*filters).first()

    def filter_tasks_by(self, limit=None, offset=0, yielded=False,
                        last_id=None, fulltextsearch=None, desc=False,
                        **filters):

        return self._filter_by(Task, limit, offset, yielded, last_id,
                              fulltextsearch, desc, **filters)

    def filter_completed_tasks_gold_tasks_by(self, limit=None, offset=0,
        last_id=None, yielded=False, desc=False, **filters):

        exp = filters.pop('exported', None)
        filters.pop('state', None) # exclude state param
        if exp is not None:
            query = self.db.session.query(Task).\
                filter(or_(Task.state == 'completed', Task.calibration == 1)).\
                filter(Task.exported == exp).\
                filter_by(**filters)
        else:
            query = self.db.session.query(Task).\
                filter(or_(Task.state == 'completed', Task.calibration == 1)).\
                filter_by(**filters)

        results = self._filter_query(query, Task, limit, offset, last_id, yielded, desc)
        return results

    def filter_completed_taskruns_gold_taskruns_by(self, limit=None, offset=0,
        last_id=None, yielded=False, desc=False, **filters):

        exp = filters.pop('exported', None)
        finish_time = filters.pop('finish_time', None)
        filters.pop('state', None) # exclude state param

        conditions = []
        if exp:
            conditions.append(Task.exported == exp)
        if finish_time:
            conditions.append(TaskRun.finish_time >= finish_time)

        query = self.db.session.query(TaskRun).join(Task).\
            filter(or_(Task.state == 'completed', Task.calibration == 1)).\
            filter(*conditions).\
            filter_by(**filters)

        results = self._filter_query(query, Task, limit, offset, last_id, yielded, desc)
        return results

    def get_gold_task_count_for_project(self, project_id):
        return (self.db.session.query(Task)
                .filter(Task.project_id == project_id)
                .filter(Task.calibration == 1)
                .count())

    def count_tasks_with(self, **filters):
        query_args, _, _, _  = self.generate_query_from_keywords(Task, **filters)
        return self.db.session.query(Task).filter(*query_args).count()

    def filter_tasks_by_user_favorites(self, uid, **filters):
        """Return tasks marked as favorited by user.id."""
        query = self.db.session.query(Task).filter(Task.fav_user_ids.any(uid))
        limit = filters.get('limit', 20)
        offset = filters.get('offset', 0)
        last_id = filters.get('last_id', None)
        desc = filters.get('desc', False)
        orderby = filters.get('orderby', 'id')
        if last_id:
            query = query.filter(Task.id > last_id)
        query = self._set_orderby_desc(query, Task, limit,
                                       last_id, offset,
                                       desc, orderby)
        return query.all()

    def get_task_favorited(self, uid, task_id):
        """Return task marked as favorited by user.id."""
        tasks = self.db.session.query(Task)\
                    .filter(Task.fav_user_ids.any(uid),
                            Task.id==task_id)\
                    .all()
        return tasks

    # Methods for queries on TaskRun objects
    def get_task_run(self, id):
        return self.db.session.query(TaskRun).get(id)

    def get_task_run_by(self, fulltextsearch=None, **attributes):
        filters, _, _, _  = self.generate_query_from_keywords(TaskRun,
                                                    fulltextsearch,
                                                    **attributes)
        return self.db.session.query(TaskRun).filter(*filters).first()

    def filter_task_runs_by(self, limit=None, offset=0, last_id=None,
                            yielded=False, fulltextsearch=None,
                            desc=False, **filters):
        return self._filter_by(TaskRun, limit, offset, yielded, last_id,
                              fulltextsearch, desc, **filters)

    def count_task_runs_with(self, **filters):
        query_args, _, _, _ = self.generate_query_from_keywords(TaskRun, **filters)
        return self.db.session.query(TaskRun).filter(*query_args).count()

    def get_user_has_task_run_for_project(self, project_id, user_id):
        return (self.db.session.query(TaskRun)
                .filter(TaskRun.user_id == user_id)
                .filter(TaskRun.project_id == project_id)
                .first()) is not None

    # Filter helpers
    def _filter_query(self, query, obj, limit, offset, last_id, yielded, desc):
        if last_id:
            query = query.filter(obj.id > last_id)
            query = query.order_by(obj.id).limit(limit)
        else:
            if desc:
                query = query.order_by(cast(obj.created, Date).desc())\
                        .limit(limit).offset(offset)
            else:
                query = query.order_by(obj.id).limit(limit).offset(offset)
        if yielded:
            limit = limit or 1
            return query.yield_per(limit)
        return query.all()


    # Methods for saving, deleting and updating both Task and TaskRun objects
    def save(self, element, clean_project=True):
        self._validate_can_be(self.SAVE_ACTION, element)
        try:
            # set task default expiration
            if element.__class__.__name__ == "Task":
                element.expiration = get_task_expiration(element.expiration, make_timestamp())
            self.db.session.add(element)
            self.db.session.commit()
            if clean_project:
                cached_projects.clean_project(element.project_id)
        except IntegrityError as e:
            self.db.session.rollback()
            raise DBIntegrityError(e)

    def update(self, element):
        self._validate_can_be(self.UPDATE_ACTION, element)
        try:
            self.db.session.merge(element)
            self.db.session.commit()
            cached_projects.clean_project(element.project_id)
        except IntegrityError as e:
            raise DBIntegrityError(e)

    def _delete(self, element):
        table = element.__class__
        inst = self.db.session.query(table).filter(table.id==element.id).first()
        self.db.session.delete(inst)

    def delete_taskrun(self, element):
        self._delete(element)
        self.db.session.commit()
        cached_projects.clean_project(element.project_id)

    def delete(self, element):
        # task repo is shared between task and taskun
        # call taskrun specific delete for taskrun deletes
        self._validate_can_be('deleted', element)
        if element.__tablename__ == "task_run":
            self.delete_taskrun(element)
            return

        tstart = time.perf_counter()
        self._validate_can_be('deleted', element)
        tend = time.perf_counter()
        time_validate = tend - tstart

        tstart = time.perf_counter()
        project_id, task_id = element.project_id, element.id
        tend = time.perf_counter()
        time_pid_tid = tend - tstart

        if current_app.config.get("SESSION_REPLICATION_ROLE_DISABLED"):
            # with session_replication_role disabled, follow regular path of data cleanup
            # from child tables via ON CASCADE DELETE configured on task table
            sql = text('''
                DELETE FROM task WHERE project_id=:project_id AND id=:task_id;
                ''')
        else:
            # expedite the deletion process that cleans up data from child tables
            # using set session_replication_role within db transaction. 'bulkdel'
            # when configured has session_replication_role set and its not required
            # to set it explicitly within db transaction
            sql_session_repl = ''
            if not 'bulkdel' in current_app.config.get('SQLALCHEMY_BINDS'):
                sql_session_repl = 'SET session_replication_role TO replica;'

            sql = text('''
                BEGIN;
                {}
                DELETE FROM result WHERE project_id=:project_id AND task_id=:task_id;
                DELETE FROM task_run WHERE project_id=:project_id AND task_id=:task_id;
                DELETE FROM task WHERE project_id=:project_id AND id=:task_id;
                COMMIT;
                '''.format(sql_session_repl))

        tstart = time.perf_counter()
        self.db.bulkdel_session.execute(sql, dict(project_id=project_id, task_id=task_id))
        tend = time.perf_counter()
        time_sql_exec = tend - tstart

        tstart = time.perf_counter()
        self.db.bulkdel_session.commit()
        tend = time.perf_counter()
        time_commit = tend - tstart

        tstart = time.perf_counter()
        cached_projects.clean_project(project_id)
        tend = time.perf_counter()
        time_clean_project = tend - tstart

        time_total = time_validate + time_pid_tid + time_sql_exec + time_commit + time_clean_project
        current_app.logger.info("Delete task profiling task %d, project %d Total time %.10f seconds. self._validate_can_be %.10f seconds, element.project_id task_id %.10f seconds, db.session.execute %.10f seconds, db.session.commit %.10f seconds, cached_projects.clean_project %.10f seconds",
                                task_id, project_id, time_total, time_validate, time_pid_tid, time_sql_exec, time_commit, time_clean_project)

    def delete_task_by_id(self, project_id, task_id):
        from pybossa.jobs import check_and_send_task_notifications

        args = dict(project_id=project_id, task_id=task_id)
        self.db.session.execute(text('''
                   DELETE FROM result WHERE project_id=:project_id
                                      AND task_id=:task_id;'''), args)
        self.db.session.execute(text('''
                   DELETE FROM task_run WHERE project_id=:project_id
                                        AND task_id=:task_id;'''), args)
        self.db.session.execute(text('''
                   DELETE FROM task WHERE project_id=:project_id
                                    AND id=:task_id;'''), args)
        self.db.session.commit()
        cached_projects.clean_project(project_id)
        check_and_send_task_notifications(project_id)

    def delete_valid_from_project(self, project, force_reset=False, filters=None):
        if not force_reset:
            """Delete only tasks that have no results associated."""
            params = {}
            sql = text('''
                DELETE FROM task WHERE task.project_id=:project_id
                AND task.id NOT IN
                (SELECT task_id FROM result
                WHERE result.project_id=:project_id GROUP BY result.task_id);
                ''')
        else:
            """force reset, remove all results."""
            filters = filters or {}
            conditions, params = get_task_filters(filters)

            # bulkdel db conn is with db user having session_replication_role
            # when bulkdel is not configured, make explict sql query to set
            # session replication role to replica
            sql_session_repl = ''
            if not ('bulkdel' in current_app.config.get('SQLALCHEMY_BINDS') or
                     current_app.config.get("SESSION_REPLICATION_ROLE_DISABLED")):
                sql_session_repl = 'SET session_replication_role TO replica;'
            sql = text('''
                BEGIN;

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
        self.db.bulkdel_session.execute(sql, dict(project_id=project.id, **params))
        self.db.bulkdel_session.commit()
        cached_projects.clean_project(project.id)
        self._delete_zip_files_from_store(project)

    def delete_taskruns_from_project(self, project):
        sql = text('''
                   DELETE FROM task_run WHERE project_id=:project_id;
                   UPDATE task SET state='ongoing', exported=false WHERE project_id=:project_id;
                   UPDATE task SET exported=true WHERE project_id=:project_id AND calibration=1
                   ''')
        self.db.session.execute(sql, dict(project_id=project.id))
        self.db.session.commit()
        cached_projects.clean_project(project.id)
        self._delete_zip_files_from_store(project)

    def get_tasks_by_filters(self, project, filters=None):
        filters = filters or {}
        conditions, params = get_task_filters(filters)

        sql = ''' SELECT task.id
                from task LEFT OUTER JOIN
                (SELECT task_id, CAST(COUNT(id) AS FLOAT) AS ct,
                MAX(finish_time) as ft FROM task_run
                WHERE project_id=:project_id GROUP BY task_id) AS log_counts
                ON task.id=log_counts.task_id
                WHERE task.project_id=:project_id {}
        '''.format(conditions)

        rows = self.db.session.execute(sql, dict(project_id=project.id, **params))
        return [row for row in rows]

    def update_tasks_redundancy(self, project, n_answers, filters=None):
        """
        Update the n_answer of every task from a project and their state.
        Use raw SQL for performance. Mark tasks as exported = False for
        tasks with curr redundancy < new redundancy, with state as completed
        and were marked as exported = True
        """
        from pybossa.jobs import check_and_send_task_notifications

        if n_answers < self.MIN_REDUNDANCY or n_answers > self.MAX_REDUNDANCY:
            raise ValueError("Invalid redundancy value: {}".format(n_answers))

        filters = filters or {}
        task_expiration = '{} day'.format(self.rdancy_upd_exp)
        conditions, params = get_task_filters(filters)
        tasks_not_updated = self._get_redundancy_update_msg(
            project, n_answers, conditions, params, task_expiration)

        self.update_task_exported_status(project.id, n_answers, conditions, params, task_expiration)
        sql = text('''
                   WITH all_tasks_with_orig_filter AS (
                        SELECT task.id as id,
                        coalesce(ct, 0) as n_task_runs, task.n_answers, ft,
                        priority_0, task.created
                        FROM task LEFT OUTER JOIN
                        (SELECT task_id, CAST(COUNT(id) AS FLOAT) AS ct,
                        MAX(finish_time) as ft FROM task_run
                        WHERE project_id=:project_id GROUP BY task_id) AS log_counts
                        ON task.id=log_counts.task_id
                        WHERE task.project_id=:project_id {}
                   ),

                   tasks_with_file_urls AS (
                        SELECT t.id as id FROM task t
                        WHERE t.id IN (SELECT id from all_tasks_with_orig_filter)
                        AND jsonb_typeof(t.info) = 'object'
                        AND EXISTS(SELECT TRUE FROM jsonb_object_keys(t.info) AS key
                        WHERE key ILIKE '%\_\_upload\_url%')
                   ),

                   tasks_excl_file_urls AS (
                        SELECT id FROM all_tasks_with_orig_filter
                        WHERE id NOT IN (SELECT id FROM tasks_with_file_urls)
                   )

                   UPDATE task SET n_answers=:n_answers,
                   state='ongoing' WHERE project_id=:project_id AND
                   ((id IN (SELECT id from tasks_excl_file_urls)) OR
                   (id IN (SELECT id from tasks_with_file_urls) AND state='ongoing'
                   AND TO_DATE(created, 'YYYY-MM-DD\THH24:MI:SS.US') >= NOW() - :task_expiration ::INTERVAL));'''
                   .format(conditions))
        self.db.session.execute(sql, dict(n_answers=n_answers,
                                          project_id=project.id,
                                          task_expiration=task_expiration,
                                          **params))
        self.update_task_state(project.id)
        self.db.session.commit()
        cached_projects.clean_project(project.id)
        check_and_send_task_notifications(project.id)
        return tasks_not_updated

    def update_task_state(self, project_id):
        # Create temp tables for completed tasks
        sql = text('''
                   CREATE TEMP TABLE complete_tasks ON COMMIT DROP AS (
                   SELECT task.id, array_agg(task_run.id) as task_runs
                   FROM task, task_run
                   WHERE task_run.task_id=task.id
                   AND task.project_id=:project_id
                   AND task.calibration!=1
                   GROUP BY task.id
                   having COUNT(task_run.id) >= task.n_answers);
                   ''')
        self.db.session.execute(sql, dict(project_id=project_id))
        # Set state to completed
        sql = text('''
                   UPDATE task SET state='completed'
                   FROM complete_tasks
                   WHERE complete_tasks.id=task.id;
                   ''')
        self.db.session.execute(sql)

        sql = text('''
                   INSERT INTO result
                   (created, project_id, task_id, task_run_ids, last_version) (
                   SELECT :ts, :project_id, completed_no_results.id,
                          completed_no_results.task_runs, true
                   FROM ( SELECT task.id as id,
                          array_agg(task_run.id) as task_runs
                          FROM task, task_run
                          WHERE task.state = 'completed'
                          AND task_run.task_id = task.id
                          AND NOT EXISTS (SELECT 1 FROM result
                                          WHERE result.task_id = task.id)
                          AND task.project_id=:project_id
                          GROUP BY task.id
                        ) as completed_no_results
                   );''')
        self.db.session.execute(sql, dict(project_id=project_id,
                                          ts=make_timestamp()))

    def update_priority(self, project_id, priority, filters):
        priority = min(1.0, priority)
        priority = max(0.0, priority)
        conditions, params = get_task_filters(filters)
        sql = text('''
                   WITH to_update AS (
                        SELECT task.id as id,
                        coalesce(ct, 0) as n_task_runs, task.n_answers, ft,
                        priority_0, task.created
                        FROM task LEFT OUTER JOIN
                        (SELECT task_id, CAST(COUNT(id) AS FLOAT) AS ct,
                        MAX(finish_time) as ft FROM task_run
                        WHERE project_id=:project_id GROUP BY task_id) AS log_counts
                        ON task.id=log_counts.task_id
                        WHERE task.project_id=:project_id {}
                   )
                   UPDATE task
                   SET priority_0=:priority
                   WHERE project_id=:project_id AND task.id in (
                        SELECT id FROM to_update);
                   '''.format(conditions))
        self.db.session.execute(sql, dict(priority=priority,
                                          project_id=project_id,
                                          **params))
        self.db.session.commit()
        cached_projects.clean_project(project_id)

    def find_duplicate(self, project_id, info, dup_checksum=None, completed_tasks=False):
        """
        Find a task id in the given project with the project info using md5
        index on info column casted as text. Md5 is used to avoid key size
        limitations in BTree indices
        """
        # with task payload containing dup_checksum value, perform duplicate
        # check based on checkum instead of comparing entire task payload info
        if dup_checksum:
            task_state_cond = "AND task.state='ongoing'" if not completed_tasks else ""
            sql = text('''
                    SELECT task.id as task_id
                    FROM task
                    WHERE task.project_id=:project_id
                    AND task.dup_checksum=:dup_checksum
                    AND task.expiration > (now() at time zone 'utc')::timestamp
                    {};'''.format(task_state_cond))
            row = self.db.session.execute(
                sql, dict(project_id=project_id, dup_checksum=dup_checksum)).first()
        else:
            sql = text('''
                    SELECT task.id as task_id
                    FROM task
                    WHERE task.project_id=:project_id
                    AND task.state='ongoing'
                    AND md5(task.info::text)=md5(((:info)::jsonb)::text);
                    ''')
            info = json.dumps(info, allow_nan=False)
            row = self.db.session.execute(
                sql, dict(info=info, project_id=project_id)).first()
        if row:
            return row[0]

    def _validate_can_be(self, action, element):
        from flask import current_app
        from pybossa.core import project_repo
        if not isinstance(element, Task) and not isinstance(element, TaskRun):
            name = element.__class__.__name__
            msg = '%s cannot be %s by %s' % (name, action, self.__class__.__name__)
            raise WrongObjectError(msg)

    def _delete_zip_files_from_store(self, project):
        from pybossa.core import json_exporter, csv_exporter
        global uploader
        if uploader is None:
            from pybossa.core import uploader
        json_tasks_filename = json_exporter.download_name(project, 'task')
        csv_tasks_filename = csv_exporter.download_name(project, 'task')
        json_taskruns_filename = json_exporter.download_name(project, 'task_run')
        csv_taskruns_filename = csv_exporter.download_name(project, 'task_run')
        container = "user_%s" % project.owner_id
        current_app.logger.info("delete_zip_files_from_store. project %d container %s. delete files %s, %s, %s, %s", project.id, container, json_tasks_filename, csv_tasks_filename, json_taskruns_filename, csv_taskruns_filename)
        uploader.delete_file(json_tasks_filename, container)
        uploader.delete_file(csv_tasks_filename, container)
        uploader.delete_file(json_taskruns_filename, container)
        uploader.delete_file(csv_taskruns_filename, container)

    def update_task_exported_status(self, project_id, n_answers, conditions, params, task_expiration):
        """
        Update exported=False for completed tasks that were exported
        and with new redundancy, they'll be marked as ongoing
        """
        sql = text('''
                   WITH all_tasks_with_orig_filter AS (
                        SELECT task.id as id,
                        coalesce(ct, 0) as n_task_runs, task.n_answers, ft,
                        priority_0, task.created
                        FROM task LEFT OUTER JOIN
                        (SELECT task_id, CAST(COUNT(id) AS FLOAT) AS ct,
                        MAX(finish_time) as ft FROM task_run
                        WHERE project_id=:project_id GROUP BY task_id) AS log_counts
                        ON task.id=log_counts.task_id
                        WHERE task.project_id=:project_id
                        AND task.state='completed'
                        AND task.n_answers < :n_answers {}
                   ),

                   tasks_with_file_urls AS (
                        SELECT t.id as id FROM task t
                        WHERE t.id IN (SELECT id from all_tasks_with_orig_filter)
                        AND jsonb_typeof(t.info) = 'object'
                        AND EXISTS(SELECT TRUE FROM jsonb_object_keys(t.info) AS key
                        WHERE key ILIKE '%\_\_upload\_url%')
                   ),

                   tasks_excl_file_urls AS (
                        SELECT id FROM all_tasks_with_orig_filter
                        WHERE id NOT IN (SELECT id FROM tasks_with_file_urls)
                   )

                   UPDATE task SET exported=False
                   WHERE project_id=:project_id AND
                   ((id IN (SELECT id from tasks_excl_file_urls)) OR
                   (id IN (SELECT id from tasks_with_file_urls) AND state='ongoing'
                   AND TO_DATE(created, 'YYYY-MM-DD\THH24:MI:SS.US') >= NOW() - :task_expiration ::INTERVAL));'''
                   .format(conditions))
        self.db.session.execute(sql, dict(n_answers=n_answers,
                                          project_id=project_id,
                                          task_expiration=task_expiration,
                                          **params))


    def _get_redundancy_update_msg(self, project, n_answers, conditions, params, task_expiration):
        sql = text('''
                   WITH all_tasks_with_orig_filter AS (
                        SELECT task.id as id,
                        coalesce(ct, 0) as n_task_runs, task.n_answers, ft,
                        priority_0, task.created
                        FROM task LEFT OUTER JOIN
                        (SELECT task_id, CAST(COUNT(id) AS FLOAT) AS ct,
                        MAX(finish_time) as ft FROM task_run
                        WHERE project_id=:project_id GROUP BY task_id) AS log_counts
                        ON task.id=log_counts.task_id
                        WHERE task.project_id=:project_id {}
                   )

                   SELECT t.id as id FROM task t
                   WHERE t.id IN (SELECT id from all_tasks_with_orig_filter)
                   AND jsonb_typeof(t.info) = 'object'
                   AND EXISTS(SELECT TRUE FROM jsonb_object_keys(t.info) AS key
                   WHERE key ILIKE '%\_\_upload\_url%')
                   AND (t.state = 'completed' OR TO_DATE(created, 'YYYY-MM-DD\THH24:MI:SS.US') < NOW() - :task_expiration ::INTERVAL)
                   AND n_answers != :n_answers;'''
                   .format(conditions))
        tasks = self.db.session.execute(sql,
            dict(project_id=project.id, n_answers=n_answers,
            task_expiration=task_expiration, **params)).fetchall()
        tasks_not_updated = '\n'.join([str(task.id) for task in tasks])
        return tasks_not_updated


    def bulk_update(self, project_id, payload):
        """
        use sqlalchemy case clause to update db rows in bulk
        construct payload in the form {task_id: priority} as
        sqlalchemy case works passing payload in the form
        WHEN task_id THEN priority
        https://stackoverflow.com/questions/54365873/sqlalchemy-update-multiple-rows-in-one-transaction
        """

        if not payload:
            return

        formatted_payload = {data["id"]: data["priority_0"] for data in payload}
        task_ids = formatted_payload.keys()
        tasks = self.db.session.query(Task).filter(Task.id.in_(task_ids))
        tasks.update({Task.priority_0: sqlalchemy_case(formatted_payload, value=Task.id)}, synchronize_session=False)
        self.db.session.commit()
        cached_projects.clean_project(project_id)


    def bulk_query(self, task_ids, return_only_task_id=False):
        """
        bulk query task based on the task id list
        """
        if return_only_task_id:
            tasks = self.db.session.query(Task).with_entities(Task.id).filter(Task.id.in_(task_ids)).all()
            tasks = [t[0] for t in tasks]
        else:
            tasks = self.db.session.query(Task).filter(Task.id.in_(task_ids)).all()
        return tasks
