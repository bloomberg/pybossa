import json
import unittest

from pybossa.user_pref import build_user_pref_filter, get_unique_user_preferences
from pybossa.util import get_user_pref_db_clause


class TestUserPrefQuery(unittest.TestCase):

    def test_returns_unique_preferences_as_unquoted_json(self):
        user_prefs = [
            {'languages': ['en'], 'locations': ['us']},
            {'languages': ['en', 'ru']}
        ]

        distinct_user_prefs = get_unique_user_preferences(user_prefs)

        self.assertEqual(
            distinct_user_prefs,
            {
                '{"languages": ["en"]}',
                '{"languages": ["ru"]}',
                '{"locations": ["us"]}'
            }
        )

    def test_returns_user_pref_as_bound_parameter(self):
        encoded_pref = json.dumps({'custom': ["reader's choice"]})

        clause, params = build_user_pref_filter({encoded_pref})

        self.assertEqual(
            clause,
            ' AND (lower(user_pref::text)::jsonb @> lower(:pref_0)::jsonb)'
        )
        self.assertEqual(params, {'pref_0': encoded_pref})
        self.assertNotIn(encoded_pref, clause)

    def test_task_user_preferences_are_bound(self):
        payload = "reader's choice' OR TRUE --"
        encoded_pref = json.dumps({'languages': [payload]}).lower()

        clause, params = get_user_pref_db_clause(
            {'languages': [payload]})

        self.assertIn('task.user_pref @> :user_pref_0', clause)
        self.assertNotIn("reader's choice", clause)
        self.assertNotIn('OR TRUE', clause)
        self.assertEqual(params, {'user_pref_0': encoded_pref})

    def test_assign_user_remains_a_caller_parameter(self):
        clause, params = get_user_pref_db_clause(
            {'languages': ['en']}, 'reader@example.com')

        self.assertIn('task.user_pref @> :assign_user', clause)
        self.assertNotIn('assign_user', params)


if __name__ == '__main__':
    unittest.main()
