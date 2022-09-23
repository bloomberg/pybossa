from test import Test
from pybossa.cache import task_browse_helpers


class TestTaskBrowseHelpers(Test):

    def test_get_field_filters(self):
        filter1 = [["fruit", "contains", "orange"]]
        result1 = task_browse_helpers._get_field_filters(filter1)

        filter2 = '[["fruit", "contains", "orange"]]'
        result2 = task_browse_helpers._get_field_filters(filter2)
        assert type(result1) is list
        assert type(result2) is list
        assert result1 == result2
