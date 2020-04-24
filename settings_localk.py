# -*- coding: utf8 -*-
# This file is part of PyBossa.
#
# Copyright (C) 2013 SF Isle of Man Limited
#
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
from datetime import timedelta
from collections import OrderedDict
from os import environ

DEBUG = False

FORCE_HTTPS = True
HOST = '0.0.0.0'
PORT = 5000
SERVER_URL = '${server_url}'
# SERVER_TYPE = 'Public QA'
SERVER_TYPE = 'TEST'
DISPLAY_PLATFORM_IDENTIFIER = True

SECRET = '${secret}'
SECRET_KEY = '${secret_key}'

S3_UPLOAD_DIRECTORY = 'dev'
S3_BUCKET = 'bcs-outgoing'
S3_IMPORT_BUCKET = 'bb-import-tasks'

SQLALCHEMY_DATABASE_URI = 'postgresql://appdbuser:${database_password}@${database_endpoint}/prod_pybossa_db'

DATA_ACCESS_MESSAGE = 'Only certain categories of data may be labeled with this platform. Please review your data with the <a href="bbg://screens/POLY ID:3606434">Bloomberg Data Classification and Handling Standard</a> before uploading.'

CONTACT_ENABLE = ['all']
CONTACT_SUBJECT = 'GIGwork message for project {short_name} by {email}'
CONTACT_BODY = 'A GIGwork support request has been sent for the project: {project_name}.'

# Slave configuration for DB
# SQLALCHEMY_BINDS = {
#    'slave': 'postgresql://user:password@server/db'
# }

ITSDANGEROUSKEY = '${itsdangerouskey}'

# project configuration
BRAND = 'GIGwork'
TITLE = 'GIGwork'
LOGO = 'gigwork.png'
COPYRIGHT = 'Set Your Institution'
DESCRIPTION = 'Set the description in your config'
TERMSOFUSE = 'http://okfn.org/terms-of-use/'
DATAUSE = 'http://opendatacommons.org/licenses/by/'
# CONTACT_EMAIL = 'info@pybossa.com'
CONTACT_EMAIL = 'dtws@gigwork.net'
CONTACT_TWITTER = 'PyBossa'

# custom configuration
ADMIN_OP_USER_CREATION = True
ENABLE_TWO_FACTOR_AUTH = True
BYPASS_TWO_FACTOR_AUTH = ['ealbert12@bloomberg.net']

# Default number of projects per page
APPS_PER_PAGE = 40

# External Auth providers
# TWITTER_CONSUMER_KEY=''
# TWITTER_CONSUMER_SECRET=''
# FACEBOOK_APP_ID=''
# FACEBOOK_APP_SECRET=''
# GOOGLE_CLIENT_ID=''
# GOOGLE_CLIENT_SECRET=''

# Supported Languages

LOCALES = [('en', 'English'), ('es', u'Espa\xf1ol'),
           ('it', 'Italiano'), ('fr', u'Fran\xe7ais'),
           ('ja', u'\u65e5\u672c\u8a9e'), ('pt_BR', 'Brazilian Portuguese')]

# list of administrator emails to which error emails get sent
# ADMINS = ['me@sysadmin.org']

# CKAN URL for API calls
# CKAN_NAME = "Demo CKAN server"
# CKAN_URL = "http://demo.ckan.org"

# logging config
# Sentry configuration
# SENTRY_DSN=''
# set path to enable
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
    'root': {
        'level': 'DEBUG',
        'handlers': ['stdout'],
        'formatter': 'default'
    }
}

MAIL_SERVER = '${smtp_server}'
MAIL_USERNAME = '${smtp_username}'
MAIL_PASSWORD = '${smtp_password}'
MAIL_PORT = 587
MAIL_USE_TLS = True
MAIL_USE_SSL = False
MAIL_FAIL_SILENTLY = False
# 'Pybossa Support <info@pybossa.com>'
MAIL_DEFAULT_SENDER = 'GIGwork Support <dtws@gigwork.net>'
# MAIL_DEFAULT_SENDER = 'Gigwork Support <pbus1520@gmail.com>' #'Pybossa Support <info@pybossa.com>'

