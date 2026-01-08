from collections import defaultdict
import json
import operator
import re
from sqlalchemy.sql import text
from werkzeug.exceptions import BadRequest
from pybossa.cache import memoize, ONE_DAY
from pybossa.core import db
from pybossa.util import (convert_est_to_utc,
    get_user_pref_db_clause, get_user_filter_db_clause, map_locations)
from flask import current_app
import pybossa.app_settings as app_settings
from functools import reduce

comparator_func = {
    "less_than": operator.lt,
    "<": operator.lt,
    "less_than_equal": operator.le,
    "<=": operator.le,
    "greater_than": operator.gt,
    ">": operator.gt,
    "greater_than_equal": operator.ge,
    ">=": operator.ge,
    "equal": operator.eq,
    "==": operator.eq,
    "not_equal": operator.ne,
    "!=": operator.ne,
}

users_emails_to_fullnames = {}

def get_task_filters(args):
    """
    build the WHERE part of the query using the filter parameters
    return the part of the WHERE clause and the dictionary of bound parameters
    """
    filters = ''
    params = {}
    args = args or {}

    if args.get('task_id'):
        params['task_id'] = args['task_id']
        filters += ' AND task.id = :task_id'
    if args.get('hide_completed') and args.get('hide_completed') is True:
        filters += " AND task.state='ongoing'"
    if args.get('pcomplete_from') is not None:
        params['pcomplete_from'] = args['pcomplete_from']
        filters += " AND (coalesce(ct, 0)/float4(task.n_answers)) >= :pcomplete_from"
    if args.get('pcomplete_to') is not None:
        params['pcomplete_to'] = args['pcomplete_to']
        filters += " AND LEAST(coalesce(ct, 0)/float4(task.n_answers), 1.0) <= :pcomplete_to"
    if args.get('priority_from') is not None:
        params['priority_from'] = args['priority_from']
        filters += " AND priority_0 >= :priority_from"
    if args.get('priority_to') is not None:
        params['priority_to'] = args['priority_to']
        filters += " AND priority_0 <= :priority_to"
    if args.get('created_from'):
        datestring = convert_est_to_utc(args['created_from']).isoformat()
        params['created_from'] = datestring
        filters += " AND task.created >= :created_from"
    if args.get('created_to'):
        datestring = convert_est_to_utc(args['created_to']).isoformat()
        params['created_to'] = datestring
        filters += " AND task.created <= :created_to"
    if args.get('assign_user'):
        params['assign_user'] = f"%{args['assign_user']}%"
        # url parameter must have %keyword% for partial match.
        filters += """
            AND EXISTS (
              SELECT 1
              FROM jsonb_array_elements_text(task.user_pref -> 'assign_user') elem
              WHERE elem ILIKE :assign_user
            )
        """
    if args.get('ftime_from'):
        datestring = convert_est_to_utc(args['ftime_from']).isoformat()
        params['ftime_from'] = datestring
        filters += " AND ft >= :ftime_from"
    if args.get('ftime_to'):
        datestring = convert_est_to_utc(args['ftime_to']).isoformat()
        params['ftime_to'] = datestring
        filters += " AND ft <= :ftime_to"
    if args.get('state'):
        params['state'] = args['state']
        filters += " AND state = :state"
    if 'gold_task' in args:
        params['calibration'] = args['gold_task']
        filters += " AND task.calibration = :calibration"

    if args.get('order_by'):
        args["order_by"] = args['order_by'].replace('lock_status', '(coalesce(ct, 0)/float4(task.n_answers))')
    if args.get('filter_by_field'):
        filter_query, filter_params = _get_task_info_filters(
            args['filter_by_field'])
        filters += filter_query
        params.update(**filter_params)
    if args.get('filter_by_upref'):
        user_pref = args['filter_by_upref']
        if user_pref['languages'] or user_pref['locations']:
            user_pref_db_clause = get_user_pref_db_clause(user_pref)
            filters += " AND ( {} )".format(user_pref_db_clause)

    # for regular user, only include tasks that user has worked on
    if args.get("allow_taskrun_edit"):
        filters += ''' AND EXISTS
        (SELECT 1 FROM task_run WHERE project_id=:project_id AND
        user_id=:user_id AND task_id=task.id)'''
        params["user_id"] = args.get('user_id')
    elif args.get("filter_by_wfilter_upref"):   # for task queue
        # task queue exclude completed tasks
        filters += " AND state!='completed'"
        # exclude tasks that the current worker has worked on before
        filters += ''' AND NOT EXISTS
        (SELECT 1 FROM task_run WHERE project_id=:project_id AND
        user_id=:user_id AND task_id=task.id)'''

        params["user_id"] = args.get('user_id')

        # include additional filters
        user_pref = args["filter_by_wfilter_upref"]["current_user_pref"]
        user_email = args["filter_by_wfilter_upref"]["current_user_email"]
        user_pref_db_clause = get_user_pref_db_clause(user_pref, user_email)
        filters += " AND ( {} )".format(user_pref_db_clause)
        params["assign_user"] = args["sql_params"]["assign_user"]

        user_profile = args["filter_by_wfilter_upref"]["current_user_profile"]
        user_filter_db_clause = get_user_filter_db_clause(user_profile)
        filters += " AND ( {} )".format(user_filter_db_clause)

    return filters, params


