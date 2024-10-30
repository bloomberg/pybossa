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
from test import Test, with_context, flask_app
from test.factories import ProjectFactory, UserFactory, TaskFactory, TaskRunFactory
from pybossa.jobs import get_export_task_jobs, project_export, export_tasks, export_all_users
from pybossa.exporter.export_helpers import filter_table_headers
from unittest.mock import patch
from nose.tools import assert_raises

class TestExport(Test):

    @with_context
    @patch.dict(flask_app.config, {'PRO_FEATURES': {'updated_exports': True}})
    def test_get_export_task_jobs(self):
        """Test JOB export task jobs works."""
        project = ProjectFactory.create()
        jobs_generator = get_export_task_jobs(queue='low')
        jobs = []
        for job in jobs_generator:
            jobs.append(job)

        msg = "There should be only one job."
        assert len(jobs) == 1, len(jobs)
        job = jobs[0]
        msg = "The job should be for the same project.id"
        assert job['args'] == [project.id], msg
        msg = "The job should be enqueued in low priority."
        assert job['queue'] == 'low', msg

    @with_context
    @patch.dict(flask_app.config, {'PRO_FEATURES': {'updated_exports': True}})
    def test_get_export_task_pro_jobs(self):
        """Test JOB export task jobs for pro users works."""
        user = UserFactory.create(pro=True)
        project = ProjectFactory.create(owner=user)
        jobs_generator = get_export_task_jobs(queue='high')
        jobs = []
        for job in jobs_generator:
            jobs.append(job)

        msg = "There should be only one job."
        assert len(jobs) == 1, len(jobs)
        job = jobs[0]
        msg = "The job should be for the same project.id"
        assert job['args'] == [project.id], msg
        msg = "The job should be enqueued in high priority."
        assert job['queue'] == 'high', msg

    @with_context
    @patch.dict(flask_app.config, {'PRO_FEATURES': {'updated_exports': False}})
    def test_get_export_task_jobs_pro_disabled_high_queue(self):
        """Test JOB export task jobs returns non pro projects for high queue if
        updated exports is enabled for everyone."""
        user = UserFactory.create()
        project = ProjectFactory.create(owner=user)
        jobs_generator = get_export_task_jobs(queue='high')
        jobs = []
        for job in jobs_generator:
            jobs.append(job)

        msg = "There should be only one job."
        assert len(jobs) == 1, len(jobs)
        job = jobs[0]
        msg = "The job should be for the same project.id"
        assert job['args'] == [project.id], msg
        msg = "The job should be enqueued in high priority."
        assert job['queue'] == 'high', msg

    @with_context
    @patch('pybossa.core.json_exporter')
    @patch('pybossa.core.csv_exporter')
    def test_project_export(self, csv_exporter, json_exporter):
        """Test JOB project_export works."""
        project = ProjectFactory.create()
        project_export(project.id)
        csv_exporter.pregenerate_zip_files.assert_called_once_with(project)
        json_exporter.pregenerate_zip_files.assert_called_once_with(project)

    @with_context
    @patch('pybossa.core.json_exporter')
    @patch('pybossa.core.csv_exporter')
    def test_project_export_none(self, csv_exporter, json_exporter):
        """Test JOB project_export without project works."""
        project_export(0)
        assert not csv_exporter.pregenerate_zip_files.called
        assert not json_exporter.pregenerate_zip_files.called

    @with_context
    @patch('pybossa.core.mail')
    @patch('pybossa.core.task_csv_exporter')
    @patch('pybossa.core.task_json_exporter')
    def test_export_tasks(self, task_json_exporter, task_csv_exporter, mail):
        """Test JOB export_tasks works."""
        user = UserFactory.create(admin=True)
        project = ProjectFactory.create(name='test_project')
        task = TaskFactory.create(project=project)
        task_run = TaskRunFactory.create(project=project, task=task)

        export_tasks(user.email_addr, project.short_name, 'task', False, 'csv')
        export_tasks(user.email_addr, project.short_name, 'task', False, 'json')

        task_csv_exporter.make_zip.assert_called_once_with(project, 'task', False, None, False)
        task_json_exporter.make_zip.assert_called_once_with(project, 'task', False, None, False)

    @with_context
    @patch('pybossa.core.task_csv_exporter')
    def test_response_zip(self, task_csv_exporter):
        """Test response_zip"""
        project = ProjectFactory.create(name='test_project')
        ty = "task"
        task_csv_exporter.response_zip(project, ty)
        task_csv_exporter.response_zip.assert_called()

    @with_context
    def test_export_all_users_exception(self):
        """Test export_all_users exception handled."""
        with assert_raises(KeyError) as exec:
            export_all_users(None, 'test@test.com')

    @with_context
    def test_filter_table_headers(self):
        """Test filter_table_headers filters task__info fields"""
        input_headers = ['task__calibration', 'task__created', 'task__exported', 'task__id', 'task__info', 'task__info__batch_id', 'task__info__class', 'task__info__document_type', 'task__info__notes', 'task__n_answers', 'task__priority_0', 'task__project_id', 'task__quorum', 'task__state', 'task__user_pref']

        # only task__info__batch_id and task__info__document_type should be present in output headers
        accepted_task_info_fields = ['batch_id', 'document_type']
        output_headers = filter_table_headers(input_headers, accepted_task_info_fields)
        assert len(output_headers) == 12

        # no task info fields should be present in output headers
        accepted_task_info_fields = []
        output_headers = filter_table_headers(input_headers, accepted_task_info_fields)
        assert len(output_headers) == 10
