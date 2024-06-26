import json
from unittest.mock import patch
from test.helper import web
from test import with_context
from test import db, Fixtures
from test.factories import ProjectFactory, UserFactory
from pybossa.core import user_repo
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
        self.signin()
        res = self.app.get("/admin/users/addsubadmin/2", follow_redirects=True)
        self.signout()
        self.signin(email="john2@john.com", password="passwd")
        self.new_project()

        res = self.app.get('/project/sampleapp/coowners', follow_redirects=True)
        assert "Manage Co-owners" in str(res.data), res.data

        self.signout()
        self.signin()

        res = self.app.get('/project/sampleapp/coowners', follow_redirects=True)
        assert "Manage Co-owners" in str(res.data), res.data

    @with_context
    def test_01_admin_and_owner_add_del_coowner(self):
        """Test admin and owner can add/del a subadmin to coowners"""
        self.register()
        self.signin()
        self.signout()
        self.register(name="John2", email="john2@john.com",
                      password="passwd")
        self.register(name="John3", email="john3@john.com",
                      password="passwd")
        self.signout()
        self.signin()
        res = self.app.get("/admin/users/addsubadmin/2", follow_redirects=True)
        res = self.app.get("/admin/users/addsubadmin/3", follow_redirects=True)
        self.signout()
        self.signin(email="john2@john.com", password="passwd")
        self.new_project()

        res = self.app.get('/project/sampleapp/add_coowner/John3', follow_redirects=True)
        assert "John3" in str(res.data), res.data

        res = self.app.get('/project/sampleapp/del_coowner/John3', follow_redirects=True)
        assert "John3" not in str(res.data), res.data

        self.signout()
        self.signin()

        res = self.app.get('/project/sampleapp/add_coowner/John3', follow_redirects=True)
        assert "John3" in str(res.data), res.data

        res = self.app.get('/project/sampleapp/del_coowner/John3', follow_redirects=True)
        assert "John3" not in str(res.data), res.data

    @with_context
    def test_02_nonadmin_notowner_authenticated_user_cannot_add_del_coowners(self):
        """Test non admin/not an owner authenticated user cannot add/del coowners to a project"""
        self.register()
        self.signin()
        self.signout()
        self.register(name="John2", email="john2@john.com",
                      password="passwd")
        self.register(name="John3", email="john3@john.com",
                      password="passwd")
        self.signout()
        self.signin()
        self.new_project()
        res = self.app.get("/admin/users/addsubadmin/2", follow_redirects=True)
        res = self.app.get('/project/sampleapp/add_coowner/John2', follow_redirects=True)
        self.signout()
        self.signin(email="john3@john.com", password="passwd")

        res = self.app.get('/project/sampleapp/add_coowner/John3', follow_redirects=True)
        res = self.app.get('/project/sampleapp/del_coowner/John2', follow_redirects=True)

        self.signout()
        self.signin()

        res = self.app.get('/project/sampleapp/coowners', follow_redirects=True)
        assert "John2" in str(res.data), res.data
        assert "John3" not in str(res.data), res.data

    @with_context
    def test_03_misc(self):
        """
        Test flash messages for add coowner/remove coowner
        """
        self.register()
        self.signin()
        self.register(name="John2", email="john2@john.com",
                      password="passwd")
        self.app.get("/admin/users/addsubadmin/2", follow_redirects=True)
        self.register(name="John3", email="john3@john.com",
                      password="passwd")
        self.app.get("/admin/users/addsubadmin/3", follow_redirects=True)
        self.register(name="John4", email="john4@john.com",
                      password="passwd")
        self.app.get("/admin/users/addsubadmin/4", follow_redirects=True)
        self.signin(email="john2@john.com", password="passwd")
        self.new_project()

        res = self.app.get('/project/sampleapp/add_coowner/John2',
                           follow_redirects=True)
        assert "User is already an owner" in str(res.data), res.data

        res = self.app.get('/project/sampleapp/del_coowner/John2',
                           follow_redirects=True)
        assert "Cannot remove project creator" in str(res.data), res.data

        res = self.app.get('/project/sampleapp/add_coowner/John3',
                           follow_redirects=True)
        assert "John3" in str(res.data), res.data

        self.signout()
        self.signin(email="john3@john.com", password="passwd")

        res = self.app.get('/project/sampleapp/del_coowner/John2',
                           follow_redirects=True)
        assert "Cannot remove project creator" in str(res.data), res.data

        res = self.app.get('/project/sampleapp/del_coowner/John4',
                           follow_redirects=True)
        assert "User is not a project owner" in str(res.data), res.data

    @with_context
    @patch('pybossa.view.account.app_settings.upref_mdata.country_name_to_country_code', new={})
    @patch('pybossa.view.account.app_settings.upref_mdata.country_code_to_country_name', new={})
    @patch('pybossa.cache.task_browse_helpers.app_settings.upref_mdata')
    def test_coowner_can(self, upref_mdata):
        """
        Coowner can access features
        """
        self.register()
        self.register(name="John2", email="john2@john.com",
                      password="passwd")
        self.signin()
        self.new_project()
        self.new_task(1)
        self.app.get("/admin/users/addsubadmin/2", follow_redirects=True)
        res = self.app.get('/project/sampleapp/add_coowner/John2',
                           follow_redirects=True)
        assert "John2" in str(res.data), res.data
        self.signout()

        self.signin(email="john2@john.com", password="passwd")

        # coowner can browse tasks in a draft project
        res = self.app.get('/project/sampleapp/tasks/browse')
        assert 'Browse Tasks' in str(res.data), res.data
        # coowner can modify task presenter
        res = self.app.get('/project/sampleapp/tasks/taskpresentereditor')
        assert 'Task Presenter Editor' in str(res.data), res.data
        # coowner can delete tasks
        res = self.app.post('/project/sampleapp/tasks/delete',
                            follow_redirects=True)
        assert 'Tasks and taskruns with no associated results have been deleted' in str(res.data), res.data
        # coowner can delete the project
        res = self.app.post('/project/sampleapp/delete',
                            follow_redirects=True)
        assert 'Project deleted' in str(res.data), res.data

    @with_context
    def test_user_search(self):
        from pybossa.core import project_repo

        admin, user2, user3, user4 = UserFactory.create_batch(4)

        project = ProjectFactory.create(owner=user2, published=True, short_name='sampleapp')
        project.owners_ids.append(user3.id)
        project_repo.save(project)

        csrf = self.get_csrf('/account/signin')
        self.signin(email=admin.email_addr, csrf=csrf)

        data = {'user': user2.name}
        res = self.app.post('/project/%s/coowners?api_key=%s' % (project.short_name, admin.api_key),
                            content_type='application/json',
                            data=json.dumps(data),
                            follow_redirects=True,
                            headers={'X-CSRFToken': csrf})
        res_data = json.loads(res.data)

        # Verify project owner is only user included in contacts.
        assert len(res_data['contacts_dict']) == 1
        assert res_data['contacts_dict'][0]['id'] == user2.id

        # Verify project coowner is included in coowners.
        assert len(res_data['coowners_dict']) == 2
        assert res_data['coowners_dict'][0]['id'] == user2.id
        assert res_data['coowners_dict'][1]['id'] == user3.id

    @with_context
    def test_coowner_add_contact(self):
        from pybossa.core import project_repo

        admin, user2, user3, user4 = UserFactory.create_batch(4)

        project = ProjectFactory.create(owner=user2, published=True, short_name='sampleapp')
        project.owners_ids.append(user3.id)
        project_repo.save(project)

        csrf = self.get_csrf('/account/signin')
        self.signin(email=admin.email_addr, csrf=csrf)

        data = {'user': user3.name}
        res = self.app.post('/project/%s/coowners?api_key=%s' % (project.short_name, admin.api_key),
                            content_type='application/json',
                            data=json.dumps(data),
                            follow_redirects=True,
                            headers={'X-CSRFToken': csrf})
        res_data = json.loads(res.data)

        # Verify project owner is only user included in contacts.
        assert len(res_data['contacts_dict']) == 1
        assert res_data['contacts_dict'][0]['id'] == user2.id

        # Verify project coowner is included in coowners.
        assert len(res_data['coowners_dict']) == 2
        assert res_data['coowners_dict'][0]['id'] == user2.id
        assert res_data['coowners_dict'][1]['id'] == user3.id

        # Add user3 (coowner) as a contact.
        data = {'coowners': project.owners_ids, 'contacts': [user2.id, user3.id]}
        res = self.app.post('/project/%s/coowners?api_key=%s' % (project.short_name, admin.api_key),
                            content_type='application/json',
                            data=json.dumps(data),
                            follow_redirects=True,
                            headers={'X-CSRFToken': csrf})
        res_data = json.loads(res.data)

        # Verify project owner and coowner are included in contacts.
        assert len(res_data['contacts_dict']) == 2
        assert res_data['contacts_dict'][0]['id'] == user2.id
        assert res_data['contacts_dict'][1]['id'] == user3.id

    @with_context
    def test_coowner_remove_contact(self):
        from pybossa.core import project_repo

        admin, user2, user3, user4 = UserFactory.create_batch(4)

        project = ProjectFactory.create(owner=user2, published=True, short_name='sampleapp')
        project.owners_ids.append(user3.id)
        project_repo.save(project)

        csrf = self.get_csrf('/account/signin')
        self.signin(email=admin.email_addr, csrf=csrf)

        data = {'user': user3.name}
        res = self.app.post('/project/%s/coowners?api_key=%s' % (project.short_name, admin.api_key),
                            content_type='application/json',
                            data=json.dumps(data),
                            follow_redirects=True,
                            headers={'X-CSRFToken': csrf})
        res_data = json.loads(res.data)

        # Verify project owner is only user included in contacts.
        assert len(res_data['contacts_dict']) == 1
        assert res_data['contacts_dict'][0]['id'] == user2.id

        # Verify project coowner is included in coowners.
        assert len(res_data['coowners_dict']) == 2
        assert res_data['coowners_dict'][0]['id'] == user2.id
        assert res_data['coowners_dict'][1]['id'] == user3.id

        # Add user3 (coowner) as a contact.
        data = {'coowners': project.owners_ids, 'contacts': [user2.id, user3.id]}
        res = self.app.post('/project/%s/coowners?api_key=%s' % (project.short_name, admin.api_key),
                            content_type='application/json',
                            data=json.dumps(data),
                            follow_redirects=True,
                            headers={'X-CSRFToken': csrf})
        res_data = json.loads(res.data)

        # Verify project owner and coowner are included in contacts.
        assert len(res_data['contacts_dict']) == 2
        assert res_data['contacts_dict'][0]['id'] == user2.id
        assert res_data['contacts_dict'][1]['id'] == user3.id

        # Remove user3 as a coowner.
        data = {'coowners': [user2.id], 'contacts': [user2.id, user3.id]}
        res = self.app.post('/project/%s/coowners?api_key=%s' % (project.short_name, admin.api_key),
                            content_type='application/json',
                            data=json.dumps(data),
                            follow_redirects=True,
                            headers={'X-CSRFToken': csrf})
        res_data = json.loads(res.data)

        # Verify project owner is only user included in contacts.
        assert len(res_data['contacts_dict']) == 1
        assert res_data['contacts_dict'][0]['id'] == user2.id

        # Verify coowner has been removed.
        assert len(res_data['coowners_dict']) == 1
        assert res_data['coowners_dict'][0]['id'] == user2.id

        # Verify contact has been removed.
        assert len(res_data['contacts_dict']) == 1
        assert res_data['contacts_dict'][0]['id'] == user2.id

    @with_context
    def test_user_search_found(self):
        from pybossa.core import project_repo

        admin, user2, user3, user4 = UserFactory.create_batch(4)

        project = ProjectFactory.create(owner=user2, published=True, short_name='sampleapp')
        project.owners_ids.append(user3.id)
        project_repo.save(project)

        csrf = self.get_csrf('/account/signin')
        self.signin(email=admin.email_addr, csrf=csrf)

        data = {'user': user3.name}
        res = self.app.post('/project/%s/coowners?api_key=%s' % (project.short_name, admin.api_key),
                            content_type='application/json',
                            data=json.dumps(data),
                            follow_redirects=True,
                            headers={'X-CSRFToken': csrf})
        res_data = json.loads(res.data)

        # Verify user3 is found in result.
        assert len(res_data['found']) == 1
        assert (res_data['found'][0]['id'] == user3.id)

    @with_context
    def test_user_search_not_found(self):
        from pybossa.core import project_repo

        admin, user2, user3, user4 = UserFactory.create_batch(4)

        project = ProjectFactory.create(owner=user2, published=True, short_name='sampleapp')
        project.owners_ids.append(user3.id)
        project_repo.save(project)

        csrf = self.get_csrf('/account/signin')
        self.signin(email=admin.email_addr, csrf=csrf)

        data = {'user': 'not exist'}
        res = self.app.post('/project/%s/coowners?api_key=%s' % (project.short_name, admin.api_key),
                            content_type='application/json',
                            data=json.dumps(data),
                            follow_redirects=True,
                            headers={'X-CSRFToken': csrf})
        res_data = json.loads(res.data)

        # Verify no results
        assert len(res_data['found']) == 0

    @with_context
    def test_user_search_partial_found(self):
        from pybossa.core import project_repo

        admin, user2, user3, user4 = UserFactory.create_batch(4)

        project = ProjectFactory.create(owner=user2, published=True, short_name='sampleapp')
        project.owners_ids.append(user3.id)
        project_repo.save(project)

        csrf = self.get_csrf('/account/signin')
        self.signin(email=admin.email_addr, csrf=csrf)

        data = {'user': 'User'}
        res = self.app.post('/project/%s/coowners?api_key=%s' % (project.short_name, admin.api_key),
                            content_type='application/json',
                            data=json.dumps(data),
                            follow_redirects=True,
                            headers={'X-CSRFToken': csrf})
        res_data = json.loads(res.data)

        # Verify results (admin, user2, user3, user4)
        assert len(res_data['found']) == 4

    @with_context
    def test_user_search_contact_found(self):
        from pybossa.core import project_repo

        admin, user2, user3, user4 = UserFactory.create_batch(4)

        project = ProjectFactory.create(owner=user2, published=True, short_name='sampleapp')
        project.owners_ids.append(user3.id)
        project_repo.save(project)

        csrf = self.get_csrf('/account/signin')
        self.signin(email=admin.email_addr, csrf=csrf)

        data = {'user': 'User', 'contact': True}
        res = self.app.post('/project/%s/coowners?api_key=%s' % (project.short_name, admin.api_key),
                            content_type='application/json',
                            data=json.dumps(data),
                            follow_redirects=True,
                            headers={'X-CSRFToken': csrf})
        res_data = json.loads(res.data)

        # Verify results (user2, user3)
        assert len(res_data['found']) == 2
        assert res_data['found'][0]['id'] == user2.id
        assert res_data['found'][1]['id'] == user3.id

    @with_context
    def test_user_search_contact_not_found(self):
        from pybossa.core import project_repo

        admin, user2, user3, user4 = UserFactory.create_batch(4)

        project = ProjectFactory.create(owner=user2, published=True, short_name='sampleapp')
        project.owners_ids.append(user3.id)
        project_repo.save(project)

        csrf = self.get_csrf('/account/signin')
        self.signin(email=admin.email_addr, csrf=csrf)

        data = {'user': user4.name, 'contact': True}
        res = self.app.post('/project/%s/coowners?api_key=%s' % (project.short_name, admin.api_key),
                            content_type='application/json',
                            data=json.dumps(data),
                            follow_redirects=True,
                            headers={'X-CSRFToken': csrf})
        res_data = json.loads(res.data)

        # Verify no results.
        assert len(res_data['found']) == 0

    @with_context
    def test_coowner_invalid(self):
        """
        Test adding and deleting a non-existing user
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

    @with_context
    def test_creator_is_added_as_owner(self):
        """
        Test that project_repo.save includes the creator as an owner even if
        not explicitly specified
        """
        from pybossa.core import project_repo
        self.register()
        project = Fixtures.create_project({
            'passwd_hash': 'hello',
            'data_classification': dict(input_data="L4 - public", output_data="L4 - public"),
            'kpi': 0.5,
            'product': 'abc',
            'subproduct': 'def'
            })
        project.owner_id = 1
        project_repo.save(project)
        assert project.owners_ids == [1]
