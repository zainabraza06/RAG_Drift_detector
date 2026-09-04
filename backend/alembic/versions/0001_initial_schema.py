"""Initial schema: golden sets and evaluation run history.

Revision ID: 0001_initial_schema
Revises: 
Create Date: 2026-09-04 08:51:00.730371
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0001_initial_schema'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('golden_sets',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('version', sa.String(length=50), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('fingerprint', sa.String(length=32), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('source', sa.String(length=20), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_golden_sets')),
    sa.UniqueConstraint('name', 'version', name='uq_golden_sets_name_version')
    )
    with op.batch_alter_table('golden_sets', schema=None) as batch_op:
        batch_op.create_index('ix_golden_sets_fingerprint', ['fingerprint'], unique=False)
        batch_op.create_index(batch_op.f('ix_golden_sets_name'), ['name'], unique=False)

    op.create_table('evaluation_runs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('run_uuid', sa.String(length=36), nullable=False),
    sa.Column('golden_set_id', sa.Integer(), nullable=True),
    sa.Column('golden_set_name', sa.String(length=200), nullable=False),
    sa.Column('golden_set_version', sa.String(length=50), nullable=False),
    sa.Column('golden_set_fingerprint', sa.String(length=32), nullable=False),
    sa.Column('query_count', sa.Integer(), nullable=False),
    sa.Column('primary_k', sa.Integer(), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('duration_ms', sa.Float(), nullable=False),
    sa.Column('connector', sa.String(length=50), nullable=False),
    sa.Column('collection', sa.String(length=200), nullable=False),
    sa.Column('document_count', sa.Integer(), nullable=False),
    sa.Column('embedding_model', sa.String(length=200), nullable=True),
    sa.Column('embedding_dimensions', sa.Integer(), nullable=True),
    sa.Column('store_extra', sa.JSON(), nullable=False),
    sa.Column('trigger', sa.String(length=20), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['golden_set_id'], ['golden_sets.id'], name=op.f('fk_evaluation_runs_golden_set_id_golden_sets'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_evaluation_runs'))
    )
    with op.batch_alter_table('evaluation_runs', schema=None) as batch_op:
        batch_op.create_index('ix_evaluation_runs_fingerprint_started', ['golden_set_fingerprint', 'started_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_evaluation_runs_golden_set_id'), ['golden_set_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_evaluation_runs_run_uuid'), ['run_uuid'], unique=True)
        batch_op.create_index('ix_evaluation_runs_started_at', ['started_at'], unique=False)

    op.create_table('golden_queries',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('golden_set_id', sa.Integer(), nullable=False),
    sa.Column('query_id', sa.String(length=200), nullable=False),
    sa.Column('query_text', sa.Text(), nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['golden_set_id'], ['golden_sets.id'], name=op.f('fk_golden_queries_golden_set_id_golden_sets'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_golden_queries')),
    sa.UniqueConstraint('golden_set_id', 'query_id', name='uq_golden_queries_set_query')
    )
    with op.batch_alter_table('golden_queries', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_golden_queries_golden_set_id'), ['golden_set_id'], unique=False)

    op.create_table('golden_expected_documents',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('golden_query_id', sa.Integer(), nullable=False),
    sa.Column('document_id', sa.String(length=400), nullable=False),
    sa.Column('relevance', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['golden_query_id'], ['golden_queries.id'], name=op.f('fk_golden_expected_documents_golden_query_id_golden_queries'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_golden_expected_documents')),
    sa.UniqueConstraint('golden_query_id', 'document_id', name='uq_expected_documents_query_doc')
    )
    with op.batch_alter_table('golden_expected_documents', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_golden_expected_documents_golden_query_id'), ['golden_query_id'], unique=False)

    op.create_table('run_metrics',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('run_id', sa.Integer(), nullable=False),
    sa.Column('k', sa.Integer(), nullable=False),
    sa.Column('query_count', sa.Integer(), nullable=False),
    sa.Column('recall_at_k', sa.Float(), nullable=False),
    sa.Column('precision_at_k', sa.Float(), nullable=False),
    sa.Column('mrr', sa.Float(), nullable=False),
    sa.Column('ndcg_at_k', sa.Float(), nullable=False),
    sa.ForeignKeyConstraint(['run_id'], ['evaluation_runs.id'], name=op.f('fk_run_metrics_run_id_evaluation_runs'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_run_metrics')),
    sa.UniqueConstraint('run_id', 'k', name='uq_run_metrics_run_k')
    )
    with op.batch_alter_table('run_metrics', schema=None) as batch_op:
        batch_op.create_index('ix_run_metrics_k_run', ['k', 'run_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_run_metrics_run_id'), ['run_id'], unique=False)

    op.create_table('run_query_scores',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('run_id', sa.Integer(), nullable=False),
    sa.Column('query_id', sa.String(length=200), nullable=False),
    sa.Column('query_text', sa.Text(), nullable=False),
    sa.Column('k', sa.Integer(), nullable=False),
    sa.Column('hits', sa.Integer(), nullable=False),
    sa.Column('recall_at_k', sa.Float(), nullable=False),
    sa.Column('precision_at_k', sa.Float(), nullable=False),
    sa.Column('reciprocal_rank', sa.Float(), nullable=False),
    sa.Column('ndcg_at_k', sa.Float(), nullable=False),
    sa.Column('first_relevant_rank', sa.Integer(), nullable=True),
    sa.Column('retrieved_ids', sa.JSON(), nullable=False),
    sa.Column('relevant_ids', sa.JSON(), nullable=False),
    sa.Column('latency_ms', sa.Float(), nullable=True),
    sa.ForeignKeyConstraint(['run_id'], ['evaluation_runs.id'], name=op.f('fk_run_query_scores_run_id_evaluation_runs'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_run_query_scores')),
    sa.UniqueConstraint('run_id', 'query_id', name='uq_query_scores_run_query')
    )
    with op.batch_alter_table('run_query_scores', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_run_query_scores_run_id'), ['run_id'], unique=False)



def downgrade() -> None:
    with op.batch_alter_table('run_query_scores', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_run_query_scores_run_id'))

    op.drop_table('run_query_scores')
    with op.batch_alter_table('run_metrics', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_run_metrics_run_id'))
        batch_op.drop_index('ix_run_metrics_k_run')

    op.drop_table('run_metrics')
    with op.batch_alter_table('golden_expected_documents', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_golden_expected_documents_golden_query_id'))

    op.drop_table('golden_expected_documents')
    with op.batch_alter_table('golden_queries', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_golden_queries_golden_set_id'))

    op.drop_table('golden_queries')
    with op.batch_alter_table('evaluation_runs', schema=None) as batch_op:
        batch_op.drop_index('ix_evaluation_runs_started_at')
        batch_op.drop_index(batch_op.f('ix_evaluation_runs_run_uuid'))
        batch_op.drop_index(batch_op.f('ix_evaluation_runs_golden_set_id'))
        batch_op.drop_index('ix_evaluation_runs_fingerprint_started')

    op.drop_table('evaluation_runs')
    with op.batch_alter_table('golden_sets', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_golden_sets_name'))
        batch_op.drop_index('ix_golden_sets_fingerprint')

    op.drop_table('golden_sets')
