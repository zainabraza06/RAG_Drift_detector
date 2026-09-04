"""Add heuristic root-cause diagnostics to drift events.

Revision ID: 0003_diagnostics
Revises: 0002_drift_events
Create Date: 2026-09-04 19:58:02.701360
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0003_diagnostics'
down_revision: str | None = '0002_drift_events'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('drift_events', schema=None) as batch_op:
        batch_op.add_column(sa.Column('diagnostics', sa.JSON(), nullable=True))



def downgrade() -> None:
    with op.batch_alter_table('drift_events', schema=None) as batch_op:
        batch_op.drop_column('diagnostics')

