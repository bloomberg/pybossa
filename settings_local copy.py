# -*- coding: utf8 -*-
# This file is part of PyBossa.
#
# Copyright (C) 2013 SF Isle of Man Limited
#
# PyBossa is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# PyBossa is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with PyBossa.  If not, see <http://www.gnu.org/licenses/>.
from collections import OrderedDict
from datetime import timedelta
from os import environ

DEBUG = True
FORCE_HTTPS = False

# webserver host and port
HOST = '0.0.0.0'
PORT = 5000
SERVER_TYPE = 'TEST'


SECRET = 'foobar'
SECRET_KEY = 'my-session-secret'

SQLALCHEMY_DATABASE_URI = 'postgresql://pybossa:tester@gig_postgres/pybossa'

# Slave configuration for DB
# SQLALCHEMY_BINDS = {
#    'slave': 'postgresql://user:password@server/db'
# }

ITSDANGEROUSKEY = 'its-dangerous-key'

# project configuration
BRAND = 'PyBossa'
TITLE = 'PyBossa'
LOGO = 'default_logo.svg'
COPYRIGHT = 'Set Your Institution'
DESCRIPTION = 'Set the description in your config'
TERMSOFUSE = 'http://okfn.org/terms-of-use/'
DATAUSE = 'http://opendatacommons.org/licenses/by/'
CONTACT_EMAIL = 'info@pybossa.com'
CONTACT_TWITTER = 'PyBossa'

# Default number of projects per page
## APPS_PER_PAGE = 20

# External Auth providers
# TWITTER_CONSUMER_KEY=''
# TWITTER_CONSUMER_SECRET=''
# FACEBOOK_APP_ID=''
# FACEBOOK_APP_SECRET=''
# GOOGLE_CLIENT_ID=''
# GOOGLE_CLIENT_SECRET=''

# Supported Languages
# NOTE: You need to create a symbolic link to the translations folder, otherwise
# this wont work.
# ln -s pybossa/themes/your-theme/translations pybossa/translations
#DEFAULT_LOCALE = 'en'
# LOCALES = [('en', 'English'), ('es', u'Español'),
#           ('it', 'Italiano'), ('fr', u'Français'),
#           ('ja', u'日本語'),('pt_BR','Brazilian Portuguese')]


# list of administrator emails to which error emails get sent
# ADMINS = ['me@sysadmin.org']

# CKAN URL for API calls
#CKAN_NAME = "Demo CKAN server"
#CKAN_URL = "http://demo.ckan.org"


# logging config
# Sentry configuration
# SENTRY_DSN=''
LOG_DICT_CONFIG = {
    'version': 1,
    'formatters': {
        'default': {
            'format': '%(name)s:%(levelname)s:[%(asctime)s] %(message)s [in %(pathname)s:%(lineno)d]',
        }
    },
    'handlers': {
        'stdout': {
            'class': 'logging.StreamHandler',
            'stream': 'ext://sys.stdout',
            'level': 'DEBUG',
            'formatter': 'default'
        }
    },
    'loggers': {
        'pybossa': {
            'level': 'DEBUG',
            'handlers': ['stdout'],
            'formatter': 'default'
        }
    }
}

# Mail setup
MAIL_SERVER = 'localhost'
MAIL_USERNAME = None
MAIL_PASSWORD = None
MAIL_PORT = 25
MAIL_FAIL_SILENTLY = False
MAIL_DEFAULT_SENDER = 'PyBossa Support <info@pybossa.com>'

# Announcement messages
# Use any combination of the next type of messages: root, user, and app owners
## ANNOUNCEMENT = {'admin': 'Root Message', 'user': 'User Message', 'owner': 'Owner Message'}

# Enforce Privacy Mode, by default is disabled
# This config variable will disable all related user pages except for admins
# Stats, top users, leaderboard, etc
ENFORCE_PRIVACY = False


# Cache setup. By default it is enabled
# Redis Sentinel
# List of Sentinel servers (IP, port)
REDIS_MASTER_DNS = 'redis_master'
REDIS_SLAVE_DNS = 'redis_master'
REDIS_PORT = 6379
REDIS_MASTER = 'mymaster'
REDIS_DB = 0
REDIS_PWD = environ.get('__REDIS_PWD')
REDIS_KEYPREFIX = 'pybossa_cache'
REDIS_SOCKET_TIMEOUT = 450

# Allowed upload extensions
ALLOWED_EXTENSIONS = ['js', 'css', 'png', 'jpg', 'jpeg', 'gif', 'zip']

# If you want to use the local uploader configure which folder
UPLOAD_METHOD = 'local'
UPLOAD_FOLDER = 'uploads'

# If you want to use Rackspace for uploads, configure it here
# RACKSPACE_USERNAME = 'username'
# RACKSPACE_API_KEY = 'apikey'
# RACKSPACE_REGION = 'ORD'

