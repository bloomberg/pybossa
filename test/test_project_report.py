from test.helper import web
from test import db, with_context
from test.factories import ProjectFactory, UserFactory, TaskFactory, TaskRunFactory
from pybossa.repositories import ProjectRepository
from pybossa import exporter
from pybossa.exporter.csv_reports_export import ProjectReportCsvExporter
from unittest.mock import patch, MagicMock
from nose.tools import assert_raises
from pybossa.cache.projects import get_project_report_projectdata
from pybossa.core import user_repo, uploader

project_repo = ProjectRepository(db)


class TestProjectReport(web.Helper):

    @with_context
    def test_nonadmin_noncoowner_access_project_report_results_403(self):
        """Test nonadmin noncoowner accessing project report returns 403"""
        self.register()
        user = user_repo.get(1)
        project = ProjectFactory.create(owner=user)
        self.signout()
        self.register(fullname='Juan', name='juan', password='juana')
        self.signin(email="juan@example.com", password='juana')
        url = '/project/%s/projectreport/export' % project.short_name
        res = self.app.get(url, follow_redirects=True)
        assert res.status_code == 403, res.data

    @with_context
    def test_admin_owner_can_access_project_report(self):
        """Test admin can access project report"""
        self.register()
        user = user_repo.get(1)
        project = ProjectFactory.create(owner=user)
        url = '/project/%s/projectreport/export' % project.short_name
        res = self.app.get(url, follow_redirects=True)
        assert res.status_code == 200, res.data

    @with_context
    def test_admin_owner_can_access_project_report_with_params(self):
        """Test project report works when accessed with correct params"""
        self.register()
        self.signin()
        user = user_repo.get(1)
        project = ProjectFactory.create(owner=user)
        url = '/project/%s/projectreport/export?type=project&format=csv' % project.short_name
        res = self.app.get(url, follow_redirects=True)
        assert res.status_code == 200, res.data

    @with_context
    def test_project_report_with_task_details(self):
        """Test project report works with project details"""
        admin = UserFactory.create(admin=True)
        admin.set_password('1234')
        user_repo.save(admin)

        owner = UserFactory.create(pro=False)
        project = ProjectFactory.create(owner=owner)
        task = TaskFactory.create(project=project)
        TaskRunFactory.create(task=task)
        url = '/project/%s/projectreport/export?type=project&format=csv' % project.short_name
        res = self.app_get_json(url, follow_redirects=True)
        assert res.status_code == 200, res.data

    @with_context
    @patch.object(exporter.os, 'remove')
    def test_project_report_cleanup_on_error(self, mock_os_remove):
        self.register()
        self.signin()
        user = user_repo.get(1)
        project = ProjectFactory.create(owner=user)
        prce = ProjectReportCsvExporter()
        with patch.object(prce, '_zip_factory', side_effect=Exception('a')):
            with assert_raises(Exception):
                prce._make_zip(project, None)
        assert mock_os_remove.called

    @with_context
    def test_project_report_date_range_data(self):
        created = "2019-10-11T10:00:00"
        date_now = "2019-12-11T10:00:00"
        two_days_ago = "2019-12-09T10:00:00"
        four_days_ago = "2019-12-07T10:00:00"
        six_days_ago  = "2019-12-05T10:00:00"

        exp_avg_time = 83808 # 58 days 04:48:00
        exp_first_task_submission = "2019-12-07T10:00:00"
        exp_last_task_submission = "2019-12-09T10:00:00"

        proj = ProjectFactory.create()
        task = TaskFactory.create(project=proj)
        TaskRunFactory.create_batch(2, project=proj, created=created, finish_time=six_days_ago, task=task)
        TaskRunFactory.create_batch(4, project=proj, created=created, finish_time=four_days_ago, task=task)
        TaskRunFactory.create_batch(6, project=proj, created=created, finish_time=two_days_ago, task=task)
        TaskRunFactory.create_batch(2, project=proj, created=created, finish_time=date_now, task=task)

        report_data = get_project_report_projectdata(proj.id, start_date=four_days_ago, end_date=two_days_ago)
        assert report_data[4] == exp_first_task_submission and report_data[5] == exp_last_task_submission
        assert report_data[6] == exp_avg_time

    @with_context
    def test_project_report_renders_date_range_form(self):
        """Test project report renders generate project report form to submit start end date"""
        self.register()
        self.signin()
        user = user_repo.get(1)
        project = ProjectFactory.create(owner=user)
        url = '/project/%s/projectreport/export' % project.short_name
        res = self.app.get(url)
        assert "Generate project report" in str(res.data), res.data
        assert "Start date" in str(res.data), res.data
        assert "End date" in str(res.data), res.data

    @with_context
    @patch('pybossa.exporter.uploader.file_exists', return_value=True)
    @patch.object(exporter.os, 'remove')
    def test_project_report_delete_existing_report(self, mock_os_remove, mock_file_exists):
        """Test project report is generated with deleting existing report zip"""
        self.register()
        self.signin()
        user = user_repo.get(1)
        project = ProjectFactory.create(owner=user)
        url = '/project/%s/projectreport/export' % project.short_name

        res = self.app.post(url)
        assert mock_os_remove.called
