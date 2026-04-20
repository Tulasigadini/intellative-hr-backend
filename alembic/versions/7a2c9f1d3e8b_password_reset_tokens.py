"""password_reset_tokens

Revision ID: 7a2c9f1d3e8b
Revises: 6f3b8d961c6f
Create Date: 2026-04-15 10:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '7a2c9f1d3e8b'
down_revision: Union[str, None] = '6f3b8d961c6f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add password_reset_token and password_reset_expires to user_accounts
    # (safe: uses IF NOT EXISTS logic via try/except at app level, but we do it here)
    op.execute("""
        ALTER TABLE user_accounts
        ADD COLUMN IF NOT EXISTS password_reset_token VARCHAR(255),
        ADD COLUMN IF NOT EXISTS password_reset_expires TIMESTAMP WITH TIME ZONE;
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE user_accounts
        DROP COLUMN IF EXISTS password_reset_token,
        DROP COLUMN IF EXISTS password_reset_expires;
    """)