# Default number of users shown in the leaderboard
# LEADERBOARD = 20
# Default shown presenters
# PRESENTERS = ["basic", "image", "sound", "video", "map", "pdf"]
# S3_PRESENTER_BUCKET = "presenter-bucket"
# S3_PRESENTERS = {"presenter_name": "path/to/presenter.html"}

# Default Google Docs spreadsheet template tasks URLs
TEMPLATE_TASKS = {
    'image': "https://docs.google.com/spreadsheet/ccc?key=0AsNlt0WgPAHwdHFEN29mZUF0czJWMUhIejF6dWZXdkE&usp=sharing",
    'sound': "https://docs.google.com/spreadsheet/ccc?key=0AsNlt0WgPAHwdEczcWduOXRUb1JUc1VGMmJtc2xXaXc&usp=sharing",
    'video': "https://docs.google.com/spreadsheet/ccc?key=0AsNlt0WgPAHwdGZ2UGhxSTJjQl9YNVhfUVhGRUdoRWc&usp=sharing",
    'map': "https://docs.google.com/spreadsheet/ccc?key=0AsNlt0WgPAHwdGZnbjdwcnhKRVNlN1dGXy0tTnNWWXc&usp=sharing",
    'pdf': "https://docs.google.com/spreadsheet/ccc?key=0AsNlt0WgPAHwdEVVamc0R0hrcjlGdXRaUXlqRXlJMEE&usp=sharing"}

# Expiration time for password protected project cookies
PASSWD_COOKIE_TIMEOUT = 60 * 30

# Login settings
REMEMBER_COOKIE_NAME = 'gw_remember_token'
PERMANENT_SESSION_LIFETIME = timedelta(hours=100)

# Expiration time for account confirmation / password recovery links
ACCOUNT_LINK_EXPIRATION = 5 * 60 * 60

# Ratelimit configuration
# LIMIT = 300
# PER = 15 * 60

# Disable new account confirmation (via email)
ACCOUNT_CONFIRMATION_DISABLED = True

# Mailchimp API key
# MAILCHIMP_API_KEY = "your-key"
# MAILCHIMP_LIST_ID = "your-list-ID"

# Flickr API key and secret
# FLICKR_API_KEY = 'your-key'
# FLICKR_SHARED_SECRET = 'your-secret'

# Dropbox app key
# DROPBOX_APP_KEY = 'your-key'

# Send emails weekly update every
# WEEKLY_UPDATE_STATS = 'Sunday'

# Youtube API server key
# YOUTUBE_API_SERVER_KEY = 'your-key'

# Enable Server Sent Events
# WARNING: this will require to run PyBossa in async mode. Check the docs.
# WARNING: if you don't enable async when serving PyBossa, the server will lock
# WARNING: and it will not work. For this reason, it's disabled by default.
# SSE = False

# Add here any other ATOM feed that you want to get notified.
NEWS_URL = ['https://github.com/pybossa/enki/releases.atom',
            'https://github.com/pybossa/pybossa-client/releases.atom',
            'https://github.com/pybossa/pbs/releases.atom']

# Pro user features. False will make the feature available to all regular users,
# while True will make it available only to pro users
PRO_FEATURES = {
    'auditlog':              True,
    'webhooks':              True,
    'updated_exports':       True,
    'notify_blog_updates':   True,
    'project_weekly_report': True,
    'autoimporter':          True,
    'better_stats':          True
}

# Libsass style. You can use nested, expanded, compact and compressed
LIBSASS_STYLE = 'compressed'

# CORS resources configuration.
# WARNING: Only modify this if you know what you are doing. The below config
# are the defaults, allowing PYBOSSA to have full CORS api.
# For more options, check the Flask-Cors documentation: https://flask-cors.readthedocs.io/en/latest/
# CORS_RESOURCES = {r"/api/*": {"origins": "*",
#                               "allow_headers": ['Content-Type',
#                                                 'Authorization'],
#                               "methods": "*"
#                               }}

# Email notifications for background jobs.
# FAILED_JOBS_MAILS = 7
# FAILED_JOBS_RETRIES = 3

# Language to use stems, full text search, etc. from postgresql.
# FULLTEXTSEARCH_LANGUAGE = 'english'


# Use strict slashes at endpoints, by default True
# This will return a 404 if and endpoint does not have the api/endpoint/
# while if you configured as False, it will return the resource with and without the trailing /
# STRICT_SLASHES = True

# Use SSO on Disqus.com
# DISQUS_SECRET_KEY = 'secret-key'
# DISQUS_PUBLIC_KEY = 'public-key'

# Use Web Push Notifications
# ONESIGNAL_APP_ID = 'Your-app-id'
# ONESIGNAL_API_KEY = 'your-app-key'

