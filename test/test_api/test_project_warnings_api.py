# -*- coding: utf8 -*-
# This file is part of PYBOSSA.
#
# Copyright (C) 2025 Scifabric LTD.
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
"""
Unit tests for project warnings in API responses.

Tests that warnings are dynamically generated in the API layer and included
in JSON responses but are never persisted to the database.

Test Coverage:
==============

1. **Core API Warning Functionality**:
   - POST with multiple warnings (tests API warning inclusion) when appropriate
   - PUT operations with warning-triggering changes when appropriate

2. **Warning Response Structure**:
   - Warnings included in top-level 'warnings' field in JSON response
   - Warning messages formatted correctly
   - Response structure integrity maintained

3. **Database Persistence**:
   - Warnings never persisted to database (dynamic generation)
   - Database state consistent across operations
   - Project data saved correctly without warnings in database
   - No side effects on database from warnings

4. **API Layer Integration**:
   - APIBase class processing preserves warnings
   - _customize_response_dict() method works correctly
   - Other API endpoints unaffected by warnings (warnings only for POST/PUT)

5. **Edge Cases and Error Handling**:
   - Empty warning lists
   - Response processing chain integrity

6. **Method-Level Unit Tests**:
   - _customize_response_dict() with various inputs
   - Handling of missing fields
   - Dynamic warning generation

The warning system now works as follows:
1. Repository layer validates products/subproducts (no warning generation)
2. API layer dynamically generates warnings during response formatting
3. Warnings included in JSON response but never persisted to database
4. Always reflects current configuration without stale data
"""

import json
from unittest.mock import patch
from test import with_context
from test.factories import UserFactory, CategoryFactory, ProjectFactory
from test.test_api import TestAPI
from pybossa.core import project_repo