# Announcement messages
# Use any combination of the next type of messages: root, user, and app owners
# ANNOUNCEMENT = {'admin': 'Hello Admin! This is a test announcement.'}
# ANNOUNCEMENT = {'user': 'Please be aware that <a HREF="https://qa.gigwork.net/">https://qa.gigwork.net/</a> will be offline for database maintenance today, 1/12/2018 at 5:00PM EST. This maintenance should last for 60 minutes.'}
ANNOUNCEMENT_LEVELS = {
    'admin': {'display': 'Admin', 'level': 0},
    'owner': {'display': 'Project Creator', 'level': 10},
    'subadmin': {'display': 'Subadmin', 'level': 20},
    'user': {'display': 'User', 'level': 30}
}
ANNOUNCEMENT_LEVEL_OPTIONS = [
    {'text': v['display'], 'value': v['level']} for k, v in ANNOUNCEMENT_LEVELS.iteritems()
]

# Enforce Privacy Mode, by default is disabled
# This config variable will disable all related user pages except for admins
# Stats, top users, leaderboard, etc
# ENFORCE_PRIVACY = False
ENFORCE_PRIVACY = True


# Cache setup. By default it is enabled
# Redis Sentinel
# List of Sentinel servers (IP, port)
# REDIS_CACHE_ENABLED = True
# REDIS_SENTINEL = [('10.2.5.145', 26379)]
# REDIS_MASTER = 'mymaster'
# REDIS_DB = 0
# REDIS_KEYPREFIX = 'pybossa_cache'
# REDIS_MASTER_DNS = '${redis_master_dns}'
# REDIS_SLAVE_DNS = '${redis_slave_dns}'
# REDIS_PORT = 6379
# REDIS_SOCKET_TIMEOUT = 450
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
REDIS_SOCKET_TIMEOUT = 45
# REDIS_SLAVE_DNS = 'redis_master'
# REDIS_PORT = 6379
# REDIS_MASTER = 'mymaster'
# REDIS_DB = 0
# REDIS_PWD = environ.get('__REDIS_PWD')
# REDIS_KEYPREFIX = 'pybossa_cache'
# REDIS_SOCKET_TIMEOUT = 45

# Allowed upload extensions
ALLOWED_EXTENSIONS = ['js', 'css', 'png', 'jpg', 'jpeg', 'gif', 'zip']

# If you want to use the local uploader configure which folder
UPLOAD_METHOD = 'cloud'
UPLOAD_BUCKET = 'qa-gigwork-uploads'
UPLOAD_FOLDER = 'uploads'

# If you want to use Rackspace for uploads, configure it here
# RACKSPACE_USERNAME = 'username'
# RACKSPACE_API_KEY = 'apikey'
# RACKSPACE_REGION = 'ORD'

# Default number of users shown in the leaderboard
# LEADERBOARD = 20
# Default shown presenters
# PRESENTERS = ["basic", "image", "sound", "video", "map", "pdf"]
# Default Google Docs spreadsheet template tasks URLs
TEMPLATE_TASKS = {}

# Expiration time for password protected project cookies
PASSWD_COOKIE_TIMEOUT = 60 * 30

# Expiration time for account confirmation / password recovery links
ACCOUNT_LINK_EXPIRATION = 5 * 60 * 60

# Ratelimit configuration
# LIMIT = 300
# PER = 15 * 60
LIMIT = 600
PER = 5 * 60
RATE_LIMIT_BY_USER_ID = True

# Disable new account confirmation (via email)
ACCOUNT_CONFIRMATION_DISABLED = True

# Mailchimp API key
# MAILCHIMP_API_KEY = "your-key"
# MAILCHIMP_LIST_ID = "your-list-ID"

# Flickr API key and# FLICKR_API_KEY = 'your-key'
# FLICKR_SHARED_SECRET = 'your-secret'

# DROPBOX APP KEY
# DROPBOX_APP_KEY = 'your-key'

# Login settings
REMEMBER_COOKIE_NAME = 'gw_remember_token'

PERMANENT_SESSION_LIFETIME = timedelta(hours=4)
SESSION_REFRESH_EACH_REQUEST = True

# CORS resources configuration.
CORS_RESOURCES = {}

# RATE_LIMIT for admins to be regular RATE_LIMIT x 4
ADMIN_RATE_MULTIPLIER = 4

