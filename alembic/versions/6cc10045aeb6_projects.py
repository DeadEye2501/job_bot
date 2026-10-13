"""projects

Revision ID: 6cc10045aeb6
Revises: c4d7e2a915b3
Create Date: 2026-10-13 00:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '6cc10045aeb6'
down_revision: Union[str, Sequence[str], None] = 'c4d7e2a915b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'profile_project',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('profile_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('url', sa.String(), nullable=True),
        sa.Column('about', sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.ForeignKeyConstraint(['profile_id'], ['profile.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'profile_project_skills',
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('skill_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['profile_project.id']),
        sa.ForeignKeyConstraint(['skill_id'], ['profile_skills.id']),
        sa.PrimaryKeyConstraint('project_id', 'skill_id'),
    )


def downgrade() -> None:
    op.drop_table('profile_project_skills')
    op.drop_table('profile_project')
