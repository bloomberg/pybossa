import json

from test import db, with_context
from test.factories import ProjectFactory, UserFactory, TaskRunFactory, PerformanceStatsFactory
from test.helper import web
from pybossa.repositories import ProjectRepository, UserRepository, PerformanceStatsRepository

project_repo = ProjectRepository(db)
user_repo = UserRepository(db)
perf_repo = PerformanceStatsRepository(db)


class TestPerfStats(web.Helper):

    @with_context
    def test_owner_has_access(self):
        project = ProjectFactory.create(published=True)
        url = '/project/%s/performancestats?api_key=%s' % (project.short_name, project.owner.api_key)
        res = self.app.get(url)
        assert 'Performance Statistics' in str(res.data), res.data

    @with_context
    def test_not_owner_has_access_to_own_stats(self):
        owner, user = UserFactory.create_batch(2)
        project = ProjectFactory.create(owner=owner, published=True)
        TaskRunFactory.create(user=owner, project=project)
        TaskRunFactory.create(user=user, project=project)
        url = '/project/%s/performancestats?api_key=%s' % (project.short_name, user.api_key)
        res = self.app_get_json(url)
        data = json.loads(res.data)
        assert len(data['contributors']) == 1
        assert str(user.id) in data['contributors']

    @with_context
    def test_has_fields_config(self):
        fields = {'hello': {}}
        project = ProjectFactory.create(published=True, info={'answer_fields': fields})
        url = '/project/%s/performancestats?api_key=%s' % (project.short_name, project.owner.api_key)
        res = self.app_get_json(url)

        data = json.loads(res.data)
        assert data['answer_fields'] == fields, data

    @with_context
    def test_has_users(self):
        users = UserFactory.create_batch(3)
        owner = users[0]
        project = ProjectFactory.create(published=True)
        TaskRunFactory.create(user=users[1], project=project)

        url = '/project/%s/performancestats?api_key=%s' % (project.short_name, owner.api_key)
        res = self.app_get_json(url)

        data = json.loads(res.data)
        data['contributors'] == [], data['contributors']

    @with_context
    def test_delete_stats(self):
        project = ProjectFactory.create()
        user = UserFactory.create()
        stat = PerformanceStatsFactory.create(
            project_id = project.id,
            user_id = user.id
        )
        url = '/project/%s/performancestats?api_key=%s' % (project.short_name, project.owner.api_key)
        res = self.app_get_json(url)
        data = json.loads(res.data)
        csrf = data['csrf']

        url = '/project/%s/performancestats?api_key=%s&field=%s&user_id=%s' % (
            project.short_name, project.owner.api_key, stat.field,
            stat.user_id)
        res = self.app.delete(url, content_type='application/json',
                              data=json.dumps({'answer_fields': {}}),
                              headers={'X-CSRFToken': csrf})
        assert res.status_code == 204
        stats = perf_repo.filter_by()
        assert not stats
