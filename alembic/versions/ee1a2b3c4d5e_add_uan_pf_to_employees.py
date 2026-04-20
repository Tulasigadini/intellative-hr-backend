"""add uan_number and pf_number to employees

Revision ID: ee1a2b3c4d5e
Revises: dda6019d046b
Create Date: 2026-04-16 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'ee1a2b3c4d5e'
down_revision = 'dda6019d046b'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('employees', sa.Column('uan_number', sa.String(30), nullable=True))
    op.add_column('employees', sa.Column('pf_number', sa.String(30), nullable=True))


def downgrade() -> None:
    op.drop_column('employees', 'uan_number')
    op.drop_column('employees', 'pf_number')
