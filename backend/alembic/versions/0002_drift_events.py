"""Add drift events: stored statistical assessments per run.

Revision ID: 0002_drift_events
Revises: 0001_initial_schema
Create Date: 2026-09-04 14:03:08.858220
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0002_drift_events'
down_revision: str | None = '0001_initial_schema'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('drift_events',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('event_uuid', sa.String(length=36), nullable=False),
    sa.Column('run_id', sa.Integer(), nullable=False),
    sa.Column('verdict', sa.String(length=20), nullable=False),
    sa.Column('summary', sa.Text(), nullable=False),
    sa.Column('query_count', sa.Integer(), nullable=False),
    sa.Column('golden_set_fingerprint', sa.String(length=32), nullable=False),
    sa.Column('baseline_run_ids', sa.JSON(), nullable=False),
    sa.Column('comparisons', sa.JSON(), nullable=False),
    sa.Column('hit_rate', sa.JSON(), nullable=True),
    sa.Column('warnings', sa.JSON(), nullable=False),
    sa.Column('config', sa.JSON(), nullable=False),
    sa.Column('detected_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['run_id'], ['evaluation_runs.id'], name=op.f('fk_drift_events_run_id_evaluation_runs'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_drift_events')),
    sa.UniqueConstraint('run_id', name='uq_drift_events_run')
    )
    with op.batch_alter_table('drift_events', schema=None) as batch_op:
        batch_op.create_index('ix_drift_events_detected_at', ['detected_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_drift_events_event_uuid'), ['event_uuid'], unique=True)
        batch_op.create_index('ix_drift_events_verdict_detected', ['verdict', 'detected_at'], unique=False)



def downgrade() -> None:
    with op.batch_alter_table('drift_events', schema=None) as batch_op:
        batch_op.drop_index('ix_drift_events_verdict_detected')
        batch_op.drop_index(batch_op.f('ix_drift_events_event_uuid'))
        batch_op.drop_index('ix_drift_events_detected_at')

    op.drop_table('drift_events')
