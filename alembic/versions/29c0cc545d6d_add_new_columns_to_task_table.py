"""add new columns to task table

Revision ID: 29c0cc545d6d
Revises: 4893d060429b
Create Date: 2021-05-06 15:06:46.892934

"""

# revision identifiers, used by Alembic.
revision = '29c0cc545d6d'
down_revision = '4893d060429b'
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column('task', sa.Column('worker_filter', JSONB))
    op.add_column('task', sa.Column('worker_pref', JSONB))


def downgrade():
    op.drop_column('task', 'worker_filter')
    op.drop_column('task', 'worker_pref')