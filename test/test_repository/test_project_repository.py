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
# Cache global variables for timeouts
from unittest.mock import patch
from sqlalchemy.exc import IntegrityError

from test import Test, db, with_context
from nose.tools import assert_raises
from test.factories import ProjectFactory, CategoryFactory
from pybossa.repositories import ProjectRepository
from pybossa.exc import WrongObjectError, DBIntegrityError
from werkzeug.exceptions import BadRequest


class TestProjectRepositoryForProjects(Test):

    def setUp(self):
        super(TestProjectRepositoryForProjects, self).setUp()
        self.project_repo = ProjectRepository(db)
        self.project_info = dict(
                    data_classification=dict(input_data="L4 - public", output_data="L4 - public"),
                    kpi=1,
                    product='abc',
                    subproduct='def')
        self.validate_fields = [{
            "path": "ext_config::service::file_path",
            "regex": [r"[\\\{\}\`\[\]\"\'\^\%\*\>\<\~\#\|\s]", r'[\x00-\x1f]', r'[\x80-\xff]', '\x7f'],
            "error_msg": "File path contains invalid characters."
        }]


    @with_context
    def test_get_return_none_if_no_project(self):
        """Test get method returns None if there is no project with the
        specified id"""

        project = self.project_repo.get(2)

        assert project is None, project


    @with_context
    def test_get_returns_project(self):
        """Test get method returns a project if exists"""

        project = ProjectFactory.create()

        retrieved_project = self.project_repo.get(project.id)

        assert project == retrieved_project, retrieved_project


    @with_context
    def test_get_by_shortname_return_none_if_no_project(self):
        """Test get_by_shortname returns None when a project with the specified
        short_name does not exist"""

        project = self.project_repo.get_by_shortname('thisprojectdoesnotexist')

        assert project is None, project


    @with_context
    def test_get_by_shortname_returns_the_project(self):
        """Test get_by_shortname returns a project if exists"""

        project = ProjectFactory.create()

        retrieved_project = self.project_repo.get_by_shortname(project.short_name)

        assert project == retrieved_project, retrieved_project


    @with_context
    def test_get_by(self):
        """Test get_by returns a project with the specified attribute"""

        project = ProjectFactory.create(name='My Project', short_name='myproject')

        retrieved_project = self.project_repo.get_by(name=project.name)

        assert project == retrieved_project, retrieved_project


    @with_context
    def test_get_by_returns_none_if_no_project(self):
        """Test get_by returns None if no project matches the query"""

        ProjectFactory.create(name='My Project', short_name='myproject')

        project = self.project_repo.get_by(name='no_name')

        assert project is None, project


    @with_context
    def get_all_returns_list_of_all_projects(self):
        """Test get_all returns a list of all the existing projects"""

        projects = ProjectFactory.create_batch(3)

        retrieved_projects = self.project_repo.get_all()

        assert isinstance(retrieved_projects, list)
        assert len(retrieved_projects) == len(projects), retrieved_projects
        for project in retrieved_projects:
            assert project in projects, project


    @with_context
    def test_filter_by_no_matches(self):
        """Test filter_by returns an empty list if no projects match the query"""

        ProjectFactory.create(name='My Project', short_name='myproject')

        retrieved_projects = self.project_repo.filter_by(name='no_name')

        assert isinstance(retrieved_projects, list)
        assert len(retrieved_projects) == 0, retrieved_projects


    @with_context
    def test_filter_by_one_condition(self):
        """Test filter_by returns a list of projects that meet the filtering
        condition"""

        ProjectFactory.create_batch(3, allow_anonymous_contributors=False)
        should_be_missing = ProjectFactory.create(allow_anonymous_contributors=True)

        retrieved_projects = self.project_repo.filter_by(allow_anonymous_contributors=False)

        assert len(retrieved_projects) == 3, retrieved_projects
        assert should_be_missing not in retrieved_projects, retrieved_projects


    @with_context
    def test_filter_by_multiple_conditions(self):
        """Test filter_by supports multiple-condition queries"""

        ProjectFactory.create_batch(2, allow_anonymous_contributors=False, featured=False)
        project = ProjectFactory.create(allow_anonymous_contributors=False, featured=True)

        retrieved_projects = self.project_repo.filter_by(
                                            allow_anonymous_contributors=False,
                                            featured=True)

        assert len(retrieved_projects) == 1, retrieved_projects
        assert project in retrieved_projects, retrieved_projects


    @with_context
    def test_filter_by_limit_offset(self):
        """Test that filter_by supports limit and offset options"""

        ProjectFactory.create_batch(4)
        all_projects = self.project_repo.filter_by()

        first_two = self.project_repo.filter_by(limit=2)
        last_two = self.project_repo.filter_by(limit=2, offset=2)

        assert len(first_two) == 2, first_two
        assert len(last_two) == 2, last_two
        assert first_two == all_projects[:2]
        assert last_two == all_projects[2:]


    @with_context
    def test_save(self):
        """Test save persist the project"""

        project = ProjectFactory.build()
        project.set_password('hello')
        assert self.project_repo.get(project.id) is None

        self.project_repo.save(project)

        assert self.project_repo.get(project.id) == project, "Project not saved"


    @with_context
    def test_save_config_file_path(self):
        """Test save with valid characters in project info"""
        with patch.dict(self.flask_app.config, {'PROJECT_INFO_FIELDS_TO_VALIDATE': self.validate_fields}):
            project = ProjectFactory.build(
                info=dict(
                    ext_config=dict(service=dict(file_path="abc/def")),
                    **self.project_info))
            assert self.project_repo.get(project.id) is None
            self.project_repo.save(project)
            assert self.project_repo.get(project.id) == project, "Project not saved"


    @with_context
    def test_save_config_file_path_fail(self):
        """Test save with invalid characters in project info"""
        with patch.dict(self.flask_app.config, {'PROJECT_INFO_FIELDS_TO_VALIDATE': self.validate_fields}):
            project1 = ProjectFactory.build(
                info=dict(
                    ext_config=dict(service=dict(file_path="abc/ def")),
                    **self.project_info))
            assert self.project_repo.get(project1.id) is None
            with assert_raises(BadRequest) as err:
                self.project_repo.save(project1)

            # path contains a space
            assert err.exception.description == "File path contains invalid characters.", err.exception.description

            project2 = ProjectFactory.build(
                info=dict(
                    ext_config=dict(service=dict(file_path="abc/%20def")),
                    **self.project_info))
            assert self.project_repo.get(project2.id) is None
            with assert_raises(BadRequest) as err:
                self.project_repo.save(project2)

            # path contains a %
            assert err.exception.description == "File path contains invalid characters.", err.exception.description


    @with_context
    def test_get_nested_value(self):
        """Test _get_nested_value() helper method"""
        data = {
            "foo": {
                "bar": {
                    "bas": "hello"
                }
            }
        }
        result = ProjectRepository._get_nested_value(self, data, "foo::bar::bas", separator="::")
        assert result == 'hello', result

        result = ProjectRepository._get_nested_value(self, data, "bad::path", separator="::")
        assert result == None, result

        result = ProjectRepository._get_nested_value(self, data, "", separator="::")
        assert result == None, result


    @with_context
    def test_save_project_password_required(self):
        """Test save project without password fails when password required"""
        with patch.dict(self.flask_app.config,
                        {'PROJECT_PASSWORD_REQUIRED': True}):
            project = ProjectFactory.build()
            assert self.project_repo.get(project.id) is None

            assert_raises(BadRequest, self.project_repo.save, project)


    @with_context
    def test_save_project_password_not_required(self):
        """Test save project without password success when password not required"""
        with patch.dict(self.flask_app.config,
                        {'PROJECT_PASSWORD_REQUIRED': False}):
            project = ProjectFactory.build()
            assert self.project_repo.get(project.id) is None

            self.project_repo.save(project)

            assert self.project_repo.get(project.id) == project, "Project not saved"


    @with_context
    def test_save_fails_if_missing_name(self):
        """Test save raises a BadRequest if project has no name"""
        project = ProjectFactory.build(name=None)
        project.set_password('hello')

        with assert_raises(BadRequest) as err:
            self.project_repo.save(project)
        assert err.exception.description == "Name required"


    @with_context
    def test_save_fails_if_missing_short_name(self):
        """Test save raises a BadRequest if project has no short_name"""
        project = ProjectFactory.build(name="exists", short_name=None)
        project.set_password('hello')

        with assert_raises(BadRequest) as err:
            self.project_repo.save(project)
        assert err.exception.description == "Short_name required"


    @with_context
    def test_save_fails_if_missing_description(self):
        """Test save raises a BadRequest if project has no description"""
        project = ProjectFactory.build(name="exists", short_name="exists", description=None)
        project.set_password('hello')

        with assert_raises(BadRequest) as err:
            self.project_repo.save(project)
        assert err.exception.description == "Description required"


    @with_context
    def test_save_fails_if_missing_kpi(self):
        """Test save raises a BadRequest if project has no kpi"""
        project = ProjectFactory.build(name="exists", short_name="exists", description="exists")
        project.info["kpi"] = None
        project.set_password('hello')

        with assert_raises(BadRequest) as err:
            self.project_repo.save(project)
        assert err.exception.description == "KPI required"


    @with_context
    def test_save_fails_if_invalid_kpi(self):
        """Test save raises a BadRequest if project kpi is invalid"""
        project = ProjectFactory.build(name="exists", short_name="exists", description="exists")
        project.info["kpi"] = ''
        project.set_password('hello')

        # fail if not value
        with assert_raises(BadRequest) as err:
            self.project_repo.save(project)
        assert err.exception.description == "KPI must be value between 0.1 and 120"

        project.info["kpi"] = 121
        project.set_password('hello')

        # fail if out of range
        with assert_raises(BadRequest) as err:
            self.project_repo.save(project)
        assert err.exception.description == "KPI must be value between 0.1 and 120"


    @with_context
    def test_save_fails_if_missing_product(self):
        """Test save raises a BadRequest if project has no product"""
        project = ProjectFactory.build(name="exists", short_name="exists", description="exists")
        project.info["product"] = None
        project.set_password('hello')

        with assert_raises(BadRequest) as err:
            self.project_repo.save(project)
        assert err.exception.description == "Product and subproduct required"


    @with_context
    def test_save_fails_if_missing_subproduct(self):
        """Test save raises a BadRequest if project has no subproduct"""
        project = ProjectFactory.build(name="exists", short_name="exists", description="exists")
        project.info["subproduct"] = None
        project.set_password('hello')

        with assert_raises(BadRequest) as err:
            self.project_repo.save(project)
        assert err.exception.description == "Product and subproduct required"


    @with_context
    def test_save_fails_if_invalid_product(self):
        """Test save raises a BadRequest if project has invalid product"""
        project = ProjectFactory.build(name="exists", short_name="exists", description="exists")
        project.info["product"] = "wrong"
        project.set_password('hello')

        with assert_raises(BadRequest) as err:
            self.project_repo.save(project)
        assert err.exception.description == "Invalid product"


    @with_context
    def test_save_fails_if_invalid_subproduct(self):
        """Test save raises a BadRequest if project has invalid subproduct"""
        project = ProjectFactory.build(name="exists", short_name="exists", description="exists")
        project.info["subproduct"] = "wrong"
        project.set_password('hello')

        with assert_raises(BadRequest) as err:
            self.project_repo.save(project)
        assert err.exception.description == "Invalid subproduct"


    @with_context
    def test_save_only_saves_projects(self):
        """Test save raises a WrongObjectError when an object which is not
        a Project instance is saved"""

        bad_object = dict()

        assert_raises(WrongObjectError, self.project_repo.save, bad_object)


    @with_context
    def test_update(self):
        """Test update persists the changes made to the project"""

        project = ProjectFactory.create(description='this is a project')
        project.description = 'the description has changed'

        self.project_repo.update(project)
        updated_project = self.project_repo.get(project.id)

        assert updated_project.description == 'the description has changed', updated_project


    @with_context
    def test_update_fails_if_integrity_error(self):
        """Test update raises a IntegrityError if the instance to be updated
        lacks a required value"""

        project = ProjectFactory.create()
        project.name = None

        # self.project_repo.update(project) generates IntegrityError
        assert_raises(IntegrityError, self.project_repo.update, project)


    @with_context
    def test_update_only_updates_projects(self):
        """Test update raises a WrongObjectError when an object which is not
        a Project instance is updated"""

        bad_object = dict()

        assert_raises(WrongObjectError, self.project_repo.update, bad_object)


    @with_context
    def test_delete(self):
        """Test delete removes the project instance"""

        project = ProjectFactory.create()

        self.project_repo.delete(project)
        deleted = self.project_repo.get(project.id)

        assert deleted is None, deleted


    @with_context
    def test_delete_also_removes_dependant_resources(self):
        """Test delete removes project tasks and taskruns too"""
        from test.factories import TaskFactory, TaskRunFactory, BlogpostFactory
        from pybossa.repositories import TaskRepository, BlogRepository

        project = ProjectFactory.create()
        task = TaskFactory.create(project=project)
        taskrun = TaskRunFactory.create(task=task)
        blogpost = BlogpostFactory.create(project=project)

        self.project_repo.delete(project)
        deleted_task = TaskRepository(db).get_task(task.id)
        deleted_taskrun = TaskRepository(db).get_task_run(taskrun.id)
        deleted_blogpost = BlogRepository(db).get(blogpost.id)

        assert deleted_task is None, deleted_task
        assert deleted_taskrun is None, deleted_taskrun


    @with_context
    def test_delete_only_deletes_projects(self):
        """Test delete raises a WrongObjectError if is requested to delete other
        than a project"""

        bad_object = dict()

        assert_raises(WrongObjectError, self.project_repo.delete, bad_object)


    @with_context
    def test_project_save_without_data_classification_fails(self):
        """Test save fails if the project has no data classification"""

        # project w/o data classification raises error
        project = ProjectFactory.build(info=dict())
        project.set_password('hello')
        assert self.project_repo.get(project.id) is None
        assert_raises(BadRequest, self.project_repo.save, project)

        # project w/o input data classification raises error
        project = ProjectFactory.build(info=dict(data_classification=dict(output_data="a")))
        project.set_password('hello')
        assert self.project_repo.get(project.id) is None
        assert_raises(BadRequest, self.project_repo.save, project)

        # project w/o output data classification raises error
        project = ProjectFactory.build(info=dict(data_classification=dict(input_data="a")))
        project.set_password('hello')
        assert self.project_repo.get(project.id) is None
        assert_raises(BadRequest, self.project_repo.save, project)

        # project w/ incorrect input data classification raises error
        project = ProjectFactory.build(info=dict(data_classification=dict(input_data="a", output_data="a")))
        project.set_password('hello')
        assert self.project_repo.get(project.id) is None
        assert_raises(BadRequest, self.project_repo.save, project)

        # project w/ incorrect output data classification raises error
        project = ProjectFactory.build(info=dict(data_classification=dict(input_data="L3 - community", output_data="a")))
        project.set_password('hello')
        assert self.project_repo.get(project.id) is None
        assert_raises(BadRequest, self.project_repo.save, project)