def _escape_like_param(string):
    string = string.replace('\\', '\\\\')
    string = string.replace('%', '\\%')
    string = string.replace('_', '\\_')
    return string


op_to_query = {
    'starts with': dict(
        query="COALESCE(task.info->>'{}', '') ilike :{} escape '\\'",
        value="{}%",
        escape=_escape_like_param),
    'contains': dict(
        query="COALESCE(task.info->>'{}', '') ilike :{} escape '\\'",
        value="%{}%",
        escape=_escape_like_param),
    'equals': dict(
        query="lower(COALESCE(task.info->>'{}', '')) = lower(:{})",
        value="{}",
        escape=lambda x: x)
}


def _get_task_info_filters(filter_args):
    params = {}
    grouped_filters = _reduce_filters(filter_args)
    ix = 0
    and_pieces = []
    for field_name, ops in grouped_filters.items():
        or_pieces = []
        for operator, field_value in ops:
            query, p_name, p_val = _get_or_piece(field_name, operator,
                                                 field_value, ix)
            or_pieces.append(query)
            params[p_name] = p_val
            ix += 1
        and_pieces.append('({})'.format(' OR '.join(or_pieces)))
    filter_query = ''.join(' AND {}'.format(piece) for piece in and_pieces)
    return filter_query, params


def _get_or_piece(field_name, operator, field_value, arg_index):
    if operator not in op_to_query:
        raise BadRequest("Invalid Operator")
    op = op_to_query[operator]
    param_name = 'filter_by_field_{}'.format(arg_index)
    param_value = (op['value'].format(op['escape'](field_value)))
    query_filter = op['query'].format(field_name, param_name)
    return query_filter, param_name, param_value


def _reduce_filters(filter_args):
    def reducer(acc, next_val):
        field_name, operator, field_value = next_val
        acc[field_name].append((operator, field_value))
        return acc
    return reduce(reducer, filter_args, defaultdict(list))


def is_valid_searchable_column(column_name):
    valid_str = r'[\w\-]{1,40}$'
    is_valid = re.match(valid_str, column_name, re.UNICODE)
    return is_valid


@memoize(ONE_DAY)
def get_searchable_columns(project_id):
    sql = text('''SELECT distinct jsonb_object_keys(info) AS col
                  FROM task
                  WHERE jsonb_typeof(info) = 'object'
                  AND project_id=:project_id;''')
    results = db.slave_session.execute(sql, dict(project_id=project_id))
    return sorted(
        row.col for row in results if is_valid_searchable_column(row.col))


allowed_fields = {
    'task_id': 'id',
    'priority': 'priority_0',
    'finish_time': 'ft',
    'pcomplete': '(coalesce(ct, 0)/float4(task.n_answers))',
    'created': 'task.created',
    'filter_by_field': 'filter_by_field',
    'lock_status': 'lock_status',
    'completed_by': 'completed_by',
    'assigned_users': 'assigned_users',
    'in_progress': 'in_progress'
}