# Enable two factor authentication
# ENABLE_TWO_FACTOR_AUTH = True

# Strong password policy for user accounts
# ENABLE_STRONG_PASSWORD = True

# Create new leaderboards based on info field keys from user
# LEADERBOARDS = ['foo', 'bar']

# AVAILABLE_IMPORTERS = ['localCSV']

# Unpublish inactive projects
# UNPUBLISH_PROJECTS = True

# Use this config variable to create valid URLs for your SPA
# SPA_SERVER_NAME = 'https://yourserver.com'

# LDAP
# LDAP_HOST = '127.0.0.1'
# LDAP_BASE_DN = 'ou=users,dc=scifabric,dc=com'
# LDAP_USERNAME = 'cn=yourusername,dc=scifabric,dc=com'
# LDAP_PASSWORD = 'yourpassword'
# LDAP_OBJECTS_DN = 'dn'
# LDAP_OPENLDAP = True
# Adapt it to your specific needs in your LDAP org
# LDAP_USER_OBJECT_FILTER = '(&(objectclass=inetOrgPerson)(cn=%s))'
# LDAP_USER_FILTER_FIELD = 'cn'
# LDAP_PYBOSSA_FIELDS = {'fullname': 'givenName',
#                        'name': 'uid',
#                        'email_addr': 'cn'}

# Flask profiler
# FLASK_PROFILER = {
#     "enabled": True,
#     "storage": {
#         "engine": "sqlite"
#     },
#     "basicAuth":{
#         "enabled": True,
#         "username": "admin",
#         "password": "admin"
#     },
#     "ignore": [
# 	    "^/static/.*"
# 	]
# }

# disallow api access without login using api key that can bypass two factor authentication
# SECURE_APP_ACCESS = True

# allow admin access to particular email addresses or to specific email accounts
# SUPERUSER_WHITELIST_EMAILS = ['@mycompany.com$', '^admin@mycompany.com$', '^subadmin@mycompany.com$']
SQLALCHEMY_TRACK_MODIFICATIONS = False
AVAILABLE_IMPORTERS = ['localCSV']

PRODUCTS_SUBPRODUCTS = {
    'BGOV': ['Government Affairs', 'Government Contracting'],
    'BLAW': ['BBNA Tax', 'BLAW Acquisition', 'Caselaw', 'Citator', 'Dockets', 'Legal Data Analysis',
             'Primary Legal Content', 'Secondary Legal Content', 'Data Coordinator', 'Data Technology'],
    'BLAW Managers / Support': ['Managers & Support'],
    'Commodities & Energy': ['BNEF', 'Commodities'],
    'Companies': ['Entity Management', 'Company Filings', 'MiFID II'],
    'Economics': ['Economics'],
    'Equity': ['BICS', 'Earnings Estimates', 'ESG', 'EVTS / Transcripts', 'Fundamentals',
               'M&A / Equity Capital Markets', 'Private Equity', 'Dividend Forecasting-BDVD', 'Corporate Actions',
               'Bloomberg Intelligence Support', 'Industry Experts', 'BRES', 'Deep Estimates', 'IR/Management',
               'Supply Chain'],
    'Event Bus': ['Event Bus'],
    'Exchanges': ['Market Structure', 'Business Analyst', 'Business Manager', 'CABM Managers / Support',
                  'Project Manager'],
    'F&O/FX/MSG Mining': ['F&O', 'FX', 'MSG Mining'],
    'Fixed Income': ['CAST', 'Municipals', 'Mortgages', "Corporates, Govt's & MMKT", 'Loans',
                     'Muni FA', 'Ratings & Curves'],
    'Funds & Holdings': ['Funds', 'Hedge Funds', 'Investor Profiles', 'Ownership', 'Portfolios',
                         'Mandates', 'Separately Managed Accounts'],
    'GD Managers / Support': ['CABM Managers / Support', 'Admin', 'Business Development',
                              'Business Support', 'Managers & Support', 'Managers BS', 'Managers BZ', 'Managers DM',
                              'Managers DT', 'Managers LS', 'Managers NO', 'Managers PW', 'Managers TL', 'Training',
                              'Vendor Support'],
    'GDA': ['GDA'],
    'GEI': ['GEI'],
    'GIS/Maps': ['GIS/Maps'],
    'Green Markets': ['Green Markets'],
    'ID Services': ['LEI', 'Regulation', 'BBGID'],
    'Indices': ['3rd Party Indices', 'Bloomberg Indices'],
    'KYC': ['Entity Exchange'],
    'Lifestyles': ['Lifestyles'],
    'Localization': ['Localization'],
    'News Support': ['Automation', 'Indexing', 'News Acquisition', 'News Extraction', 'Web Content'],
    'Non-GD': ['Enterprise', 'News', 'Sales'],
    'PORT': ['PORT QA'],
    'Pricing': ['Account Management', 'CABM Managers / Support', 'Content Specialist',
                'Pricing - Placeholder', 'Product Development'],
    'Product Development': ['DATA <GO>'],
    'Profiles': ['Profiles'],
    'Regulation': ['Regulation'],
    'Research': ['Account Management', 'CABM Managers / Support', 'Content Specialist',
                 'Entitlement Specialist', 'Product Development'],
    'Search Bar': ['Search Bar'],
    'Technology': ['Automated Quality Control', 'Business Intelligence', 'Data Engineering', 'Data Governance',
                   'Data Pipelining', 'Data Sciences', 'EMEA TechOps', 'GDTO Managers / Support', 'Integration & Support',
                   'NY TechOps', 'Operational Analysis', 'Project Management Office', 'Technology Advocates'],
    'Third Party': ['CABM Managers / Support', 'Third Party'],
    'Training': ['GDTP']
}

