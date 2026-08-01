"""Canonical platform foundation.

Revision ID: 20260801_0001
Revises: None
"""

from alembic import op
import sqlalchemy as sa

revision = "20260801_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Frozen Phase 1 schema; do not replace with live ORM metadata.
    op.create_table('companies',
    sa.Column('company_id', sa.String(length=36), nullable=False),
    sa.Column('legal_name', sa.String(length=300), nullable=True),
    sa.Column('display_name', sa.String(length=300), nullable=True),
    sa.Column('current_legal_name', sa.String(length=300), nullable=True),
    sa.Column('country', sa.String(length=2), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('company_id', name=op.f('pk_companies'))
    )
    op.create_index('ix_companies_display_name', 'companies', ['display_name'], unique=False)
    op.create_table('data_sources',
    sa.Column('source_id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('code', sa.String(length=80), nullable=False),
    sa.Column('name', sa.String(length=160), nullable=False),
    sa.Column('source_type', sa.String(length=40), nullable=False),
    sa.Column('url', sa.Text(), nullable=True),
    sa.Column('is_official', sa.Boolean(), nullable=False),
    sa.Column('limitations', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('source_id', name=op.f('pk_data_sources')),
    sa.UniqueConstraint('code', name=op.f('uq_data_sources_code'))
    )
    op.create_table('exchanges',
    sa.Column('code', sa.String(length=16), nullable=False),
    sa.Column('name', sa.String(length=160), nullable=False),
    sa.Column('mic', sa.String(length=4), nullable=True),
    sa.Column('country', sa.String(length=2), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('timezone', sa.String(length=64), nullable=False),
    sa.PrimaryKeyConstraint('code', name=op.f('pk_exchanges')),
    sa.UniqueConstraint('mic', name=op.f('uq_exchanges_mic'))
    )
    op.create_table('indices',
    sa.Column('index_id', sa.String(length=36), nullable=False),
    sa.Column('code', sa.String(length=80), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('provider', sa.String(length=64), nullable=True),
    sa.Column('market', sa.String(length=16), nullable=False),
    sa.PrimaryKeyConstraint('index_id', name=op.f('pk_indices')),
    sa.UniqueConstraint('code', name=op.f('uq_indices_code'))
    )
    op.create_table('model_builds',
    sa.Column('build_id', sa.String(length=36), nullable=False),
    sa.Column('model_version', sa.String(length=80), nullable=False),
    sa.Column('factor_config_version', sa.String(length=80), nullable=False),
    sa.Column('factor_config_hash', sa.String(length=64), nullable=False),
    sa.Column('universe_name', sa.String(length=120), nullable=False),
    sa.Column('universe_version', sa.String(length=120), nullable=False),
    sa.Column('data_cutoff', sa.DateTime(timezone=True), nullable=False),
    sa.Column('built_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('status', sa.String(length=24), nullable=False),
    sa.Column('duration_seconds', sa.Numeric(precision=16, scale=3), nullable=True),
    sa.Column('attempted_count', sa.Integer(), nullable=False),
    sa.Column('scored_count', sa.Integer(), nullable=False),
    sa.Column('failed_count', sa.Integer(), nullable=False),
    sa.Column('provider_versions', sa.JSON(), nullable=False),
    sa.Column('source_data_version', sa.String(length=160), nullable=True),
    sa.Column('validation_status', sa.String(length=200), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('error_summary', sa.Text(), nullable=True),
    sa.CheckConstraint('attempted_count >= 0', name=op.f('ck_model_builds_attempted_nonnegative')),
    sa.CheckConstraint('failed_count >= 0', name=op.f('ck_model_builds_failed_nonnegative')),
    sa.CheckConstraint('scored_count >= 0', name=op.f('ck_model_builds_scored_nonnegative')),
    sa.PrimaryKeyConstraint('build_id', name=op.f('pk_model_builds'))
    )
    op.create_index('ix_model_builds_latest', 'model_builds', ['status', 'built_at'], unique=False)
    op.create_table('sectors',
    sa.Column('sector_id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('name', sa.String(length=160), nullable=False),
    sa.PrimaryKeyConstraint('sector_id', name=op.f('pk_sectors')),
    sa.UniqueConstraint('name', name=op.f('uq_sectors_name'))
    )
    op.create_table('import_runs',
    sa.Column('import_run_id', sa.String(length=36), nullable=False),
    sa.Column('source_id', sa.Integer(), nullable=False),
    sa.Column('source_version', sa.String(length=120), nullable=True),
    sa.Column('source_timestamp', sa.DateTime(timezone=True), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('status', sa.String(length=24), nullable=False),
    sa.Column('summary', sa.JSON(), nullable=True),
    sa.Column('source_hash', sa.String(length=64), nullable=True),
    sa.ForeignKeyConstraint(['source_id'], ['data_sources.source_id'], name=op.f('fk_import_runs_source_id_data_sources')),
    sa.PrimaryKeyConstraint('import_run_id', name=op.f('pk_import_runs'))
    )
    op.create_table('industries',
    sa.Column('industry_id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('sector_id', sa.Integer(), nullable=True),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('sub_industry', sa.String(length=200), nullable=True),
    sa.ForeignKeyConstraint(['sector_id'], ['sectors.sector_id'], name=op.f('fk_industries_sector_id_sectors')),
    sa.PrimaryKeyConstraint('industry_id', name=op.f('pk_industries')),
    sa.UniqueConstraint('sector_id', 'name', 'sub_industry', name='uq_industries_classification')
    )
    op.create_table('data_freshness',
    sa.Column('freshness_id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('dataset', sa.String(length=100), nullable=False),
    sa.Column('partition_key', sa.String(length=160), nullable=False),
    sa.Column('source_id', sa.Integer(), nullable=True),
    sa.Column('import_run_id', sa.String(length=36), nullable=True),
    sa.Column('state', sa.String(length=24), nullable=False),
    sa.Column('source_timestamp', sa.DateTime(timezone=True), nullable=True),
    sa.Column('retrieved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('normalized_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('data_version', sa.String(length=160), nullable=True),
    sa.Column('quality_status', sa.String(length=24), nullable=False),
    sa.Column('warning', sa.Text(), nullable=True),
    sa.Column('raw_payload_hash', sa.String(length=64), nullable=True),
    sa.ForeignKeyConstraint(['import_run_id'], ['import_runs.import_run_id'], name=op.f('fk_data_freshness_import_run_id_import_runs')),
    sa.ForeignKeyConstraint(['source_id'], ['data_sources.source_id'], name=op.f('fk_data_freshness_source_id_data_sources')),
    sa.PrimaryKeyConstraint('freshness_id', name=op.f('pk_data_freshness')),
    sa.UniqueConstraint('dataset', 'partition_key', name='uq_data_freshness_partition')
    )
    op.create_index('ix_freshness_state', 'data_freshness', ['state', 'normalized_at'], unique=False)
    op.create_table('import_issues',
    sa.Column('issue_id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('import_run_id', sa.String(length=36), nullable=False),
    sa.Column('source_record_id', sa.String(length=200), nullable=True),
    sa.Column('issue_type', sa.String(length=40), nullable=False),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('raw_record', sa.JSON(), nullable=True),
    sa.Column('resolution_status', sa.String(length=24), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['import_run_id'], ['import_runs.import_run_id'], name=op.f('fk_import_issues_import_run_id_import_runs'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('issue_id', name=op.f('pk_import_issues'))
    )
    op.create_index('ix_import_issues_status', 'import_issues', ['resolution_status', 'issue_type'], unique=False)
    op.create_table('instruments',
    sa.Column('instrument_id', sa.String(length=36), nullable=False),
    sa.Column('company_id', sa.String(length=36), nullable=True),
    sa.Column('security_type', sa.String(length=32), nullable=False),
    sa.Column('country', sa.String(length=2), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('timezone', sa.String(length=64), nullable=False),
    sa.Column('sector_id', sa.Integer(), nullable=True),
    sa.Column('industry_id', sa.Integer(), nullable=True),
    sa.Column('market_cap_category', sa.String(length=40), nullable=True),
    sa.Column('quality_status', sa.String(length=24), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['company_id'], ['companies.company_id'], name=op.f('fk_instruments_company_id_companies')),
    sa.ForeignKeyConstraint(['industry_id'], ['industries.industry_id'], name=op.f('fk_instruments_industry_id_industries')),
    sa.ForeignKeyConstraint(['sector_id'], ['sectors.sector_id'], name=op.f('fk_instruments_sector_id_sectors')),
    sa.PrimaryKeyConstraint('instrument_id', name=op.f('pk_instruments'))
    )
    op.create_table('index_memberships',
    sa.Column('membership_id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('index_id', sa.String(length=36), nullable=False),
    sa.Column('instrument_id', sa.String(length=36), nullable=False),
    sa.Column('effective_from', sa.Date(), nullable=False),
    sa.Column('effective_to', sa.Date(), nullable=True),
    sa.Column('source_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['index_id'], ['indices.index_id'], name=op.f('fk_index_memberships_index_id_indices'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['instrument_id'], ['instruments.instrument_id'], name=op.f('fk_index_memberships_instrument_id_instruments'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['source_id'], ['data_sources.source_id'], name=op.f('fk_index_memberships_source_id_data_sources')),
    sa.PrimaryKeyConstraint('membership_id', name=op.f('pk_index_memberships')),
    sa.UniqueConstraint('index_id', 'instrument_id', 'effective_from', name='uq_index_memberships_identity')
    )
    op.create_index('ix_memberships_instrument', 'index_memberships', ['instrument_id', 'effective_to'], unique=False)
    op.create_table('instrument_aliases',
    sa.Column('alias_id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('instrument_id', sa.String(length=36), nullable=False),
    sa.Column('alias_type', sa.String(length=32), nullable=False),
    sa.Column('value', sa.String(length=300), nullable=False),
    sa.Column('normalized_value', sa.String(length=300), nullable=False),
    sa.Column('valid_from', sa.Date(), nullable=True),
    sa.Column('valid_to', sa.Date(), nullable=True),
    sa.Column('source_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['instrument_id'], ['instruments.instrument_id'], name=op.f('fk_instrument_aliases_instrument_id_instruments'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['source_id'], ['data_sources.source_id'], name=op.f('fk_instrument_aliases_source_id_data_sources')),
    sa.PrimaryKeyConstraint('alias_id', name=op.f('pk_instrument_aliases')),
    sa.UniqueConstraint('instrument_id', 'alias_type', 'normalized_value', name='uq_instrument_aliases_identity')
    )
    op.create_index('ix_aliases_normalized_value', 'instrument_aliases', ['normalized_value'], unique=False)
    op.create_table('instrument_listings',
    sa.Column('listing_id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('instrument_id', sa.String(length=36), nullable=False),
    sa.Column('exchange_code', sa.String(length=16), nullable=False),
    sa.Column('symbol', sa.String(length=40), nullable=False),
    sa.Column('bse_code', sa.String(length=6), nullable=True),
    sa.Column('isin', sa.String(length=12), nullable=True),
    sa.Column('exchange_segment', sa.String(length=40), nullable=True),
    sa.Column('exchange_series', sa.String(length=16), nullable=True),
    sa.Column('status', sa.String(length=24), nullable=False),
    sa.Column('listing_date', sa.Date(), nullable=True),
    sa.Column('delisting_date', sa.Date(), nullable=True),
    sa.Column('is_primary', sa.Boolean(), nullable=False),
    sa.Column('is_sme', sa.Boolean(), nullable=True),
    sa.Column('valid_from', sa.Date(), nullable=True),
    sa.Column('valid_to', sa.Date(), nullable=True),
    sa.CheckConstraint('bse_code IS NULL OR length(bse_code) = 6', name=op.f('ck_instrument_listings_bse_code_length')),
    sa.CheckConstraint('isin IS NULL OR length(isin) = 12', name=op.f('ck_instrument_listings_isin_length')),
    sa.ForeignKeyConstraint(['exchange_code'], ['exchanges.code'], name=op.f('fk_instrument_listings_exchange_code_exchanges')),
    sa.ForeignKeyConstraint(['instrument_id'], ['instruments.instrument_id'], name=op.f('fk_instrument_listings_instrument_id_instruments'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('listing_id', name=op.f('pk_instrument_listings'))
    )
    op.create_index('ix_listings_bse_code', 'instrument_listings', ['bse_code'], unique=False)
    op.create_index('ix_listings_exchange_symbol', 'instrument_listings', ['exchange_code', 'symbol'], unique=False)
    op.create_index('ix_listings_isin', 'instrument_listings', ['isin'], unique=False)
    op.create_index('ix_listings_status', 'instrument_listings', ['status'], unique=False)
    op.create_index('uq_listings_current_exchange_symbol', 'instrument_listings', ['exchange_code', 'symbol'], unique=True, sqlite_where=sa.text('valid_to IS NULL'), postgresql_where=sa.text('valid_to IS NULL'))
    op.create_index('uq_listings_one_primary', 'instrument_listings', ['instrument_id'], unique=True, sqlite_where=sa.text('valid_to IS NULL AND is_primary = 1'), postgresql_where=sa.text('valid_to IS NULL AND is_primary'))
    op.create_table('provider_symbols',
    sa.Column('mapping_id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('instrument_id', sa.String(length=36), nullable=False),
    sa.Column('provider', sa.String(length=64), nullable=False),
    sa.Column('provider_symbol', sa.String(length=100), nullable=False),
    sa.Column('provider_instrument_id', sa.String(length=160), nullable=True),
    sa.Column('valid_from', sa.Date(), nullable=True),
    sa.Column('valid_to', sa.Date(), nullable=True),
    sa.Column('is_primary', sa.Boolean(), nullable=False),
    sa.Column('source_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['instrument_id'], ['instruments.instrument_id'], name=op.f('fk_provider_symbols_instrument_id_instruments'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['source_id'], ['data_sources.source_id'], name=op.f('fk_provider_symbols_source_id_data_sources')),
    sa.PrimaryKeyConstraint('mapping_id', name=op.f('pk_provider_symbols'))
    )
    op.create_index('ix_provider_symbols_instrument_provider', 'provider_symbols', ['instrument_id', 'provider'], unique=False)
    op.create_index('uq_provider_symbols_current', 'provider_symbols', ['provider', 'provider_symbol'], unique=True, sqlite_where=sa.text('valid_to IS NULL'), postgresql_where=sa.text('valid_to IS NULL'))
    op.create_table('quote_snapshots',
    sa.Column('quote_id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('instrument_id', sa.String(length=36), nullable=False),
    sa.Column('provider', sa.String(length=64), nullable=False),
    sa.Column('provider_symbol', sa.String(length=100), nullable=False),
    sa.Column('last_price', sa.Numeric(precision=24, scale=8), nullable=True),
    sa.Column('previous_close', sa.Numeric(precision=24, scale=8), nullable=True),
    sa.Column('currency', sa.String(length=3), nullable=True),
    sa.Column('market_status', sa.String(length=24), nullable=False),
    sa.Column('provider_timestamp', sa.DateTime(timezone=True), nullable=True),
    sa.Column('retrieved_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('freshness_state', sa.String(length=24), nullable=False),
    sa.Column('quality_status', sa.String(length=24), nullable=False),
    sa.Column('raw_payload_hash', sa.String(length=64), nullable=True),
    sa.ForeignKeyConstraint(['instrument_id'], ['instruments.instrument_id'], name=op.f('fk_quote_snapshots_instrument_id_instruments')),
    sa.PrimaryKeyConstraint('quote_id', name=op.f('pk_quote_snapshots'))
    )
    op.create_index('ix_quotes_instrument_retrieved', 'quote_snapshots', ['instrument_id', 'retrieved_at'], unique=False)
    op.create_table('score_snapshots',
    sa.Column('score_id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('build_id', sa.String(length=36), nullable=False),
    sa.Column('instrument_id', sa.String(length=36), nullable=False),
    sa.Column('rank', sa.Integer(), nullable=False),
    sa.Column('multibagger_score', sa.Numeric(precision=6, scale=3), nullable=False),
    sa.Column('investment_score', sa.Numeric(precision=6, scale=3), nullable=False),
    sa.Column('confidence', sa.Numeric(precision=6, scale=5), nullable=False),
    sa.Column('risk_score', sa.Numeric(precision=6, scale=3), nullable=False),
    sa.Column('investability', sa.String(length=80), nullable=False),
    sa.Column('positive_signal_count', sa.Integer(), nullable=False),
    sa.Column('red_flag_count', sa.Integer(), nullable=False),
    sa.Column('coverage_quality', sa.Numeric(precision=6, scale=5), nullable=True),
    sa.Column('has_missing_data', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('rank > 0', name=op.f('ck_score_snapshots_rank_positive')),
    sa.ForeignKeyConstraint(['build_id'], ['model_builds.build_id'], name=op.f('fk_score_snapshots_build_id_model_builds'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['instrument_id'], ['instruments.instrument_id'], name=op.f('fk_score_snapshots_instrument_id_instruments')),
    sa.PrimaryKeyConstraint('score_id', name=op.f('pk_score_snapshots')),
    sa.UniqueConstraint('build_id', 'instrument_id', name='uq_score_snapshots_build_instrument'),
    sa.UniqueConstraint('build_id', 'rank', name='uq_score_snapshots_build_rank')
    )
    op.create_index('ix_scores_build_multibagger', 'score_snapshots', ['build_id', 'multibagger_score'], unique=False)
    op.create_index('ix_scores_instrument_created', 'score_snapshots', ['instrument_id', 'created_at'], unique=False)
    op.create_table('score_components',
    sa.Column('component_id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('score_id', sa.Integer(), nullable=False),
    sa.Column('component_name', sa.String(length=100), nullable=False),
    sa.Column('score', sa.Numeric(precision=6, scale=3), nullable=False),
    sa.Column('confidence', sa.Numeric(precision=6, scale=5), nullable=False),
    sa.Column('contribution', sa.Numeric(precision=8, scale=4), nullable=True),
    sa.Column('evidence_count', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['score_id'], ['score_snapshots.score_id'], name=op.f('fk_score_components_score_id_score_snapshots'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('component_id', name=op.f('pk_score_components')),
    sa.UniqueConstraint('score_id', 'component_name', name='uq_score_components_identity')
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    # Reverse only the canonical schema; the legacy DuckDB ledger is untouched.
    op.drop_table('score_components')
    op.drop_index('ix_scores_instrument_created', table_name='score_snapshots')
    op.drop_index('ix_scores_build_multibagger', table_name='score_snapshots')
    op.drop_table('score_snapshots')
    op.drop_index('ix_quotes_instrument_retrieved', table_name='quote_snapshots')
    op.drop_table('quote_snapshots')
    op.drop_index('uq_provider_symbols_current', table_name='provider_symbols', sqlite_where=sa.text('valid_to IS NULL'), postgresql_where=sa.text('valid_to IS NULL'))
    op.drop_index('ix_provider_symbols_instrument_provider', table_name='provider_symbols')
    op.drop_table('provider_symbols')
    op.drop_index('uq_listings_one_primary', table_name='instrument_listings', sqlite_where=sa.text('valid_to IS NULL AND is_primary = 1'), postgresql_where=sa.text('valid_to IS NULL AND is_primary'))
    op.drop_index('uq_listings_current_exchange_symbol', table_name='instrument_listings', sqlite_where=sa.text('valid_to IS NULL'), postgresql_where=sa.text('valid_to IS NULL'))
    op.drop_index('ix_listings_status', table_name='instrument_listings')
    op.drop_index('ix_listings_isin', table_name='instrument_listings')
    op.drop_index('ix_listings_exchange_symbol', table_name='instrument_listings')
    op.drop_index('ix_listings_bse_code', table_name='instrument_listings')
    op.drop_table('instrument_listings')
    op.drop_index('ix_aliases_normalized_value', table_name='instrument_aliases')
    op.drop_table('instrument_aliases')
    op.drop_index('ix_memberships_instrument', table_name='index_memberships')
    op.drop_table('index_memberships')
    op.drop_table('instruments')
    op.drop_index('ix_import_issues_status', table_name='import_issues')
    op.drop_table('import_issues')
    op.drop_index('ix_freshness_state', table_name='data_freshness')
    op.drop_table('data_freshness')
    op.drop_table('industries')
    op.drop_table('import_runs')
    op.drop_table('sectors')
    op.drop_index('ix_model_builds_latest', table_name='model_builds')
    op.drop_table('model_builds')
    op.drop_table('indices')
    op.drop_table('exchanges')
    op.drop_table('data_sources')
    op.drop_index('ix_companies_display_name', table_name='companies')
    op.drop_table('companies')
    # ### end Alembic commands ###
