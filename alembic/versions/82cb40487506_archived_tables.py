"""archived tables

Revision ID: 82cb40487506
Revises: ed775af5e086
Create Date: 2022-03-03 22:56:03.256489

"""

# revision identifiers, used by Alembic.
revision = '82cb40487506'
down_revision = 'ed775af5e086'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


def upgrade():
    op.create_table(
        'task_archived',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('created', sa.Text),
        sa.Column('project_id', sa.Integer),
        sa.Column('state', sa.Text),
        sa.Column('quorum', sa.Integer),
        sa.Column('calibration', sa.Integer),
        sa.Column('priority_0', sa.Float),
        sa.Column('info', JSONB),
        sa.Column('n_answers', sa.Integer),
        sa.Column('fav_user_ids', sa.ARRAY(sa.Integer)),
        sa.Column('exported', sa.Boolean),
        sa.Column('user_pref', JSONB),
        sa.Column('gold_answers', JSONB),
        sa.Column('expiration', sa.DateTime),
        sa.Column('worker_filter', JSONB),
        sa.Column('worker_pref', JSONB),
        sa.Column('updated', sa.DateTime, nullable=False)
    )

    op.create_table(
        'task_run_archived',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('created', sa.Text),
        sa.Column('project_id', sa.Integer),
        sa.Column('task_id', sa.Integer),
        sa.Column('user_id', sa.Integer),
        sa.Column('user_ip', sa.Text),
        sa.Column('finish_time', sa.Text),
        sa.Column('timeout', sa.Integer),
        sa.Column('calibration', sa.Integer),
        sa.Column('info', JSONB),
        sa.Column('gold_ans_status', sa.Unicode(length=20)),
        sa.Column('external_uid', sa.String),
        sa.Column('media_url', sa.String),
        sa.Column('updated', sa.DateTime, nullable=False)
    )

    op.create_table(
        'result_archived',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('created', sa.Text),
        sa.Column('project_id', sa.Integer),
        sa.Column('task_id', sa.Integer),
        sa.Column('task_run_ids', sa.ARRAY(sa.Integer)),
        sa.Column('last_version', sa.Boolean),
        sa.Column('info', JSONB),
        sa.Column('updated', sa.DateTime, nullable=False)
    )


def downgrade():
    op.drop_table('task_archived')
    op.drop_table('task_run_archived')
    op.drop_table('result_archived')
