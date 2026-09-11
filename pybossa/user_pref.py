import json


def get_unique_user_preferences(user_prefs):
    distinct_user_prefs = set()
    for user_pref in user_prefs:
        for key, values in user_pref.items():
            if isinstance(values, list):
                for value in values:
                    distinct_user_prefs.add(json.dumps({key: [value]}))
    return distinct_user_prefs


def build_user_pref_filter(distinct_task_prefs):
    clauses = []
    params = {}
    for index, user_pref in enumerate(sorted(distinct_task_prefs)):
        param_name = 'pref_{}'.format(index)
        clauses.append(
            'lower(user_pref::text)::jsonb @> lower(:{})::jsonb'.format(param_name)
        )
        params[param_name] = user_pref
    return ' AND ({})'.format(' OR '.join(clauses)), params
