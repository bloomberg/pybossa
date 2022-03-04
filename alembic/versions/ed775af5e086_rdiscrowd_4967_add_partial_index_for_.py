"""RDISCROWD-4967 add partial index for task table

Revision ID: ed775af5e086
Revises: 29c0cc545d6d
Create Date: 2022-02-28 15:01:53.582867

"""

# revision identifiers, used by Alembic.
revision = 'ed775af5e086'
down_revision = '29c0cc545d6d'

from alembic import op


def upgrade():
    # Workaround of "CREATE INDEX CONCURRENTLY cannot run inside a transaction block" exception
    op.execute('COMMIT')

    op.create_index('task_state_calibration_exported_idx', 'task',
                    ['id'],
                    postgresql_where="(state = 'completed'::text OR calibration = 1) AND exported = false",
                    postgresql_concurrently=True
                    )

    op.create_index('task_state_enrich_idx', 'task',
                    ['id'],
                    postgresql_where="state = 'enrich'::text",
                    postgresql_concurrently=True
                    )


def downgrade():
    op.execute('COMMIT')
    op.execute('DROP INDEX CONCURRENTLY IF EXISTS task_state_calibration_exported_idx')
    op.execute('DROP INDEX CONCURRENTLY IF EXISTS task_state_enrich_idx')
