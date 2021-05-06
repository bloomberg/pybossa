"""add worker_pref to task

Revision ID: 9483d60f9f4b
Revises: 17f20588b41e
Create Date: 2021-04-01 22:10:09.136811

"""

# revision identifiers, used by Alembic.
revision = '9483d60f9f4b'
down_revision = '17f20588b41e'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

def upgrade():
    op.add_column('task', sa.Column('worker_pref', JSONB))


def downgrade():
    op.drop_column('task', 'worker_pref')
