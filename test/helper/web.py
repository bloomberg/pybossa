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

import json
from unittest.mock import patch

from test import Test, db, Fixtures, with_context
from pybossa.model.category import Category
from pybossa.model.task import Task
from pybossa.model.task_run import TaskRun
from werkzeug.http import parse_cookie
from test.factories import UserFactory


class Helper(Test):
    """Class to help testing the web interface"""


    def html_title(self, title=None):
        """Helper function to create an HTML title"""
        if title is None:
            return "<title>PYBOSSA - PyBossa by Scifabric</title>"
        else:
            return "<title>PYBOSSA &middot; %s - PyBossa by Scifabric</title>" % title

    @patch('pybossa.view.account.signer')
    def register(self, mock=None, fullname='John Doe', name='johndoe',
                 password='p4ssw0rd', email=None, consent=False, subadmin=False,
                 data_access=['L4'], admin=True):

        """Helper function to register and sign in a user"""
        if email is None:
            email = name + '@example.com'
        userdict = {'fullname': fullname, 'name': name,
                    'email_addr': email, 'password': password,
                    'consent': consent, 'subadmin': subadmin,
                    'admin': admin, 'data_access': data_access}
        if mock:
            mock.loads.return_value = userdict

        return self.app.get('/account/register/confirmation?key=fake-key',
                            follow_redirects=True)

    def signin(self, method="POST", email="johndoe@example.com",
               password="p4ssw0rd", next=None, data_access=['L4'],  
               content_type="multipart/form-data", follow_redirects=True, csrf=None):
        """Helper function to sign in current user"""
        url = '/account/signin'
        headers = None
        if next is not None:
            url = url + '?next=' + next
        if method == "POST":
            payload = {'email': email, 'password': password}
            if content_type == 'application/json':
                data = json.dumps(payload)
            else:
                data = payload
            if csrf:
                headers = {'X-CSRFToken': csrf}
            return self.app.post(url, data=data,
                                 content_type=content_type,
                                 follow_redirects=follow_redirects,
                                 headers=headers)
        else:
            return self.app.get(url, follow_redirects=follow_redirects,
                                content_type=content_type, headers=headers)

    def gig_account_creator_register_signin(self, fullname="John Gig", name="gig",
                 password="p4ssw0rd", email=None, consent=False, with_csrf=False):
        if email is None:
            email = name + '@example.com'
        self.register(fullname=fullname, name=name, password=password,
                      email=email, consent=consent)
        csrf = None
        if with_csrf:
            csrf = self.get_csrf('/account/signin')
        self.signin(email=email, password=password, csrf=csrf)

    def signin_user(self, user=None, **kwargs):
        if not user:
            user = UserFactory.create(**kwargs)
        pwd = '123'
        user.set_password(pwd)
        self.signin(email=user.email_addr, password=pwd)

    def otpvalidation(self, method="POST", token='invalid', otp='-1',
                      content_type="multipart/form-data", follow_redirects=True,
                      csrf=None):
        url = '/account/{}/otpvalidation'.format(token)
        headers = None
        if method == 'POST':
            payload = dict(otp=otp)
            if content_type == 'application/json':
                data = json.dumps(payload)
            else:
                data = payload
            if csrf:
                headers = {'X-CSRFToken': csrf}
            return self.app.post(url, data=data,
                                 content_type=content_type,
                                 follow_redirects=follow_redirects,
                                 headers=headers)
        else:
            return self.app.get(url, data=json.dumps({}),
                                content_type=content_type, headers=headers)

    def profile(self, name="johndoe"):
        """Helper function to check profile of signed in user"""
        url = "/account/%s" % name
        return self.app.get(url, follow_redirects=True)

    def update_profile(self, method="POST", id=1, fullname="John Doe",
                       name="johndoe", locale="es",
                       email_addr="johndoe@example.com",
                       subscribed=False,
                       new_name=None,
                       btn='Profile',
                       content_type="multipart/form-data",
                       csrf=None,
                       follow_redirects=True):
        """Helper function to update the profile of users"""
        url = "/account/%s/update" % name
        if new_name:
            name = new_name
        if (method == "POST"):
            payload = {'id': id, 'fullname': fullname,
                       'name': name,
                       'locale': locale,
                       'email_addr': email_addr,
                       'btn': btn}
            if content_type == 'application/json':
                payload = json.dumps(payload)
            headers = None
            if csrf:
                headers = {'X-CSRFToken': csrf}
            return self.app.post(url,
                                 data=payload,
                                 follow_redirects=follow_redirects,
                                 content_type=content_type,
                                 headers=headers)
        else:
            return self.app.get(url,
                                follow_redirects=follow_redirects,
                                content_type=content_type)

    def signout(self, follow_redirects=True, content_type="text/html"):
        """Helper function to sign out current user"""
        return self.app.get('/account/signout',
                            follow_redirects=follow_redirects,
                            content_type=content_type)

    def create_categories(self):
        with self.flask_app.app_context():
            categories = db.session.query(Category).all()
            if len(categories) == 0:
                print("Categories 0")
                print("Creating default ones")
                self._create_categories()


    def new_project(self, method="POST", name="Sample Project",
                        short_name="sampleapp", description="Description",
                        long_description='Long Description\n================', kpi=0.5,
                        input_data_class="L4 - public", output_data_class="L4 - public"):
        """Helper function to create a project"""
        if method == "POST":
            self.create_categories()
            res = self.app.post("/project/new", data={
                'name': name,
                'short_name': short_name,
                'description': description,
                'long_description': long_description,
                'password': 'Abc01$',
                'product': 'abc',
                'subproduct': 'def',
                'kpi': kpi,
                'input_data_class': input_data_class,
                'output_data_class': output_data_class
            }, follow_redirects=True)
        else:
            res = self.app.get("/project/new", follow_redirects=True)
        return res

    def new_task(self, project_id):
        """Helper function to create tasks for a project"""
        tasks = []
        for i in range(0, 10):
            tasks.append(Task(project_id=project_id, state='ongoing', info={}))
        db.session.add_all(tasks)
        db.session.commit()

    def delete_task_runs(self, project_id=1):
        """Deletes all TaskRuns for a given project_id"""
        db.session.query(TaskRun).filter_by(project_id=project_id).delete()
        db.session.commit()

    def task_settings_scheduler(self, method="POST", short_name='sampleapp',
                                sched="default"):
        """Helper function to modify task scheduler"""
        url = "/project/%s/tasks/scheduler" % short_name
        if method == "POST":
            return self.app.post(url, data={
                'sched': sched,
                'gold_task_probability': .4
            }, follow_redirects=True)
        else:
            return self.app.get(url, follow_redirects=True)

    def task_settings_redundancy(self, method="POST", short_name='sampleapp',
                                 n_answers=30):
        """Helper function to modify task redundancy"""
        url = "/project/%s/tasks/redundancy" % short_name
        if method == "POST":
            return self.app.post(url, data={
                'n_answers': n_answers,
            }, follow_redirects=True)
        else:
            return self.app.get(url, follow_redirects=True)

    def task_settings_priority(self, method="POST", short_name='sampleapp',
                                 task_ids="1", priority_0=0.0):
        """Helper function to modify task redundancy"""
        url = "/project/%s/tasks/priority" % short_name
        if method == "POST":
            return self.app.post(url, data={
                'task_ids': task_ids,
                'priority_0': priority_0
            }, follow_redirects=True)
        else:
            return self.app.get(url, follow_redirects=True)

    def delete_project(self, method="POST", short_name="sampleapp"):
        """Helper function to delete a project"""
        if method == "POST":
            return self.app.post("/project/%s/delete" % short_name,
                                 follow_redirects=True)
        else:
            return self.app.get("/project/%s/delete" % short_name,
                                follow_redirects=True)

    def update_project(self,
                       method="POST", short_name="sampleapp", id=1,
                       new_name="Sample Project",
                       new_short_name="sampleapp",
                       new_description="Description",
                       new_allow_anonymous_contributors=False,
                       new_category_id=1,
                       new_long_description="Long desc",
                       new_sched="random",
                       new_webhook='http://server.com',
                       new_protect=False,
                       new_password=None,
                       new_product='abc',
                       new_subproduct='def',
                       new_kpi=0.5,
                       new_input_data_class='L4 - public',
                       new_output_data_class='L4 - public'):
        """Helper function to update a project"""
        payload = dict(id=id,
                       name=new_name,
                       short_name=new_short_name,
                       description=new_description,
                       allow_anonymous_contributors=new_allow_anonymous_contributors,
                       category_id=new_category_id,
                       long_description=new_long_description,
                       sched=new_sched,
                       webhook=new_webhook,
                       protect=new_protect,
                       password=new_password,
                       product=new_product,
                       subproduct=new_subproduct,
                       kpi=new_kpi,
                       input_data_class=new_input_data_class,
                       output_data_class=new_output_data_class)

        if method == "POST":
            return self.app.post("/project/%s/update" % short_name,
                                 data=payload, follow_redirects=True)
        else:
            return self.app.get("/project/%s/update" % short_name,
                                follow_redirects=True)


    def check_cookie(self, response, name):
        # Checks for existence of a cookie and verifies the value of it
        cookies = response.headers.getlist('Set-Cookie')
        for cookie in cookies:
            c_key, c_value = list(parse_cookie(cookie).items())[0]
            if c_key == name:
                return c_value
        # Cookie not found
        return False
