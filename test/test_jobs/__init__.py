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

from datetime import datetime, timedelta
from pybossa.jobs import create_dict_jobs, enqueue_periodic_jobs,\
    get_quarterly_date, get_periodic_jobs, perform_completed_tasks_cleanup,\
    get_saturday_4pm_date
from unittest.mock import patch
from nose.tools import assert_raises
from test import with_context, Test
from test.factories import ProjectFactory, TaskFactory, TaskRunFactory
from accessdb import AccessDatabase
from sqlalchemy.sql import text


def jobs():
    """Generator."""
    yield dict(name='name', args=[], kwargs={}, timeout=10, queue='email')
    yield dict(name='name', args=[], kwargs={}, timeout=10, queue='low')
    yield dict(name='name', args=[], kwargs={}, timeout=10, queue='low')
    yield dict(name='name', args=[], kwargs={}, timeout=10, queue='high')
    yield dict(name='name', args=[], kwargs={}, timeout=10, queue='super')
    yield dict(name='name', args=[], kwargs={}, timeout=10, queue='medium')
    yield dict(name='name', args=[], kwargs={}, timeout=10, queue='monthly')
    yield dict(name='name', args=[], kwargs={}, timeout=10, queue='quaterly')
    yield dict(name='name', args=[], kwargs={}, timeout=10, queue='weekly')