def parse_tasks_browse_args(args):
    """
    Parse querystring arguments
    :param args: content of request.args
    :return: a dictionary of selected filters
    """
    parsed_args = dict()
    if args.get('task_id'):
        parsed_args['task_id'] = int(args['task_id'])
    if args.get('pcomplete_from') is not None:
        parsed_args['pcomplete_from'] = float(args['pcomplete_from']) / 100
    if args.get('pcomplete_to') is not None:
        parsed_args['pcomplete_to'] = float(args['pcomplete_to']) / 100
    if args.get('hide_completed'):
        parsed_args['hide_completed'] = args['hide_completed'].lower() == 'true'

    iso_string_format = '^\d{4}\-\d{2}\-\d{2}T\d{2}:\d{2}(:\d{2})?(\.\d+)?$'

    if args.get('created_from'):
        if re.match(iso_string_format, args['created_from']):
            parsed_args["created_from"] = args['created_from']
        else:
            raise ValueError('created_from date format error, value: {}'
                             .format(args['created_from']))
    if args.get('created_to'):
        if re.match(iso_string_format, args['created_to']):
            parsed_args["created_to"] = args['created_to']
        else:
            raise ValueError('created_to date format error, value: {}'
                             .format(args['created_to']))
    if args.get('ftime_from'):
        if re.match(iso_string_format, args['ftime_from']):
            parsed_args["ftime_from"] = args['ftime_from']
        else:
            raise ValueError('ftime_from date format error, value: %s'
                             .format(args['ftime_from']))
    if args.get('ftime_to'):
        if re.match(iso_string_format, args['ftime_to']):
            parsed_args["ftime_to"] = args['ftime_to']
        else:
            raise ValueError('ftime_to date format error, value: %s'
                             .format(args['ftime_to']))
    if args.get('assign_user') is not None:
        parsed_args["assign_user"] = args['assign_user']
    if args.get('priority_from') is not None:
        parsed_args['priority_from'] = float(args['priority_from'])
    if args.get('priority_to') is not None:
        parsed_args['priority_to'] = float(args['priority_to'])
    if args.get('display_columns') and type(args.get('display_columns')) == list:
        parsed_args['display_columns'] = args['display_columns']
    elif args.get('display_columns') and type(args.get('display_columns')) != list:
        parsed_args['display_columns'] = json.loads(args['display_columns'])
    if not isinstance(parsed_args.get('display_columns'), list):
        parsed_args['display_columns'] = ['task_id', 'priority', 'pcomplete',
                                          'created', 'finish_time', 'gold_task',
                                          'actions', 'lock_status']
    if 'display_info_columns' in args:
        display_info_columns = args['display_info_columns']

        if not isinstance(display_info_columns, list):
            display_info_columns = json.loads(display_info_columns)
        parsed_args['display_info_columns'] = display_info_columns

    # Parse order_by fields.
    order_by, parsed_args['order_by_dict'] = parse_tasks_browse_order_by_args(
        args.get('order_by'),
        parsed_args.get('display_info_columns', []))
    if order_by:
        parsed_args['order_by'] = order_by

    if args.get('filter_by_field'):
        parsed_args['filter_by_field'] = _get_field_filters(args['filter_by_field'])

    if args.get('filter_by_upref'):
        user_pref = json.loads(args['filter_by_upref'])
        validate_user_preferences(user_pref)
        parsed_args['filter_by_upref'] = user_pref

    if args.get('state'):
        if args['state'] not in ['ongoing', 'completed']:
            raise ValueError('invalid task state: %s'.format(args['state']))
        parsed_args['state'] = args['state']

    gold_task = args.get('gold_task')
    if gold_task and gold_task != 'All':
        if gold_task in ['0', '1']:
            parsed_args['gold_task'] = gold_task
        else:
            raise ValueError('invalid gold value')

    in_progress = args.get('in_progress')
    if in_progress and in_progress != 'All':
        if in_progress in ['Yes', 'No']:
            parsed_args['in_progress'] = in_progress
        else:
            raise ValueError("Invalid in progress value. Only 'Yes' and 'No' are supported")

    return parsed_args


