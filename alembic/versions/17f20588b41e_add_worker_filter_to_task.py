"""add worker_filter to task

Revision ID: 17f20588b41e
Revises: 4893d060429b
Create Date: 2021-04-01 22:09:48.574950

"""

# revision identifiers, used by Alembic.
revision = '17f20588b41e'
down_revision = '4893d060429b'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

def upgrade():
    op.add_column('task', sa.Column('worker_filter', JSONB))


def downgrade():
    op.drop_column('task', 'worker_filter')