class TestProjectRepositoryForCategories(Test):

    def setUp(self):
        super(TestProjectRepositoryForCategories, self).setUp()
        self.project_repo = ProjectRepository(db)


    @with_context
    def test_get_category_return_none_if_no_category(self):
        """Test get_category method returns None if there is no category with
        the specified id"""

        category = self.project_repo.get_category(200)

        assert category is None, category


    @with_context
    def test_get_category_returns_category(self):
        """Test get_category method returns a category if exists"""

        category = CategoryFactory.create()

        retrieved_category = self.project_repo.get_category(category.id)

        assert category == retrieved_category, retrieved_category


    @with_context
    def test_get_category_by(self):
        """Test get_category returns a category with the specified attribute"""

        category = CategoryFactory.create(name='My Cat', short_name='mycat')

        retrieved_category = self.project_repo.get_category_by(name=category.name)

        assert category == retrieved_category, retrieved_category


    @with_context
    def test_get_category_by_returns_none_if_no_category(self):
        """Test get_category returns None if no category matches the query"""

        CategoryFactory.create(name='My Project', short_name='mycategory')

        category = self.project_repo.get_by(name='no_name')

        assert category is None, category


    @with_context
    def get_all_returns_list_of_all_categories(self):
        """Test get_all_categories returns a list of all the existing categories"""

        categories = CategoryFactory.create_batch(3)

        retrieved_categories = self.project_repo.get_all_categories()

        assert isinstance(retrieved_categories, list)
        assert len(retrieved_categories) == len(categories), retrieved_categories
        for category in retrieved_categories:
            assert category in categories, category


    @with_context
    def test_filter_categories_by_no_matches(self):
        """Test filter_categories_by returns an empty list if no categories
        match the query"""

        CategoryFactory.create(name='My Project', short_name='mycategory')

        retrieved_categories = self.project_repo.filter_categories_by(name='no_name')

        assert isinstance(retrieved_categories, list)
        assert len(retrieved_categories) == 0, retrieved_categories

    @with_context
    def test_filter_categories_by_ownerid(self):
        """Test filter_categories_by removes ownerid from query."""

        CategoryFactory.create(name='My Project', short_name='mycategory')

        retrieved_categories = self.project_repo.filter_categories_by(short_name='mycategory',
                                                                      owner_id=1)

        assert isinstance(retrieved_categories, list)
        assert len(retrieved_categories) == 1, retrieved_categories

    @with_context
    def test_filter_categories_by_one_condition(self):
        """Test filter_categories_by returns a list of categories that meet
        the filtering condition"""

        CategoryFactory.create_batch(3, description='generic category')
        should_be_missing = CategoryFactory.create(description='other category')

        retrieved_categories = (self.project_repo
            .filter_categories_by(description='generic category'))

        assert len(retrieved_categories) == 3, retrieved_categories
        assert should_be_missing not in retrieved_categories, retrieved_categories


    @with_context
    def test_filter_categories_by_limit_offset(self):
        """Test that filter_categories_by supports limit and offset options"""

        CategoryFactory.create_batch(4)
        all_categories = self.project_repo.filter_categories_by()

        first_two = self.project_repo.filter_categories_by(limit=2)
        last_two = self.project_repo.filter_categories_by(limit=2, offset=2)

        assert len(first_two) == 2, first_two
        assert len(last_two) == 2, last_two
        assert first_two == all_categories[:2]
        assert last_two == all_categories[2:]


    @with_context
    def test_save_category(self):
        """Test save_category persist the category"""

        category = CategoryFactory.build()
        assert self.project_repo.get(category.id) is None

        self.project_repo.save_category(category)

        assert self.project_repo.get_category(category.id) == category, "Category not saved"


    @with_context
    def test_save_category_fails_if_integrity_error(self):
        """Test save_category raises a DBIntegrityError if the instance to be
       saved lacks a required value"""

        category = CategoryFactory.build(name=None)

        assert_raises(DBIntegrityError, self.project_repo.save_category, category)


    @with_context
    def test_save_category_only_saves_categories(self):
        """Test save_category raises a WrongObjectError when an object which is
        not a Category instance is saved"""

        bad_object = ProjectFactory.build()

        assert_raises(WrongObjectError, self.project_repo.save_category, bad_object)


    @with_context
    def test_update_category(self):
        """Test update_category persists the changes made to the category"""

        info = {'key': 'val'}
        category = CategoryFactory.create(info=info)
        info_new = {'f': 'v'}
        category.info = info_new

        self.project_repo.update_category(category)
        updated_category = self.project_repo.get_category(category.id)

        assert updated_category.info == info_new, updated_category


    @with_context
    def test_update_category_fails_if_integrity_error(self):
        """Test update raises a DBIntegrityError if the instance to be updated
        lacks a required value"""

        category = CategoryFactory.create()
        category.name = None

        assert_raises(DBIntegrityError, self.project_repo.update_category, category)


    @with_context
    def test_update_category_only_updates_categories(self):
        """Test update_category raises a WrongObjectError when an object which is
        not a Category instance is updated"""

        bad_object = ProjectFactory.build()

        assert_raises(WrongObjectError, self.project_repo.update_category, bad_object)


    @with_context
    def test_delete_category(self):
        """Test delete_category removes the category instance"""

        category = CategoryFactory.create()

        self.project_repo.delete_category(category)
        deleted = self.project_repo.get_category(category.id)

        assert deleted is None, deleted


    @with_context
    def test_delete_category_only_deletes_categories(self):
        """Test delete_category raises a WrongObjectError if is requested to
        delete other than a category"""

        bad_object = dict()

        assert_raises(WrongObjectError, self.project_repo.delete_category, bad_object)

    @with_context
    def test_fulltext_search_category(self):
        """Test fulltext search in JSON info works."""
        category = CategoryFactory.create()
        text = 'something word you me bar'
        data = {'foo': text}
        category.info = data
        self.project_repo.update_category(category)

        info = 'foo::word'
        res = self.project_repo.filter_categories_by(info=info, fulltextsearch='1')
        assert len(res) == 1, len(res)
        assert res[0][0].info['foo'] == text, res[0]

        res = self.project_repo.filter_categories_by(info=info)
        assert len(res) == 0, len(res)

    @with_context
    def test_fulltext_search_category_01(self):
        """Test fulltext search in JSON info works."""
        category = CategoryFactory.create()
        text = 'something word you me bar'
        data = {'foo': text, 'bar': 'foo'}
        category.info = data
        self.project_repo.update_category(category)

        info = 'foo::word&bar|bar::foo'
        res = self.project_repo.filter_categories_by(info=info, fulltextsearch='1')
        assert len(res) == 1, len(res)
        assert res[0][0].info['foo'] == text, res[0]


    @with_context
    def test_info_json_search_category(self):
        """Test search in JSON info works."""
        category = CategoryFactory.create()
        text = 'bar'
        data = {'foo': text}
        category.info = data
        self.project_repo.update_category(category)

        info = 'foo::bar'
        res = self.project_repo.filter_categories_by(info=info)
        assert len(res) == 1, len(res)
        assert res[0].info['foo'] == text, res[0]
