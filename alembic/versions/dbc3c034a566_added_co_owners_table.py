"""added co owners table

Revision ID: dbc3c034a566
Revises: 52209719b79e
Create Date: 2017-10-02 09:06:54.856193

"""

# revision identifiers, used by Alembic.
revision = 'dbc3c034a566'
down_revision = '52209719b79e'


from alembic import op
import sqlalchemy as sa


def upgrade():
    op.create_table('project_coowner',
    sa.Column('project_id', sa.INTEGER(), nullable=False, primary_key=True),
    sa.Column('coowner_id', sa.INTEGER(), nullable=False, primary_key=True),
    )

    op.create_foreign_key(u'project_coowner_coowner_id_fkey', 'project_coowner',
                          'user', ['coowner_id'], ['id'], ondelete=u'CASCADE')
    op.create_foreign_key(u'project_coowner_project_id_fkey', 'project_coowner',
                          'project', ['project_id'], ['id'], ondelete=u'CASCADE')


def downgrade():
    op.drop_constraint(u'project_coowner_coowner_id_fkey', 'project_coowner', type_='foreignkey')
    op.drop_constraint(u'project_coowner_project_id_fkey', 'project_coowner', type_='foreignkey')
    op.drop_constraint('project_coowner_pkey', table_name='project_coowner', type='primary')

    op.drop_table('project_coowner')