# Wizard Steps
# 'step_name': {
#
#        'title': 'Step 1', [Title that will be displayed on the UI]
#        'icon': 'fa fa-pencil', [Icon class that will be use to be displayed on the UI]
#        'href': {'url_for': 'project.new' [Url that will be redirected to when user click at step]
#                 'args': ['short_name', 'published'] [arguments for url_for function possible values are "short_name" and "published" or empty]
#                }
#        'done_checks': {'always': False, 'and': [''], 'or': []},  [if True Step is going to be filled]
#        'enable_checks': {'always': True, 'and': [''], 'or': []}, [if True Step border are going to be blue]
#        'visible_checks': {'and': ['not_project_exist'], 'or': []}, [if True Step is going to be visible]
#        [Checks:
#           The 'always' key must be used to keep a static value {always: True/False}, it means no its not dependent on
#           any logic.
#
#           All 'check-names' keys represent specific checks functions that can be found on the wizard.py class as check_options.
#               each step can have combinations of checks in {'and':[], 'or': []} and the final result will be a bolean condition
#               equivalent to"any('or') or all(and)"
#         ]
#    }

WIZARD_STEPS = OrderedDict([
    ('new_project', {
        'title': 'Project Creation',
        'icon': 'fa fa-pencil',
        'href': {'url_for': 'project.new',
                 'args': ['']},
        'done_checks': {'always': False},
        'enable_checks': {'always': True},
        'visible_checks': {'and': ['not_project_exist'], 'or': []},
    }),
    ('project_details', {
        'title': 'Project Details',
        'icon': 'fa fa-pencil',
        'href': {'url_for': 'project.update',
                 'args': ['short_name']},
        'done_checks': {'always': True},
        'enable_checks': {'always': True},
        'visible_checks': {'and': ['project_exist'], 'or': []}
    }),
    ('task_imports', {
        'title': 'Import Tasks',
        'icon': 'fa fa-file',
        'href': {'url_for': 'project.import_task',
                 'args': ['short_name']},
        'done_checks': {'and': ['tasks_amount'], 'or': []},
        'enable_checks': {'and': ['project_exist'], 'or': []},
        'visible_checks': {'always': True}
    }),
    ('task_presenter', {
        'title': 'Task Presenter',
        'icon': 'fa fa-pencil',
        'href': {'url_for': 'project.task_presenter_editor',
                 'args': ['short_name']},
        'done_checks': {'and': ['task_presenter', 'task_guidelines'], 'or': []},
        'enable_checks': {'and': ['tasks_amount'], 'or': ['task_presenter', 'task_guidelines', 'project_publish']},
        'visible_checks': {'always': True}
    }),
    ('task_settings', {
        'title': 'Settings',
        'icon': 'fa fa-cogs',
        'href': {'url_for': 'project.summary',
                 'args': ['short_name']},
        'done_checks': {'and': ['task_presenter', 'tasks_amount'], 'or': ['project_publish']},
        'enable_checks': {'and': ['task_presenter', 'tasks_amount'], 'or': ['project_publish']},
        'visible_checks': {'always': True}
    }),
    ('publish', {
        'title': 'Publish',
        'icon': 'fa fa-check',
        'href': {'url_for': 'project.publish',
                 'args': ['short_name']},
        'done_checks': {'always': False},
        'enable_checks': {'and': ['task_presenter', 'tasks_amount'], 'or': ['project_publish']},
        'visible_checks': {'and': ['not_project_publish'], 'or': ['not_project_exist']},
    }),
    ('published', {
        'title': 'Published',
        'icon': 'fa fa-check',
        'href': {'url_for': 'project.publish',
                 'args': ['short_name']},
        'done_checks': {'always': True},
        'enable_checks': {'always': True},
        'visible_checks': {'and': ['project_publish'], 'or': []},
    })]
)
