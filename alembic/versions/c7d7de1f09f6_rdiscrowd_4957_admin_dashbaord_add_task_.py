"""RDISCROWD-4957 admin dashbaord-add task_crated_idx

Revision ID: c7d7de1f09f6
Revises: ed775af5e086
Create Date: 2022-03-16 11:14:18.737830

"""

# revision identifiers, used by Alembic.
revision = 'c7d7de1f09f6'
down_revision = 'ed775af5e086'

from alembic import op


def upgrade():
    op.execute('COMMIT')
    op.execute('CREATE INDEX CONCURRENTLY IF NOT EXISTS task_created_idx ON task (created);')


def downgrade():
    op.execute('COMMIT')
    op.execute('DROP INDEX CONCURRENTLY IF EXISTS task_created_idx;')