# Reference docs label and links to be included in email invite to new user/admin/subadmin
USER_MANUAL_LABEL = 'GIGwork user manual'
USER_MANUAL_URL = 'https://s3.amazonaws.com/cf-s3uploads/gigdocumentation/GIGworkWorkerManual.pdf'
ADMIN_MANUAL_LABEL = '{TEAM 770968768 <GO>}'
ADMIN_MANUAL_URL = 'https://cms.prod.bloomberg.com/team/pages/viewpage.action?pageId=770968768'
ALLOWED_S3_BUCKETS = ['cf-s3uploads', 'as-nrgfin', 'pr-funds', 'pr-law',
                      'pr-mortgage', 'pr-portfolio', 'glbl-localization', 'gd-fixedincome', 'gd-futures']
IS_QA = True
ENABLE_STRONG_PASSWORD = True
GA_ID = 'UA-102883085-1'
PRIVACY_POLICY_PAGE = 'https://www.bloomberg.com/notices/privacy/'
FAILED_JOBS_RETRIES = 0
AVAILABLE_IMPORTERS = ['localCSV']
SECURE_APP_ACCESS = True
SUPERUSER_WHITELIST_EMAILS = ['@bloomberg.net$',
                              '^dtws@gigwork.net$', '^deep.jch@gmail.com$']

# Default shown presenters
PRESENTERS = ["basic", "annex", "helper-components",
              "entity-tagging", "pointshoot-base", "relevancy"]
S3_PRESENTER_BUCKET = "presenter-templates"
S3_PRESENTERS = {
    "annex": "annex_presenter.html",
    "helper-components": "helper_components_presenter.html",
    "entity-tagging": "entity_tagging_presenter.html",
    "pointshoot-base": "pointshoot-base.html",
    "relevancy": "relevancy.html"
}
HISTORICAL_CONTRIBUTIONS_AS_CATEGORY = True
DEFAULT_SYNC_TARGET = 'https://gigwork.net'
PROJECT_URL = 'https://github.com/bloomberg/pybossa'

AVAILABLE_SCHEDULERS = [
    ('default', 'Default'),
    ('locked_scheduler', 'Locked'),
    ('user_pref_scheduler', 'User Preference Scheduler')
]

DISABLE_TASK_PRESENTER_EDITOR = False
SIGNATURE_SECRET = '${signature_secret}'
REDUNDANCY_UPDATE_EXPIRATION = 90

DISABLE_ANONYMOUS_ACCESS = True