def parse_tasks_browse_order_by_args(order_by, display_info_columns):
    order_by_result = None
    order_by_dict = dict()

    if order_by:
        # Convert dict {'task_id': 'asc'} to string "task_id asc".
        order_by = re.sub("[{}:'\"]", '', str(order_by)) if type(order_by).__name__ == 'dict' else order_by
        order_by_result = order_by.strip()

        # allowing custom user added task.info columns to be sortable
        allowed_sort_fields = allowed_fields.copy()
        allowed_sort_fields.update({col: "task.info->>'{}'".format(col) for col in display_info_columns})
        for clause in order_by.split(','):
            clause = clause.strip()
            order_by_field = clause.split(' ')
            if len(order_by_field) != 2 or order_by_field[0] not in allowed_sort_fields:
                raise ValueError('order_by value sent by the user is invalid: %s'.format(order_by))
            if order_by_field[0] in order_by_dict:
                raise ValueError('order_by field is duplicated: %s'.format(order_by))
            order_by_dict[order_by_field[0]] = order_by_field[1]

        # Update order_by value to use query format.
        for key, value in allowed_sort_fields.items():
            # Sort by single field: bi desc -> task.info->>'bi' desc
            order_by_result = re.sub(r'^' + key + ' ', value + ' ', order_by_result)
            # Sort by multiple fields: bi desc, companyId asc -> task.info->>'bi' desc, task.info->>'companyId' asc
            order_by_result = re.sub(r',\s{0,1}' + key + ' ', ', ' + value + ' ', order_by_result)

    return (order_by_result, order_by_dict)


def validate_user_preferences(user_pref):
    if not isinstance(user_pref, dict) or \
        not all(x in ['languages', 'locations'] for x in user_pref.keys()):
            raise ValueError('invalid user preference keys')

    valid_user_preferences = app_settings.upref_mdata.get_valid_user_preferences() \
        if app_settings.upref_mdata else {}
    valid_languages = valid_user_preferences.get('languages')
    valid_locations = valid_user_preferences.get('locations')


    lang = user_pref.get('languages')
    loc = user_pref.get('locations')

    if lang and valid_languages and not all(x in valid_languages for x in lang):
        raise ValueError('invalid languages user preference: {}'
                        .format(lang))

    if loc and valid_locations and not all(x in valid_locations for x in loc):
        raise ValueError('invalid locations user preference: {}'
                        .format(loc))

    user_pref['locations'] = map_locations(loc)['locations']


def _get_field_filters(filters):
    filters = filters if type(filters) is list else json.loads(filters)
    return [(name, operator, value)
            for name, operator, value in filters
            if value and is_valid_searchable_column(name)]


def user_meet_task_requirement(task_id, user_filter, user_profile):
    for field, filters in user_filter.items():
        if field not in user_profile or user_profile.get(field) is None:
            # if user profile does not have attribute, user does not qualify for the task
            return False
        user_data = user_profile.get(field) or 0

        # Convert user_data to float for numeric comparisons
        # if the field is not numeric, it will be compared as a string.
        try:
            user_data = float(user_data)
        except ValueError:
            # non numeric data to be compared as string
            pass

        # Validate operator and perform comparison
        if len(filters) < 2:
            current_app.logger.error("Validating worker filter failed for task %d on field %s, error: insufficient filter parameters", task_id, field)
            return False

        require = filters[0]
        op = filters[1]
        if op not in comparator_func:
            current_app.logger.error("Validating worker filter failed for task %d on field %s, error: invalid operator %s", task_id, field, op)
            return False

        try:
            if not comparator_func[op](user_data, require):
                return False
        except Exception as e:
            current_app.logger.exception(f"Validating worker filter failed for task {task_id} on field {field}, comparison failed")
            return False
    return True


def get_task_preference_score(task_pref, user_profile):
    score = 0
    for key, value in task_pref.items():
        user_data = user_profile.get(key) or 0
        try:
            user_data = float(user_data)
            score += value * user_data
        except ValueError as e:
            # TODO: when user profile is not number, we need another method to calculate score
            pass
    return score


def get_user_fullname_from_email(email_addr):
    # search user by email address in local
    # cache users_emails_to_fullnames first
    # look for user in db if not found in cache
    # with user not found in db, return their email address
    # that would be useful for correcting wrong email addresses.
    from pybossa.core import user_repo

    if email_addr in users_emails_to_fullnames:
        return users_emails_to_fullnames[email_addr]

    user_fullname = email_addr  # missing user info will replace fullname with their email address
    user = user_repo.get_by(email_addr=email_addr)
    if user:
        user_fullname = user.fullname
        users_emails_to_fullnames[email_addr] = user_fullname
    return user_fullname


def get_users_fullnames_from_emails(emails):
    # Given list of user emails as an input,
    # obtain user full names, sort and return.
    users_info = {}
    for email_addr in emails:
        user_fullname = get_user_fullname_from_email(email_addr)
        users_info[user_fullname] = email_addr
    sorted_users_info = dict(sorted(users_info.items()))
    return sorted_users_info