class TestProjectWarningsAPI(TestAPI):
    """Test Project API warnings functionality."""

    DEPRECATED_PRODUCT_SUBPRODUCT_WARNING_MESSAGE = ('Combination of selected Product and Subproduct has been deprecated '
                'and will be removed in future. Refer to GIGwork documentation for '
                'taxonomy updates.')

    @with_context
    def test_post_valid_product_with_deprecated_subproduct_shows_warning(self):
        """Test POST with valid product but deprecated subproduct shows warning."""
        test_config = {
            'DEPRECATED_PRODUCTS_SUBPRODUCTS': {
                'Deprecated Product': ['Any Subproduct'],
                'Valid Product': ['Deprecated Subproduct']
            },
            'PRODUCTS_SUBPRODUCTS': {
                'Deprecated Product': ['Any Subproduct'],
                'Valid Product': ['Deprecated Subproduct', 'Valid Subproduct']
            }
        }

        with patch.dict(self.flask_app.config, test_config):
            CategoryFactory.create()
            user = UserFactory.create()

            project_data = {
                'name': 'Test Project',
                'short_name': 'test_valid_prod_deprecated_sub',
                'description': 'Test valid product with deprecated subproduct',
                'long_description': 'Test valid product with deprecated subproduct',
                'password': 'hello',
                'info': {
                    'product': 'Valid Product',
                    'subproduct': 'Deprecated Subproduct',
                    'data_classification': {
                        'input_data': 'L4 - public',
                        'output_data': 'L4 - public'
                    },
                    'kpi': 0.5
                }
            }

            url = '/api/project?api_key=%s' % user.api_key
            res = self.app.post(url, data=json.dumps(project_data))

            assert res.status_code == 200, res.data
            response_data = json.loads(res.data)

            # Verify warning is present when using valid product with deprecated subproduct
            assert 'warnings' in response_data
            assert len(response_data['warnings']) == 1
            assert self.DEPRECATED_PRODUCT_SUBPRODUCT_WARNING_MESSAGE == response_data['warnings'][0]

            # Verify project was saved to database
            project = project_repo.get(response_data['id'])
            assert project is not None
            assert project.info['product'] == 'Valid Product'
            assert project.info['subproduct'] == 'Deprecated Subproduct'

            # Verify no warnings in database
            assert 'warnings' not in project.info

    @with_context
    def test_post_valid_product_with_valid_subproduct_no_warning(self):
        """Test POST with same valid product but valid subproduct shows no warning."""
        test_config = {
            'DEPRECATED_PRODUCTS_SUBPRODUCTS': {
                'Deprecated Product': ['Any Subproduct'],
                'Valid Product': ['Deprecated Subproduct']
            },
            'PRODUCTS_SUBPRODUCTS': {
                'Deprecated Product': ['Any Subproduct'],
                'Valid Product': ['Deprecated Subproduct', 'Valid Subproduct']
            }
        }

        with patch.dict(self.flask_app.config, test_config):
            CategoryFactory.create()
            user = UserFactory.create()

            project_data = {
                'name': 'Test Project',
                'short_name': 'test_valid_prod_valid_sub',
                'description': 'Test valid product with valid subproduct',
                'long_description': 'Test valid product with valid subproduct',
                'password': 'hello',
                'info': {
                    'product': 'Valid Product',
                    'subproduct': 'Valid Subproduct',
                    'data_classification': {
                        'input_data': 'L4 - public',
                        'output_data': 'L4 - public'
                    },
                    'kpi': 0.5
                }
            }

            url = '/api/project?api_key=%s' % user.api_key
            res = self.app.post(url, data=json.dumps(project_data))

            assert res.status_code == 200, res.data
            response_data = json.loads(res.data)

            # Verify no warning when using valid product with valid subproduct
            assert 'warnings' not in response_data

            # Verify project was saved to database
            project = project_repo.get(response_data['id'])
            assert project is not None
            assert project.info['product'] == 'Valid Product'
            assert project.info['subproduct'] == 'Valid Subproduct'

            # Verify no warnings in database
            assert 'warnings' not in project.info

    @with_context
    def test_post_deprecated_product_with_subproduct_shows_warning(self):
        """Test POST with deprecated product and its subproduct shows warning."""
        test_config = {
            'DEPRECATED_PRODUCTS_SUBPRODUCTS': {
                'Deprecated Product': ['Subproduct A', 'Subproduct B'],
                'Valid Product': ['Deprecated Subproduct']
            },
            'PRODUCTS_SUBPRODUCTS': {
                'Deprecated Product': ['Subproduct A', 'Subproduct B'],
                'Valid Product': ['Deprecated Subproduct', 'Valid Subproduct']
            }
        }

        with patch.dict(self.flask_app.config, test_config):
            CategoryFactory.create()
            user = UserFactory.create()

            project_data = {
                'name': 'Test Project',
                'short_name': 'test_deprecated_prod_with_sub',
                'description': 'Test deprecated product with subproduct',
                'long_description': 'Test deprecated product with subproduct',
                'password': 'hello',
                'info': {
                    'product': 'Deprecated Product',
                    'subproduct': 'Subproduct A',
                    'data_classification': {
                        'input_data': 'L4 - public',
                        'output_data': 'L4 - public'
                    },
                    'kpi': 0.5
                }
            }

            url = '/api/project?api_key=%s' % user.api_key
            res = self.app.post(url, data=json.dumps(project_data))

            assert res.status_code == 200, res.data
            response_data = json.loads(res.data)

            # Verify warning is present when using deprecated product
            assert 'warnings' in response_data
            assert len(response_data['warnings']) == 1
            assert self.DEPRECATED_PRODUCT_SUBPRODUCT_WARNING_MESSAGE == response_data['warnings'][0]

            # Verify project was saved to database
            project = project_repo.get(response_data['id'])
            assert project is not None
            assert project.info['product'] == 'Deprecated Product'
            assert project.info['subproduct'] == 'Subproduct A'

            # Verify no warnings in database
            assert 'warnings' not in project.info

    @with_context
    def test_put_project_with_valid_products_subproducts_has_no_warnings(self):
        """Test PUT project with valid product and valid subproduct has no warnings."""
        test_config = {
            'DEPRECATED_PRODUCTS_SUBPRODUCTS': {
                'Old Product': ['Old Subproduct']
            },
            'PRODUCTS_SUBPRODUCTS': {
                'Valid Product': ['Valid Subproduct', 'Another Valid Subproduct'],
                'Old Product': ['Old Subproduct']
            }
        }

        with patch.dict(self.flask_app.config, test_config):
            user = UserFactory.create()
            project = ProjectFactory.create(
                owner=user,
                short_name='test_put_valid',
                info={
                    'product': 'Valid Product',
                    'subproduct': 'Valid Subproduct',
                    'data_classification': {
                        'input_data': 'L4 - public',
                        'output_data': 'L4 - public'
                    },
                    'kpi': 0.5
                }
            )

            # Update project to use a different valid subproduct under same valid product
            update_data = {
                'name': 'Updated Name',
                'description': 'Updated Description',
                'info': {
                    'product': 'Valid Product',
                    'subproduct': 'Another Valid Subproduct',
                    'data_classification': {
                        'input_data': 'L4 - public',
                        'output_data': 'L4 - public'
                    },
                    'kpi': 0.7
                }
            }

            url = '/api/project/%s?api_key=%s' % (project.id, user.api_key)
            res = self.app.put(url, data=json.dumps(update_data))

            assert res.status_code == 200, res.data
            response_data = json.loads(res.data)

            # Verify no warnings in response when using valid product and valid subproduct
            assert 'warnings' not in response_data

            # Verify project was updated in database
            updated_project = project_repo.get(project.id)
            assert updated_project.name == 'Updated Name'
            assert updated_project.info['product'] == 'Valid Product'
            assert updated_project.info['subproduct'] == 'Another Valid Subproduct'
            assert updated_project.info['kpi'] == 0.7

            # Verify no warnings in database
            assert 'warnings' not in updated_project.info

    @with_context
    def test_put_valid_product_with_deprecated_subproduct_shows_warning(self):
        """Test PUT with valid product but deprecated subproduct shows warning."""
        test_config = {
            'DEPRECATED_PRODUCTS_SUBPRODUCTS': {
                'Deprecated Product': ['Any Subproduct'],
                'Valid Product': ['Deprecated Subproduct']
            },
            'PRODUCTS_SUBPRODUCTS': {
                'Deprecated Product': ['Any Subproduct'],
                'Valid Product': ['Deprecated Subproduct', 'Valid Subproduct']
            }
        }

        with patch.dict(self.flask_app.config, test_config):
            user = UserFactory.create()
            project = ProjectFactory.create(
                owner=user,
                short_name='test_put_valid_prod_deprecated_sub',
                info={
                    'product': 'Valid Product',
                    'subproduct': 'Valid Subproduct',
                    'data_classification': {
                        'input_data': 'L4 - public',
                        'output_data': 'L4 - public'
                    },
                    'kpi': 0.5
                }
            )

            # Update to use deprecated subproduct
            update_data = {
                'info': {
                    'product': 'Valid Product',
                    'subproduct': 'Deprecated Subproduct',
                    'data_classification': {
                        'input_data': 'L4 - public',
                        'output_data': 'L4 - public'
                    },
                    'kpi': 0.5
                }
            }

            url = '/api/project/%s?api_key=%s' % (project.id, user.api_key)
            res = self.app.put(url, data=json.dumps(update_data))

            assert res.status_code == 200, res.data
            response_data = json.loads(res.data)

            # Verify warning is present when using valid product with deprecated subproduct
            assert 'warnings' in response_data
            assert len(response_data['warnings']) == 1
            assert self.DEPRECATED_PRODUCT_SUBPRODUCT_WARNING_MESSAGE == response_data['warnings'][0]

            # Verify project was updated in database
            updated_project = project_repo.get(project.id)
            assert updated_project.info['product'] == 'Valid Product'
            assert updated_project.info['subproduct'] == 'Deprecated Subproduct'

            # Verify no warnings in database
            assert 'warnings' not in updated_project.info


    @with_context
    def test_put_deprecated_product_with_subproduct_shows_warning(self):
        """Test PUT with deprecated product and its subproduct shows warning."""
        test_config = {
            'DEPRECATED_PRODUCTS_SUBPRODUCTS': {
                'Deprecated Product': ['Subproduct A', 'Subproduct B'],
                'Valid Product': ['Deprecated Subproduct']
            },
            'PRODUCTS_SUBPRODUCTS': {
                'Deprecated Product': ['Subproduct A', 'Subproduct B'],
                'Valid Product': ['Deprecated Subproduct', 'Valid Subproduct']
            }
        }

        with patch.dict(self.flask_app.config, test_config):
            user = UserFactory.create()
            project = ProjectFactory.create(
                owner=user,
                short_name='test_put_deprecated_prod_with_sub',
                info={
                    'product': 'Valid Product',
                    'subproduct': 'Valid Subproduct',
                    'data_classification': {
                        'input_data': 'L4 - public',
                        'output_data': 'L4 - public'
                    },
                    'kpi': 0.5
                }
            )

            # Update to use deprecated product
            update_data = {
                'info': {
                    'product': 'Deprecated Product',
                    'subproduct': 'Subproduct A',
                    'data_classification': {
                        'input_data': 'L4 - public',
                        'output_data': 'L4 - public'
                    },
                    'kpi': 0.5
                }
            }

            url = '/api/project/%s?api_key=%s' % (project.id, user.api_key)
            res = self.app.put(url, data=json.dumps(update_data))

            assert res.status_code == 200, res.data
            response_data = json.loads(res.data)

            # Verify warning is present when using deprecated product
            assert 'warnings' in response_data
            assert len(response_data['warnings']) == 1
            assert self.DEPRECATED_PRODUCT_SUBPRODUCT_WARNING_MESSAGE == response_data['warnings'][0]

            # Verify project was updated in database
            updated_project = project_repo.get(project.id)
            assert updated_project.info['product'] == 'Deprecated Product'
            assert updated_project.info['subproduct'] == 'Subproduct A'

            # Verify no warnings in database
            assert 'warnings' not in updated_project.info

    @with_context
    def test_project_warnings_not_persisted_after_multiple_operations(self):
        """Test that warnings are consistently not persisted across multiple API operations."""
        test_config = {
            'DEPRECATED_PRODUCTS_SUBPRODUCTS': {
                'Old Product': ['Valid Subproduct'],
                'Valid Product': ['Old Subproduct']
            },
            'PRODUCTS_SUBPRODUCTS': {
                'Old Product': ['Valid Subproduct'],
                'Valid Product': ['Old Subproduct', 'Valid Subproduct']
            }
        }

        with patch.dict(self.flask_app.config, test_config):
            CategoryFactory.create()
            user = UserFactory.create()

            # 1. POST with deprecated product
            project_data = {
                'name': 'Test Project',
                'short_name': 'test_persistence',
                'description': 'Test project for warning persistence',
                'long_description': 'Test project for warning persistence',
                'password': 'hello',
                'info': {
                    'product': 'Old Product',
                    'subproduct': 'Valid Subproduct',
                    'data_classification': {
                        'input_data': 'L4 - public',
                        'output_data': 'L4 - public'
                    },
                    'kpi': 0.5
                }
            }

            url = '/api/project?api_key=%s' % user.api_key
            res = self.app.post(url, data=json.dumps(project_data))
            assert res.status_code == 200
            post_response = json.loads(res.data)
            project_id = post_response['id']

            # Verify POST response has warnings
            assert 'warnings' in post_response
            assert len(post_response['warnings']) >= 1

            # Check database after POST
            project = project_repo.get(project_id)
            assert 'warnings' not in project.info

            # 2. PUT with renamed subproduct
            update_data = {
                'info': {
                    'product': 'Valid Product',
                    'subproduct': 'Old Subproduct',
                    'data_classification': {
                        'input_data': 'L4 - public',
                        'output_data': 'L4 - public'
                    },
                    'kpi': 0.8
                }
            }

            url = '/api/project/%s?api_key=%s' % (project_id, user.api_key)
            res = self.app.put(url, data=json.dumps(update_data))
            assert res.status_code == 200
            put_response = json.loads(res.data)

            # Verify PUT response has different warnings
            assert 'warnings' in put_response
            assert self.DEPRECATED_PRODUCT_SUBPRODUCT_WARNING_MESSAGE in put_response['warnings']

            # Check database after PUT
            project = project_repo.get(project_id)
            assert 'warnings' not in project.info
            assert project.info['kpi'] == 0.8

            # 3. GET project (should have no warnings)
            url = '/api/project/%s?api_key=%s' % (project_id, user.api_key)
            res = self.app.get(url)
            assert res.status_code == 200
            get_response = json.loads(res.data)

            # Verify GET response has no warnings
            assert 'warnings' not in get_response

    @with_context
    def test_customize_response_dict_handles_empty_warnings(self):
        """Test _customize_response_dict method handles projects with no warnings."""
        from pybossa.api.project import ProjectAPI

        test_config = {
            'PRODUCTS_SUBPRODUCTS': {
                'Old Product': ['Valid Subproduct'],
                'Valid Product': ['Old Subproduct', 'Valid Subproduct']
            },
            'DEPRECATED_PRODUCTS_SUBPRODUCTS': {
                'Old Product': ['Valid Subproduct']
            }
        }

        with patch.dict(self.flask_app.config, test_config):
            api = ProjectAPI()

            # Test with no warnings
            response_dict = {
                'id': 1,
                'name': 'Test Project',
                'info': {
                    'product': 'Valid Product',
                    'subproduct': 'Valid Subproduct'
                }
            }

            result = api._customize_response_dict(response_dict.copy())

            # Should return unchanged if no warnings
            assert 'warnings' not in result
            assert result == response_dict

    @with_context
    def test_customize_response_dict_handles_warnings_dynamically(self):
        """Test _customize_response_dict method generates warnings dynamically."""
        from pybossa.api.project import ProjectAPI

        test_config = {
            'PRODUCTS_SUBPRODUCTS': {
                'Old Product': ['Valid Subproduct'],
                'Valid Product': ['Old Subproduct', 'Valid Subproduct']
            },
            'DEPRECATED_PRODUCTS_SUBPRODUCTS': {
                'Old Product': ['Valid Subproduct']
            }
        }

        with patch.dict(self.flask_app.config, test_config):
            api = ProjectAPI()

            # Test with deprecated product (should generate warnings dynamically)
            response_dict = {
                'id': 1,
                'name': 'Test Project',
                'info': {
                    'product': 'Old Product',
                    'subproduct': 'Valid Subproduct'
                }
            }

            result = api._customize_response_dict(response_dict.copy())

            # Should generate warnings dynamically
            assert 'warnings' in result
            assert len(result['warnings']) == 1
            assert self.DEPRECATED_PRODUCT_SUBPRODUCT_WARNING_MESSAGE == result['warnings'][0]

            # Other fields should remain unchanged
            assert result['id'] == 1
            assert result['name'] == 'Test Project'
            assert result['info']['product'] == 'Old Product'
            assert result['info']['subproduct'] == 'Valid Subproduct'

    @with_context
    def test_customize_response_dict_handles_missing_info_field(self):
        """Test _customize_response_dict method handles response without info field."""
        from pybossa.api.project import ProjectAPI

        api = ProjectAPI()

        # Test with no info field
        response_dict = {
            'id': 1,
            'name': 'Test Project'
        }

        result = api._customize_response_dict(response_dict.copy())

        # Should return unchanged
        assert result == response_dict
        assert 'warnings' not in result


    @with_context
    def test_warnings_do_not_affect_other_api_responses(self):
        """Test that warnings functionality doesn't interfere with other API responses."""
        test_config = {
            'DEPRECATED_PRODUCTS_SUBPRODUCTS': {
                'Old Product': ['Valid Subproduct']
            },
            'PRODUCTS_SUBPRODUCTS': {
                'Old Product': ['Valid Subproduct']
            }
        }

        with patch.dict(self.flask_app.config, test_config):
            user = UserFactory.create()

            # Create a project with warnings
            project = ProjectFactory.create(
                owner=user,
                short_name='test_other_apis',
                info={
                    'product': 'Old Product',
                    'subproduct': 'Valid Subproduct',
                    'data_classification': {
                        'input_data': 'L4 - public',
                        'output_data': 'L4 - public'
                    },
                    'kpi': 0.5
                }
            )

            # Test GET /api/project (list projects) - should not have warnings
            url = '/api/project?api_key=%s' % user.api_key
            res = self.app.get(url)
            assert res.status_code == 200
            projects_list = json.loads(res.data)

            for project_data in projects_list:
                assert 'warnings' not in project_data
                if 'info' in project_data:
                    assert '_warnings' not in project_data['info']

            # Test GET /api/project/:id - should not have warnings
            url = '/api/project/%s?api_key=%s' % (project.id, user.api_key)
            res = self.app.get(url)
            assert res.status_code == 200
            project_data = json.loads(res.data)
            assert 'warnings' not in project_data

    @with_context
    def test_warnings_survive_api_base_response_processing(self):
        """Test that warnings survive the full API response processing chain."""
        test_config = {
            'DEPRECATED_PRODUCTS_SUBPRODUCTS': {
                'Old Product': ['Valid Subproduct']
            },
            'PRODUCTS_SUBPRODUCTS': {
                'Old Product': ['Valid Subproduct']
            }
        }

        with patch.dict(self.flask_app.config, test_config):
            CategoryFactory.create()
            user = UserFactory.create()

            project_data = {
                'name': 'Test API Processing',
                'short_name': 'test_api_processing',
                'description': 'Test full API processing chain',
                'long_description': 'Test full API processing chain',
                'password': 'hello',
                'info': {
                    'product': 'Old Product',
                    'subproduct': 'Valid Subproduct',
                    'data_classification': {
                        'input_data': 'L4 - public',
                        'output_data': 'L4 - public'
                    },
                    'kpi': 0.5,
                    'extra_field': 'extra_value'  # Additional field to test info processing
                }
            }

            # POST with warnings
            url = '/api/project?api_key=%s' % user.api_key
            res = self.app.post(url, data=json.dumps(project_data))

            assert res.status_code == 200, res.data
            response_data = json.loads(res.data)

            # Verify full response structure integrity
            expected_fields = [
                'id', 'name', 'short_name', 'description', 'long_description',
                'info', 'owner_id', 'created', 'updated', 'warnings'
            ]

            for field in expected_fields:
                assert field in response_data, f"Missing field: {field}"

            # Verify warnings are properly formatted
            assert isinstance(response_data['warnings'], list)
            assert len(response_data['warnings']) == 1
            assert self.DEPRECATED_PRODUCT_SUBPRODUCT_WARNING_MESSAGE == response_data['warnings'][0]

            # Verify info field integrity
            assert response_data['info']['product'] == 'Old Product'
            assert response_data['info']['subproduct'] == 'Valid Subproduct'
            assert response_data['info']['extra_field'] == 'extra_value'

            # Verify other fields are preserved
            assert response_data['name'] == project_data['name']
            assert response_data['short_name'] == project_data['short_name']

            # Verify database integrity
            project = project_repo.get(response_data['id'])
            assert project.name == project_data['name']
            assert project.info['product'] == 'Old Product'
            assert project.info['extra_field'] == 'extra_value'
            assert 'warnings' not in project.info

