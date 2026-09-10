import json

from test import db, with_context, with_context_settings
from test.factories import ProjectFactory, UserFactory
from test.helper import web
from pybossa.repositories import ProjectRepository

project_repo = ProjectRepository(db)


class TestEnrichment(web.Helper):

    @with_context_settings(ENRICHMENT_TYPES={'<type>': ['subtype']})
    def test_get_enrichment_config_uses_html_safe_json(self):
        owner = UserFactory.create(subadmin=True)
        enrichments = [{'in_field_name': '<enrichment-field>'}]
        project = ProjectFactory.create(owner=owner,
                                        info={'enrichments': enrichments})
        url = '/project/%s/enrichment?api_key=%s' % (project.short_name,
                                                     owner.api_key)

        res = self.app.get(url)

        assert res.status_code == 200, res
        assert b'var enrich_data = [{' in res.data
        assert b'\\u003cenrichment-field\\u003e' in res.data
        assert b'var enrichment_types = {"\\u003ctype\\u003e":' in res.data
        assert b'<enrichment-field>' not in res.data
        assert b'<type>' not in res.data

        data = json.loads(self.app_get_json(url).data)
        assert data['enrichments'] == enrichments

    @with_context
    def test_post_enirchment_config(self):
        project = ProjectFactory.create(published=True)
        url = '/project/%s/enrichment?api_key=%s' % (project.short_name, project.owner.api_key)
        res = self.app_get_json(url)
        data = json.loads(res.data)
        assert res.status_code == 200 and 'enrichments' in data, res
        
        csrf = data['csrf']
        enrich_data = {
            'enrich_data': {
                'in_field_name': 'A',
                'task_state': 'e',
                'type': 'fun',
                'sub_type': 'picnic',
                'out_field_name': 'enrich_A'                
            }
        }
        res = self.app.post(url, content_type='application/json',
                            data=json.dumps(enrich_data),
                            headers={'X-CSRFToken': csrf})
        data = json.loads(res.data)
        assert res.status_code == 200 and \
            data['flash'] == 'Success! Project data enrichment updated', res

        project = project_repo.get(project.id)
        updated_enrichments = project.info['enrichments']
        assert enrich_data['enrich_data'] == updated_enrichments, 'Updated enrichment do not match'
