from helper import web
from default import with_context
from default import db
from pybossa.repositories import ProjectRepository


class TestCoowners(web.Helper):

    def setup(self):
        super(TestCoowners, self).setUp()
        self.project_repo = ProjectRepository(db)

    @with_context
    def test_00_admin_and_owner_can_access_coowners_page(self):
        """Test admin and owner can access coowners page"""
        self.register()
        self.signin()
        self.signout()
        self.register(name="John2", email="john2@john.com",
                      password="passwd")
        self.signout()
        self.signin(email="john2@john.com", password="passwd")
        self.new_project()

        res = self.app.get('/project/sampleapp/coowners', follow_redirects=True)
        assert "Manage Co-owners" in res.data, res.data

    @with_context
    def test_01_admin_and_owner_add_del_coowner(self):
        """Test admin and owner can add and delete coowners"""
        self.register()
        self.register(name="John2", email="john2@john.com",
                      password="passwd")
        self.register(name="John3", email="john3@john.com",
                      password="passwd")
        self.signin(email="john2@john.com", password="passwd")
        self.new_project()

        res = self.app.get('/project/sampleapp/add_coowner/John3',
                           follow_redirects=True)
        assert "John3" in res.data, res.data

        res = self.app.get('/project/sampleapp/del_coowner/John3',
                           follow_redirects=True)
        assert "John3" not in res.data, res.data

        self.signout()
        self.signin()

        res = self.app.get('/project/sampleapp/add_coowner/John3',
                           follow_redirects=True)
        assert "John3" in res.data, res.data

        res = self.app.get('/project/sampleapp/del_coowner/John3',
                           follow_redirects=True)
        assert "John3" not in res.data, res.data

    @with_context
    def test_02_nonadmin_notowner_authenticated_user_cannot_add_del_coowners(self):
        """
        Test non admin/not an owner authenticated user cannot add and delete
        coowners to a project
        """
        self.register()
        self.register(name="John2", email="john2@john.com",
                      password="passwd")
        self.register(name="John3", email="john3@john.com",
                      password="passwd")
        self.signin()
        self.new_project()
        self.new_task(1)
        res = self.app.get('/project/sampleapp/add_coowner/John2',
                           follow_redirects=True)
        assert "John2" in res.data, res.data
        self.signout()

        self.signin(email="john3@john.com", password="passwd")
        res = self.app.get('/project/sampleapp/add_coowner/John3',
                           follow_redirects=True)
        res = self.app.get('/project/sampleapp/del_coowner/John2',
                           follow_redirects=True)
        self.signout()

        self.signin()
        res = self.app.get('/project/sampleapp/coowners',
                           follow_redirects=True)
        assert "John2" in res.data, res.data
        assert "John3" not in res.data, res.data

    @with_context
    def test_coowner_can(self):
        """
        """
        self.register()
        self.register(name="John2", email="john2@john.com",
                      password="passwd")
        self.signin()
        self.new_project()
        self.new_task(1)
        res = self.app.get('/project/sampleapp/add_coowner/John2',
                           follow_redirects=True)
        assert "John2" in res.data, res.data
        self.signout()

        self.signin(email="john2@john.com", password="passwd")

        # coowner can browse tasks in a draft project
        res = self.app.get('/project/sampleapp/tasks/browse')
        assert 'Browse tasks' in res.data, res.data
        # coowner can modify task presenter
        res = self.app.get('/project/sampleapp/tasks/taskpresentereditor')
        assert 'Task Presenter Editor' in res.data, res.data
        # coowner can delete tasks
        res = self.app.post('/project/sampleapp/tasks/delete',
                            follow_redirects=True)
        assert 'Tasks and taskruns with no associated results have been deleted' in res.data, res.data
        # coowner can delete the project
        res = self.app.post('/project/sampleapp/delete',
                            follow_redirects=True)
        assert 'Project deleted' in res.data, res.data

    @with_context
    def test_coowner_invalid(self):
        """
        """
        self.register()
        self.signin()
        self.new_project()

        # add non-existing user.
        res = self.app.get('/project/sampleapp/add_coowner/John2',
                           follow_redirects=True)
        assert res.status_code == 404, res.status_code
        # delete non-existing user.
        res = self.app.get('/project/sampleapp/del_coowner/John2',
                           follow_redirects=True)
        assert res.status_code == 404, res.status_code
