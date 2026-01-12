from datetime import datetime, timedelta

from pybossa.task_creator_helper import get_task_expiration
from test import with_context


def are_almost_equal(date1, date2):
    c1 = date1 < date2 + timedelta(hours=1)
    c2 = date1 > date2 - timedelta(hours=1)
    return c1 and c2


def to_datetime(timestamp):
    return datetime.strptime(timestamp, '%Y-%m-%dT%H:%M:%S.%f')


class TestGetTaskExpirationDatetime(object):

    @with_context
    def test_current_expiration_is_before(self):
        now = datetime.utcnow()
        current_exp = now + timedelta(days=30)
        exp = get_task_expiration(current_exp, now)
        assert exp == current_exp

    @with_context
    def test_current_expiration_is_after_max(self):
        now = datetime.utcnow()
        current_exp = now + timedelta(days=400)
        exp = get_task_expiration(current_exp, now)
        assert are_almost_equal(exp, now + timedelta(days=365))

    @with_context
    def test_expiration_within_max(self):
        now = datetime.utcnow()
        current_exp = now + timedelta(days=90)
        exp = get_task_expiration(current_exp, now)
        assert are_almost_equal(exp, current_exp)

    @with_context
    def test_current_expiration_is_none(self):
        now = datetime.utcnow()
        exp = get_task_expiration(None, now)
        assert are_almost_equal(exp, now + timedelta(days=60))


class TestGetTaskExpirationString(object):

    @with_context
    def test_current_expiration_is_before(self):
        now = datetime.utcnow()
        current_exp = now + timedelta(days=30)
        exp = get_task_expiration(current_exp.isoformat(), now)
        assert to_datetime(exp) == current_exp

    @with_context
    def test_current_expiration_is_after_max(self):
        now = datetime.utcnow()
        current_exp = now + timedelta(days=400)
        exp = get_task_expiration(current_exp.isoformat(), now)
        assert are_almost_equal(
            to_datetime(exp), now + timedelta(days=365))

    @with_context
    def test_create_date_is_set(self):
        now = datetime.utcnow()
        current_exp = now + timedelta(days=30)
        exp = get_task_expiration(current_exp.isoformat(), now)
        assert to_datetime(exp) == current_exp
