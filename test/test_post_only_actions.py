# -*- coding: utf8 -*-
"""Focused source-level regression for CSRF-protected UI mutations.

Run directly without the DB-backed test package bootstrap:

    python3 pybossa/test/test_post_only_actions.py
"""

import ast
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).parents[1]
APP = ROOT / 'pybossa'
THEME = APP / 'themes' / 'default'

ROUTE_FUNCTIONS = {
    APP / 'view' / 'admin.py': (
        'add_admin',
        'del_admin',
        'add_subadmin',
        'del_subadmin',
        'enable_user',
        'disable_user',
    ),
    APP / 'view' / 'projects.py': (
        'make_random_task_gold',
        'add_coowner',
        'del_coowner',
    ),
    APP / 'view' / 'account.py': (
        'start_export',
        'delete',
    ),
}

TEMPLATE_ACTIONS = {
    THEME / 'templates' / 'admin' / '_helpers.html': {
        'admin.add_admin': 2,
        'admin.del_admin': 2,
        'admin.add_subadmin': 1,
        'admin.del_subadmin': 1,
        'admin.enable_user': 1,
        'admin.disable_user': 1,
    },
    THEME / 'templates' / 'projects' / '_helpers.html': {
        'project.make_random_task_gold': 2,
        'project.add_coowner': 1,
        'project.del_coowner': 1,
    },
    THEME / 'templates' / 'account' / 'public_profile.html': {
        'account.start_export': 1,
        'account.delete': 1,
    },
    THEME / 'static' / 'src' / 'components' / 'setting' / 'quiz_setting.vue': {
        'make-random-gold': 1,
    },
}


class PostOnlyActionTest(unittest.TestCase):

    def test_mutating_routes_are_post_only(self):
        for path, function_names in ROUTE_FUNCTIONS.items():
            functions = {
                node.name: node
                for node in ast.walk(ast.parse(path.read_text()))
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
            for function_name in function_names:
                route = next(
                    decorator for decorator in functions[function_name].decorator_list
                    if isinstance(decorator, ast.Call) and
                    isinstance(decorator.func, ast.Attribute) and
                    decorator.func.attr == 'route'
                )
                methods = next(
                    keyword.value for keyword in route.keywords
                    if keyword.arg == 'methods'
                )
                self.assertEqual(ast.literal_eval(methods), ['POST'])

    def test_all_ui_actions_are_token_bearing_post_forms(self):
        for path, actions in TEMPLATE_ACTIONS.items():
            source = path.read_text()
            for action, count in actions.items():
                self.assertEqual(source.count(action), count, (path, action))
                if path.suffix == '.vue':
                    self.assertIn('method="post"', source)
                    self.assertIn('name="csrf_token"', source)
                    self.assertIn(':value="csrfToken"', source)
                    self.assertNotIn(':href="`/project/${getProjectName()}/make-random-gold`"', source)
                    continue

                pattern = re.compile(
                    r'<form\b(?:(?!</form>).)*action="[^\n]*' +
                    re.escape(action) +
                    r'(?:(?!</form>).)*name="csrf_token"(?:(?!</form>).)*</form>',
                    re.DOTALL,
                )
                self.assertEqual(len(pattern.findall(source)), count, (path, action))
                self.assertNotRegex(
                    source,
                    r'href="[^\n]*' + re.escape(action),
                )

    def test_dead_webpush_get_caller_is_removed(self):
        source = (THEME / 'templates' / 'projects' / 'update.html').read_text()
        self.assertNotIn('/webpush', source)
        self.assertNotIn('id="webpush"', source)


if __name__ == '__main__':
    unittest.main()
