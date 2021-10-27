import json

from test import db, with_context
from test.factories import ProjectFactory
from test.helper import web
from pybossa.repositories import ProjectRepository

project_repo = ProjectRepository(db)


class TestAnnotations(web.Helper):

    @with_context
    def test_post_annotation_config(self):
        annotation_config = {
            "sampling_script": "ddddd",
            "sampling_method": "RANDOM",
            "dataset_description": "aaaaa",
            "provider": "CONTINGENT_WORKER",
            "restrictions_and_permissioning": "bbbbb"
        }

        project = ProjectFactory.create(published=True)
        url = '/project/%s/annotconfig?api_key=%s' % (project.short_name, project.owner.api_key)
        res = self.app_get_json(url)
        data = json.loads(res.data)
        assert res.status_code == 200
        assert all([ak in data['form'].keys() for ak in annotation_config.keys()]), res

        csrf = data['csrf']
        res = self.app.post(url, content_type='application/json',
                            data=json.dumps(annotation_config),
                            headers={'X-CSRFToken': csrf})
        data = json.loads(res.data)
        assert res.status_code == 200 and \
            data['flash'] == 'Project annotation configurations updated', res

        project = project_repo.get(project.id)
        updated_annotation_config = project.info['annotation_config']
        assert annotation_config == updated_annotation_config, 'Updated annotation configurations do not match'
