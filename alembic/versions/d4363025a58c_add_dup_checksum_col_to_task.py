"""add dup_checksum_col to task

Revision ID: d4363025a58c
Revises: c7d7de1f09f6
Create Date: 2024-11-27 20:22:48.450611

"""

# revision identifiers, used by Alembic.
revision = 'd4363025a58c'
down_revision = 'c7d7de1f09f6'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column('task', sa.Column('dup_checksum', sa.String, nullable=True))
    op.execute('COMMIT')
    op.execute('CREATE INDEX CONCURRENTLY IF NOT EXISTS task_project_id_dup_checksum ON task (project_id, dup_checksum);')

def downgrade():
    op.drop_column('task', 'dup_checksum')
    op.execute('COMMIT')
    op.execute('DROP INDEX CONCURRENTLY IF EXISTS task_project_id_dup_checksum;')
