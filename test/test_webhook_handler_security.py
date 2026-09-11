import ast
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock


PYBOSSA_ROOT = Path(__file__).resolve().parents[1]
PROJECTS_VIEW = PYBOSSA_ROOT / 'pybossa/view/projects.py'


class AbortRequest(Exception):

    def __init__(self, status_code):
        self.status_code = status_code


class AccessDenied(Exception):
    pass


def load_webhook_handler():
    tree = ast.parse(PROJECTS_VIEW.read_text(encoding='utf-8'))
    handler = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == 'webhook_handler'
    )
    handler.decorator_list = []

    project = SimpleNamespace(id=10, webhook='https://receiver.test')
    repository = MagicMock()
    repository.filter_by.return_value = []
    webhook_queue = MagicMock()
    authorization = MagicMock()
    password_check = MagicMock(return_value=None)
    webhook_model = object()
    webhook_job = object()

    def abort(status_code):
        raise AbortRequest(status_code)

    namespace = {
        'Webhook': webhook_model,
        '_check_if_redirect_to_password': password_check,
        'abort': abort,
        'ensure_authorized_to': authorization,
        'json': json,
        'pro_features': lambda: {'webhooks_enabled': True},
        'project_by_shortname': lambda short_name: (project, None, None),
        'request': SimpleNamespace(method='POST', args={}),
        'webhook': webhook_job,
        'webhook_queue': webhook_queue,
        'webhook_repo': repository,
    }
    module = ast.fix_missing_locations(ast.Module(body=[handler], type_ignores=[]))
    exec(compile(module, str(PROJECTS_VIEW), 'exec'), namespace)
    return namespace['webhook_handler'], SimpleNamespace(
        authorization=authorization,
        password_check=password_check,
        project=project,
        repository=repository,
        webhook_job=webhook_job,
        webhook_model=webhook_model,
        webhook_queue=webhook_queue,
    )


def webhook_record(identifier=22, project_id=10):
    record = SimpleNamespace(
        id=identifier,
        payload={'project_id': project_id},
        project_id=project_id,
    )
    record.dictize = MagicMock(return_value={
        'id': identifier,
        'payload': record.payload,
        'project_id': project_id,
    })
    return record


class TestWebhookHandlerSecurity(unittest.TestCase):

    def test_post_authorizes_before_loading_webhook(self):
        handler, dependencies = load_webhook_handler()
        dependencies.authorization.side_effect = AccessDenied
        dependencies.repository.get.return_value = webhook_record()
        dependencies.repository.get_by.return_value = webhook_record()

        with self.assertRaises(AccessDenied):
            handler('owned-project', oid=22)

        dependencies.authorization.assert_called_once_with(
            'read', dependencies.webhook_model,
            project_id=dependencies.project.id
        )
        dependencies.repository.get.assert_not_called()
        dependencies.repository.get_by.assert_not_called()
        dependencies.webhook_queue.enqueue.assert_not_called()

    def test_post_checks_project_password_before_loading_webhook(self):
        handler, dependencies = load_webhook_handler()
        password_response = object()
        dependencies.password_check.return_value = password_response
        dependencies.repository.get.return_value = webhook_record()
        dependencies.repository.get_by.return_value = webhook_record()

        response = handler('owned-project', oid=22)

        self.assertIs(response, password_response)
        dependencies.repository.get.assert_not_called()
        dependencies.repository.get_by.assert_not_called()
        dependencies.webhook_queue.enqueue.assert_not_called()

    def test_post_lookup_is_scoped_to_url_project(self):
        handler, dependencies = load_webhook_handler()
        foreign_webhook = webhook_record(project_id=99)
        dependencies.repository.get.return_value = foreign_webhook
        dependencies.repository.get_by.return_value = None

        with self.assertRaises(AbortRequest) as error:
            handler('owned-project', oid=foreign_webhook.id)

        self.assertEqual(404, error.exception.status_code)
        dependencies.repository.get_by.assert_called_once_with(
            id=foreign_webhook.id, project_id=dependencies.project.id
        )
        dependencies.repository.get.assert_not_called()
        dependencies.webhook_queue.enqueue.assert_not_called()


if __name__ == '__main__':
    unittest.main()