class TestJobs(Test):


    @with_context
    def test_create_dict_jobs(self):
        """Test JOB create_dict_jobs works."""
        data = [{'id': 1, 'short_name': 'app'}]
        timeout = self.flask_app.config.get('TIMEOUT')
        jobs_gen = create_dict_jobs(data, 'function', timeout)
        jobs = []
        for j in jobs_gen:
            jobs.append(j)
        assert len(jobs) == 1
        assert jobs[0]['name'] == 'function', jobs[0]
        assert jobs[0]['timeout'] == timeout, jobs[0]

    @with_context
    def test_get_default_jobs(self):
        """Test JOB get_default_jobs works."""
        from pybossa.jobs import warm_up_stats, warn_old_project_owners
        from pybossa.jobs import warm_cache, news, get_default_jobs
        from pybossa.jobs import disable_users_job, send_email_notifications
        timeout = self.flask_app.config.get('TIMEOUT')
        job_names = [warm_up_stats, warn_old_project_owners, warm_cache, news,
                     disable_users_job, send_email_notifications]
        for job in get_default_jobs():
            if job['name'] == warm_cache:
                assert job['timeout'] == 2*timeout, job
            else:
                assert job['timeout'] == timeout, job
            assert job['name'] in job_names, job

    @with_context
    @patch('pybossa.jobs.get_periodic_jobs')
    def test_enqueue_periodic_jobs(self, get_periodic_jobs):
        """Test JOB enqueue_periodic_jobs works."""
        get_periodic_jobs.return_value = jobs()
        queue_name = 'low'
        res = enqueue_periodic_jobs(queue_name)
        expected_jobs = [job for job in jobs() if job['queue'] == queue_name]
        msg = "%s jobs in %s have been enqueued" % (len(expected_jobs), queue_name)
        assert res == msg, res

    @with_context
    @patch('pybossa.jobs.get_periodic_jobs')
    def test_enqueue_periodic_jobs_bad_queue_name(self, mock_get_periodic_jobs):
        """Test JOB enqueue_periodic_jobs diff queue name works."""
        mock_get_periodic_jobs.return_value = jobs()
        queue_name = 'badqueue'
        res = enqueue_periodic_jobs(queue_name)
        msg = "%s jobs in %s have been enqueued" % (0, queue_name)
        assert res == msg, res

    @with_context
    @patch('pybossa.jobs.get_periodic_jobs')
    def test_enqueue_periodic_weekly_job(self, mock_get_periodic_jobs):
        """Test JOB enqueue_periodic_jobs for queue name 'weekly' works."""
        mock_get_periodic_jobs.return_value = jobs()
        queue_name = "weekly"
        res = enqueue_periodic_jobs(queue_name)
        msg = "%s jobs in %s have been enqueued" % (1, queue_name)
        assert res == msg, res

    @with_context
    @patch('pybossa.jobs.get_export_task_jobs')
    @patch('pybossa.jobs.get_project_jobs')
    @patch('pybossa.jobs.get_autoimport_jobs')
    @patch('pybossa.jobs.get_inactive_users_jobs')
    @patch('pybossa.jobs.get_non_contributors_users_jobs')
    def test_get_periodic_jobs_with_low_queue(self, non_contr, inactive,
            autoimport, project, export):
        export.return_value = jobs()
        autoimport.return_value = jobs()
        low_jobs = get_periodic_jobs('low')
        # Only returns jobs for the specified queue
        for job in low_jobs:
            assert job['queue'] == 'low'
        # Does not call unnecessary functions for performance
        assert non_contr.called == False
        assert inactive.called == False
        assert project.called == False

    @with_context
    @patch('pybossa.jobs.get_export_task_jobs')
    @patch('pybossa.jobs.get_project_jobs')
    @patch('pybossa.jobs.get_autoimport_jobs')
    @patch('pybossa.jobs.get_inactive_users_jobs')
    @patch('pybossa.jobs.get_non_contributors_users_jobs')
    def test_get_periodic_jobs_with_high_queue(self, non_contr, inactive,
            autoimport, project, export):
        export.return_value = jobs()
        high_jobs = get_periodic_jobs('high')
        # Only returns jobs for the specified queue
        for job in high_jobs:
            assert job['queue'] == 'high'
        # Does not call unnecessary functions for performance
        assert non_contr.called == False
        assert inactive.called == False
        assert project.called == True
        assert autoimport.called == False

    @with_context
    @patch('pybossa.jobs.get_export_task_jobs')
    @patch('pybossa.jobs.get_project_jobs')
    @patch('pybossa.jobs.get_autoimport_jobs')
    @patch('pybossa.jobs.get_inactive_users_jobs')
    @patch('pybossa.jobs.get_non_contributors_users_jobs')
    def test_get_periodic_jobs_with_super_queue(self, non_contr, inactive,
            autoimport, project, export):
        project.return_value = jobs()
        super_jobs = get_periodic_jobs('super')
        # Only returns jobs for the specified queue
        for job in super_jobs:
            assert job['queue'] == 'super'
        # Does not call unnecessary functions for performance
        assert non_contr.called == False
        assert inactive.called == False
        assert export.called == False
        assert autoimport.called == False

    @with_context
    @patch('pybossa.jobs.get_export_task_jobs')
    @patch('pybossa.jobs.get_project_jobs')
    @patch('pybossa.jobs.get_autoimport_jobs')
    @patch('pybossa.jobs.get_inactive_users_jobs')
    @patch('pybossa.jobs.get_non_contributors_users_jobs')
    def test_get_periodic_jobs_with_quaterly_queue(self, non_contr, inactive,
            autoimport, project, export):
        inactive.return_value = jobs()
        non_contr.return_value = jobs()
        quaterly_jobs = get_periodic_jobs('quaterly')
        # Only returns jobs for the specified queue
        for job in quaterly_jobs:
            assert job['queue'] == 'quaterly'
        # Does not call unnecessary functions for performance
        assert autoimport.called == False
        assert export.called == False
        assert project.called == False

    @with_context
    def test_get_quarterly_date_1st_quarter_returns_31_march(self):
        january_1st = datetime(2015, 1, 1)
        february_2nd = datetime(2015, 2, 2)
        march_31st = datetime(2015, 3, 31)

        assert get_quarterly_date(january_1st) == datetime(2015, 3, 31)
        assert get_quarterly_date(february_2nd) == datetime(2015, 3, 31)
        assert get_quarterly_date(march_31st) == datetime(2015, 3, 31)

    @with_context
    def test_get_quarterly_date_2nd_quarter_returns_30_june(self):
        april_1st = datetime(2015, 4, 1)
        may_5th = datetime(2015, 5, 5)
        june_30th = datetime(2015, 4, 10)

        assert get_quarterly_date(april_1st) == datetime(2015, 6, 30)
        assert get_quarterly_date(may_5th) == datetime(2015, 6, 30)
        assert get_quarterly_date(june_30th) == datetime(2015, 6, 30)

    @with_context
    def test_get_quarterly_date_3rd_quarter_returns_30_september(self):
        july_1st = datetime(2015, 7, 1)
        august_6th = datetime(2015, 8, 6)
        september_30th = datetime(2015, 9, 30)

        assert get_quarterly_date(july_1st) == datetime(2015, 9, 30)
        assert get_quarterly_date(august_6th) == datetime(2015, 9, 30)
        assert get_quarterly_date(september_30th) == datetime(2015, 9, 30)

    @with_context
    def test_get_quarterly_date_4th_quarter_returns_31_december(self):
        october_1st = datetime(2015, 10, 1)
        november_24th = datetime(2015, 11,24)
        december_31st = datetime(2015, 12, 31)

        assert get_quarterly_date(october_1st) == datetime(2015, 12, 31)
        assert get_quarterly_date(november_24th) == datetime(2015, 12, 31)
        assert get_quarterly_date(december_31st) == datetime(2015, 12, 31)

    @with_context
    def test_get_quarterly_date_returns_same_time_as_passed(self):
        now = datetime.utcnow()

        returned_date = get_quarterly_date(now)

        assert now.time() == returned_date.time()

    @with_context
    def test_get_quarterly_date_raises_TypeError_on_wrong_args(self):
        assert_raises(TypeError, get_quarterly_date, 'wrong_arg')

    @with_context
    @patch('pybossa.jobs.get_export_task_jobs')
    @patch('pybossa.jobs.get_project_jobs')
    @patch('pybossa.jobs.get_autoimport_jobs')
    @patch('pybossa.jobs.get_inactive_users_jobs')
    @patch('pybossa.jobs.get_non_contributors_users_jobs')
    def test_completed_tasks_cleanup_scheduled_with_weekly_queue(self, non_contr, inactive,
            autoimport, project, export):
        """Test completed_tasks_cleanup gets scheduled."""
        inactive.return_value = jobs()
        non_contr.return_value = jobs()

        project = ProjectFactory.create(info=dict(completed_tasks_cleanup_days=30))
        weekly_jobs = get_periodic_jobs("weekly")
        # Only returns jobs for the specified queue
        for job in weekly_jobs:
            assert job["name"].__name__ == "perform_completed_tasks_cleanup", "completed tasks cleanup job should be scheduled"
            assert job['queue'] == "weekly"

    @with_context
    @patch('pybossa.jobs.purge_task_data')
    def test_completed_tasks_cleanup(self, mock_purge_tasks):
        """Test completed_tasks_cleanup deletes tasks qualify for deletion."""

        cleanup_days = 30
        project = ProjectFactory.create(info=dict(completed_tasks_cleanup_days=cleanup_days))

        # task creation dates. generate sample tasks
        # 2 tasks completed are with creation date more than 30 days from current date
        # 1 task completed and is with current creation date
        now = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S')
        created = (datetime.utcnow() - timedelta(60)).strftime('%Y-%m-%dT%H:%M:%S')
        past_30days = (datetime.utcnow() - timedelta(30)).strftime('%Y-%m-%dT%H:%M:%S')

        task1 = TaskFactory.create(project=project, created=past_30days, n_answers=2, state="completed")
        task2 = TaskFactory.create(project=project, created=now, n_answers=4, state="completed")
        task3 = TaskFactory.create(project=project, created=past_30days, n_answers=3, state="completed")

        TaskRunFactory.create_batch(2, project=project, created=created, finish_time=now, task=task1)
        TaskRunFactory.create_batch(4, project=project, created=created, finish_time=now, task=task2)
        TaskRunFactory.create_batch(3, project=project, created=created, finish_time=now, task=task3)

        task1_id, task2_id, task3_id = task1.id, task2.id, task3.id
        project_id = project.id
        perform_completed_tasks_cleanup()
        assert mock_purge_tasks.call_count == 2
        # task 1 and task 3 would be cleaned up as they are completed
        # and 30 days old hence qualifying for deletion.
        # task 2 though complete is less than 30 days old, hence not
        # get called for deletion
        expected_calls_params = [(task3_id, project.id), (task1_id, project.id)]
        actual_calls_params = []
        for call in mock_purge_tasks.call_args_list:
            assert call[0] in expected_calls_params
            actual_calls_params.append(call[0])
        assert (task2_id, project_id) not in actual_calls_params, "Task id 2 should not be purged"

    @with_context
    def test_saturday_4pm_date(self):
        """Test date generated is saturday 4 pm date from a given date."""
        date1 = datetime.strptime("2022-10-12 10:00PM", "%Y-%m-%d %I:%M%p")
        saturday = get_saturday_4pm_date(date1)
        assert saturday.strftime("%Y-%m-%d %H:%M:%S") == "2022-10-15 16:00:00"
        # test with some other date
        date2 = datetime.strptime("2026-01-31 10:00AM", "%Y-%m-%d %I:%M%p")
        saturday = get_saturday_4pm_date(date2)
        assert saturday.strftime("%Y-%m-%d %H:%M:%S") == "2026-01-31 16:00:00"

    @with_context
    @patch('pybossa.jobs.purge_task_data')
    def test_completed_tasks_cleanup_bad_config(self, mock_purge_tasks):
        """Test completed_tasks_cleanup deletes tasks qualify for deletion."""

        from flask import current_app
        current_app.config['COMPLETED_TASK_CLEANUP_DAYS'] = [(None, None)]
        perform_completed_tasks_cleanup()
        assert not mock_purge_tasks.called

    @with_context
    @patch('pybossa.jobs.purge_task_data')
    def test_completed_tasks_cleanup_bad_project_config(self, mock_purge_tasks):
        """Test completed_tasks_cleanup deletes tasks qualify for deletion."""

        from flask import current_app
        current_app.config['COMPLETED_TASK_CLEANUP_DAYS'] = [(30, "30 days"), (60, "60 days")]
        ProjectFactory.create(info=dict(completed_tasks_cleanup_days=240))
        ProjectFactory.create(info=dict(completed_tasks_cleanup_days="xyz"))
        perform_completed_tasks_cleanup()
        assert not mock_purge_tasks.called

    # TODO: uncomment after tests database can be upgraded similar to pybossa database
    # this test performs end to end testing archiving data to tables and cleaning up
    # archive tables from test db upon testing complete for future test runs to be successful
    # mock_purge_tasks can be removed with task data cleanup and archive happening in actual
    # @with_context
    # @patch('pybossa.jobs.purge_task_data')
    # def test_completed_tasks_cleanup(self, mock_purge_tasks):
    #     """Test completed_tasks_cleanup deletes tasks qualify for deletion."""

    #     cleanup_days = 30
    #     project = ProjectFactory.create(info=dict(completed_tasks_cleanup_days=cleanup_days))

    #     # task creation dates. generate sample tasks
    #     # 2 tasks completed are with creation date more than 30 days from current date
    #     # 1 task completed and is with current creation date
    #     now = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S')
    #     created = (datetime.utcnow() - timedelta(60)).strftime('%Y-%m-%dT%H:%M:%S')
    #     past_30days = (datetime.utcnow() - timedelta(30)).strftime('%Y-%m-%dT%H:%M:%S')

    #     task1 = TaskFactory.create(project=project, created=past_30days, n_answers=2, state="completed")
    #     task2 = TaskFactory.create(project=project, created=now, n_answers=4, state="completed")
    #     task3 = TaskFactory.create(project=project, created=past_30days, n_answers=3, state="completed")

    #     TaskRunFactory.create_batch(2, project=project, created=created, finish_time=now, task=task1)
    #     TaskRunFactory.create_batch(4, project=project, created=created, finish_time=now, task=task2)
    #     TaskRunFactory.create_batch(3, project=project, created=created, finish_time=now, task=task3)

    #     task1_id, task2_id, task3_id = task1.id, task2.id, task3.id
    #     project_id = project.id
    #     perform_completed_tasks_cleanup()
    #     assert mock_purge_tasks.call_count == 2
    #     # task 1 and task 3 would be cleaned up as they are completed
    #     # and 30 days old hence qualifying for deletion.
    #     # task 2 though complete is less than 30 days old, hence not
    #     # get called for deletion
    #     expected_calls_params = [(task3_id, project.id), (task1_id, project.id)]
    #     actual_calls_params = []
    #     for call in mock_purge_tasks.call_args_list:
    #         assert call[0] in expected_calls_params
    #         actual_calls_params.append(call[0])
    #     assert (task2_id, project_id) not in actual_calls_params, "Task id 2 should not be purged"

        # To test actual task cleanup against database, make sure to have
        # archived tables created in you local test database.
        # Uncommment following code before running tests locally
        # in order to perform end to end testing against test database.
        # with AccessDatabase() as db:
        #     # confirm expected task data cleaned up from task table
        #     # sql = f"SELECT count(*) FROM task WHERE id IN({task1.id}, {task2.id}, {task3.id});"
        #     sql = f"SELECT count(*) FROM task WHERE id IN({task1_id}, {task2_id}, {task3_id});"
        #     db.execute_sql(sql)
        #     available_task_count = db.cursor.fetchone()[0]
        #     print("Available tasks after completed tasks cleanup", available_task_count)
        #     assert available_task_count == 1, available_task_count

        #     # confirm expected task run data cleaned up from task_run table
        #     sql = f"SELECT count(*) FROM task_run WHERE task_id IN({task1_id}, {task2_id}, {task3_id});"
        #     db.execute_sql(sql)
        #     available_task_run_count = db.cursor.fetchone()[0]
        #     assert available_task_run_count == 4, "With task1 & task3 deleted, only task2 taskruns that are less than 30 days old should be available"

        #     # confirm expected task result data cleaned up from task table
        #     sql = f"SELECT count(*) FROM result WHERE task_id IN({task1_id}, {task2_id}, {task3_id});"
        #     db.execute_sql(sql)
        #     available_result_count = db.cursor.fetchone()[0]
        #     assert available_result_count == 1, "With task1 & task3 deleted, only task2 results that are less than 30 days old should be available"

        #     # 2 tasks expected to be archived; task1 and task3 that are 30 days old tasks
        #     sql = f"SELECT count(*) FROM task_archived WHERE project_id = {project_id};"
        #     db.execute_sql(sql)
        #     archived_tasks_count = db.cursor.fetchone()[0]
        #     assert archived_tasks_count == 2, "Two completed tasks that are 30 days old should be archived"

        #     # 5 task runs expected to be archived. 2 from taskid 1 and 3 from taskid 3 that are 30 days old tasks
        #     sql = f"SELECT count(*) FROM task_run_archived WHERE project_id = {project_id};"
        #     db.execute_sql(sql)
        #     archived_task_runs_count = db.cursor.fetchone()[0]
        #     assert archived_task_runs_count == 5, "Two completed tasks that are 30 days old should be archived"

        #     # 2 results expected to be archived. 1 for taskid 1 and 1 for taskid 3 that are 30 days old tasks
        #     sql = f"SELECT count(*) FROM result_archived WHERE project_id = {project_id};"
        #     db.execute_sql(sql)
        #     archived_results_count = db.cursor.fetchone()[0]
        #     assert archived_results_count == 2, "Two completed tasks that are 30 days old should be archived"

        # # perform archived records cleanup upon tests complete
        # with AccessDatabase() as db:
        #     sql = f"DELETE FROM task_archived WHERE id IN({task1_id}, {task2_id}, {task3_id});"
        #     db.execute_sql(sql)
        #     db.conn.commit()
        #     sql = f"DELETE FROM task_run_archived WHERE task_id IN({task1_id}, {task2_id}, {task3_id});"
        #     db.execute_sql(sql)
        #     db.conn.commit()
        #     sql = f"DELETE FROM result_archived WHERE task_id IN({task1_id}, {task2_id}, {task3_id});"
        #     db.execute_sql(sql)
        #     db.conn.commit()