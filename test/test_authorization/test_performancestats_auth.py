import importlib.util
import pathlib
import sys
import types
import unittest
from types import SimpleNamespace


class ProjectAuth(object):

    def can(self, user, action, project):
        return user.admin or \
            (user.subadmin and user.id in project.owners_ids) or \
            user.id in project.info.get('project_users', [])


package_name = '_performancestats_auth_test'
package = types.ModuleType(package_name)
package.__path__ = []
project_module = types.ModuleType(package_name + '.project')
project_module.ProjectAuth = ProjectAuth
sys.modules[package_name] = package
sys.modules[package_name + '.project'] = project_module

module_path = pathlib.Path(__file__).resolve().parents[2] / \
    'pybossa/auth/performancestats.py'
spec = importlib.util.spec_from_file_location(
    package_name + '.performancestats', module_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
PerformanceStatsAuth = module.PerformanceStatsAuth


class ProjectRepository(object):

    def __init__(self, project):
        self.project = project

    def get(self, project_id):
        if project_id == self.project.id:
            return self.project


class TestPerformanceStatsAuth(unittest.TestCase):

    def setUp(self):
        self.project = SimpleNamespace(
            id=10,
            published=True,
            owners_ids=[3],
            info={'project_users': [2]},
            get_project_users=lambda: [2],
            needs_password=lambda: True)
        self.stat = SimpleNamespace(project_id=10, user_id=4)
        self.auth = PerformanceStatsAuth(ProjectRepository(self.project))

    @staticmethod
    def user(user_id, admin=False, subadmin=False, authenticated=True):
        return SimpleNamespace(
            id=user_id,
            admin=admin,
            subadmin=subadmin,
            is_authenticated=authenticated)

    def test_project_participant_cannot_read_another_users_stats(self):
        participant = self.user(2)

        self.assertFalse(self.auth.can(participant, 'read', self.stat))

    def test_stat_subject_can_read_own_stats(self):
        self.assertTrue(self.auth.can(self.user(4), 'read', self.stat))

    def test_admin_can_read_any_users_stats(self):
        self.assertTrue(self.auth.can(
            self.user(1, admin=True), 'read', self.stat))

    def test_subadmin_project_owner_can_read_any_users_stats(self):
        self.assertTrue(self.auth.can(
            self.user(3, subadmin=True), 'read', self.stat))

    def test_non_owner_subadmin_cannot_read_another_users_stats(self):
        self.assertFalse(self.auth.can(
            self.user(5, subadmin=True), 'read', self.stat))

    def test_authenticated_user_can_start_a_stats_query(self):
        self.assertTrue(self.auth.can(self.user(2), 'read'))

    def test_anonymous_user_cannot_read_stats(self):
        anonymous = self.user(None, authenticated=False)

        self.assertFalse(self.auth.can(anonymous, 'read'))
        self.assertFalse(self.auth.can(anonymous, 'read', self.stat))


if __name__ == '__main__':
    unittest.main()