'''BSSO_SETTINGS = {
    "strict": True,
    "debug": True,
    "sp": {
        "entityId": "${server_url}",
        "assertionConsumerService": {
            "url": "${server_url}/bloomberg/login",
            "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
        },
        "singleLogoutService": {
            "url": "${server_url}/login/callback",
            "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
        },
        "NameIDFormat": "urn:oasis:names:tc:SAML:2.0:nameid-format:transient"
    },
    "idp": {
        "entityId": "https://bssobeta.bloomberg.com",
        "singleSignOnService": {
            "url": "https://bssobeta.blpprofessional.com/idp/SSO.saml2",
            "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
        },
        "singleLogoutService": {
            "url": "https://bssobeta.blpprofessional.com/idp/SSO.saml2",
            "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
        },
        "x509cert": "MIIFcDCCA1igAwIBAgIGAWDc7XACMA0GCSqGSIb3DQEBDQUAMHkxCzAJBgNVBAYTAlVTMREwDwYDVQQIEwhOZXcgWW9yazERMA8GA1UEBxMITmV3IFlvcmsxFzAVBgNVBAoTDkJsb29tYmVyZyBMLlAuMQ0wCwYDVQQLEwRORElTMRwwGgYDVQQDExNic3NvYmxwcHJvZmVzc2lvbmFsMB4XDTE4MDEwOTIxNTcxNloXDTI4MDEwNzIxNTcxNloweTELMAkGA1UEBhMCVVMxETAPBgNVBAgTCE5ldyBZb3JrMREwDwYDVQQHEwhOZXcgWW9yazEXMBUGA1UEChMOQmxvb21iZXJnIEwuUC4xDTALBgNVBAsTBE5ESVMxHDAaBgNVBAMTE2Jzc29ibHBwcm9mZXNzaW9uYWwwggIiMA0GCSqGSIb3DQEBAQUAA4ICDwAwggIKAoICAQCmX1jsc8D/R7r/3hmbcoeUZAgDcG6Mofhj0q9LjCw3QKLLTQRHT9PWmULlwBg8nu9e9ywq26F6LRMVZWyqzFd2MqnzU7Tc4GNGOAEmukOAnXM24G0qtOV88fsCPVDurFuR8yYwiPhzgBoZGe14LVzJhBA/8XPTO0PYqV8o9yCtOJS/vG32THjgIuPROQKLNvHodk7Z+8dxYBLmlT5W2cjwUm7aa2KABmeAkCWVEeXf9I/10qa4ro8SRYulkljOnGuwIkmoUGe0SrttassPj5tvsYP/b/hY5mbIYbG9fh7QIHv6UWgQ6eGN//YzwmT5GvMzoFKYSt7h96uQzE3nN42LAfGVk9SMEca/R82dXRV9nhuUHV3WjFzpy0etlGTfH60krUUYobZYzMjsrVKeG3DxxVevkFwHMR1T4vtUsP+VytCrjdj2sU9uv2ulCkv7rrLg7c9wn27uTYmiypWLojUPc72EnQpnuEzIledYjseF0ABaFhPhB2P3gZFO1aLrW3XpaOfNOu8MgPqhVkxeEvKu5FnhgFJKz+s4lWji52u1BAjK04Y0zGUdgZQ0ev8aOknzSXzYawn0l7UWCxI+ETeomGajohv+kCjLjDRC56BntU+h/pG9otZtekHb4uUBxTZkEprjfj2dn22DJpGzsvzwW3oV2djDelZXVZ0ESYvxQQIDAQABMA0GCSqGSIb3DQEBDQUAA4ICAQB+0faMOyPRszxHl1pKFnl+msLBIZMiMX8mT/q4rfAt4LS8naO67JClDNh9RxGW8cZT2z++vAmJ53c6+6Ixc4Qjcsh145uOAl5hChnMyOZ2s9By/2qBd4y46EAsrjVnfLYR/qzOF7bvwm1cyoXSTUPeKCk2oxG1bmyIaDuiJH6Uz5fbkgavwo47F1d6I83QW2eZnYAfSua61LVEQsiuUe7M63bPvPEJ1+kOOIKKZac3Ewm/fbRcd3xBY5jXiu3EBcQPxLMdWiYlhl3BkxykM7/lFZAYJLGUJYXDd0eypaxUhD0rm3pEOaHM5FJBkb/KIUEbkwRwfr35fuonKfX2MZB+RGgIFZ8TJ4g8HPvOh7CxNotbDHsXNDsXrzKXcy8HlZUGlwhBM65yVePYNEuLu9toSXY6vCwYqCGt5uCFQ4jjA6PTf/K9uprwQyjyv6Tke3qHyeya7AbersLXY1MKEEXSVPFaaHmgOWx5RjnH4D35rlbTqK45ieU1jZAlyb6ZKE1dGG6L7oSjk6f539/6St0QAdGFfSRuKtzc9FBmMOmOZdFRIDK0wqV60UTQ+UGrvy9NIfkkeZnl7Ev9hTgTtUyBafo4tRGHoYh0M9+nTFLb3A4wbCvl84a9YOLeLX5BVaO2pXoIBO7Co6srrRDxqEWzwQbAiUdHT4ZqWfw7IKGZsQ=="
    },
    "security": {
        "authnRequestsSigned": False,
        "wantAssertionsSigned": True
    }
}'''


EXTERNAL_CONFIGURATIONS = OrderedDict([
    ('gigwork_poller', {
        'display': 'Response File Location (BCOS)',
        'fields': {
            'target_bucket': ('TextField', 'BCOS bucket', None)
        }
    })
])

EXTERNAL_CONFIGURATIONS_VUE = OrderedDict([
    ('gigwork_poller', {
        'display': 'Response File & Consensus Location (BCOS)',
        'fields': [{
            'type': 'TextField',
            'name': 'target_bucket'
        }]
    })
])

SQLALCHEMY_TRACK_MODIFICATIONS = False
# RQ Dashboard settings
RQ_POLL_INTERVAL = 2500
REDIS_HOST = REDIS_MASTER_DNS

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

ENRICHMENT_TYPES = {
    'OOTB': ['NLPNED', 'NLPLKP']
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


EXPORT_BUCKET = 'qa-gigwork-exports'
EXPORT_MAX_SIZE = 8 * 1024 * 1024
STALE_USERS_MONTHS = 3
EXTENDED_STALE_USERS_MONTHS = 9
EXTENDED_STALE_USERS_DOMAINS = ['bloomberg.net']
