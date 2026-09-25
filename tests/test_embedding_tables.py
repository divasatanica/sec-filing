from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, Integer, String

from sec_filing_agent.db.tables import (
    ChunkEmbedding,
    EmbeddingModelProfile,
    FilingChunk,
    FinancialFact,
)


def test_embedding_tables_support_multiple_model_profiles_and_chunk_cascade() -> None:
    profile_constraints = {
        constraint.name: tuple(column.name for column in constraint.columns)
        for constraint in EmbeddingModelProfile.__table__.constraints
        if constraint.name
    }
    embedding_constraints = {
        constraint.name: tuple(column.name for column in constraint.columns)
        for constraint in ChunkEmbedding.__table__.constraints
        if constraint.name
    }

    assert profile_constraints["uq_embedding_model_profiles_identity"] == (
        "model_name",
        "revision",
        "dimensions",
    )
    assert embedding_constraints["uq_chunk_embeddings_chunk_profile"] == (
        "chunk_id",
        "model_profile_id",
    )
    assert isinstance(ChunkEmbedding.__table__.c.id.type, BigInteger)
    assert isinstance(ChunkEmbedding.__table__.c.chunk_id.type, BigInteger)
    assert isinstance(ChunkEmbedding.__table__.c.model_profile_id.type, Integer)
    assert isinstance(ChunkEmbedding.__table__.c.embedding.type, Vector)
    assert tuple(
        column.name
        for index in ChunkEmbedding.__table__.indexes
        if index.name == "ix_chunk_embeddings_model_profile_cik"
        for column in index.columns
    ) == ("model_profile_id", "cik")

    foreign_keys = {
        foreign_key.parent.name: (foreign_key.target_fullname, foreign_key.ondelete)
        for foreign_key in ChunkEmbedding.__table__.foreign_keys
    }
    assert foreign_keys["chunk_id"] == ("filing_chunks.id", "CASCADE")
    assert foreign_keys["model_profile_id"] == ("embedding_model_profiles.id", "RESTRICT")


def test_hot_fact_tables_expose_a_database_enforced_company_scope() -> None:
    for table in (FilingChunk.__table__, ChunkEmbedding.__table__, FinancialFact.__table__):
        cik = table.c.cik
        foreign_key = next(iter(cik.foreign_keys))

        assert isinstance(cik.type, String)
        assert cik.type.length == 10
        assert cik.nullable is False
        assert foreign_key.target_fullname == "companies.cik"
        assert foreign_key.ondelete == "RESTRICT"

    assert "ix_filing_chunks_cik" in {index.name for index in FilingChunk.__table__.indexes}
    assert "ix_financial_facts_cik" in {index.name for index in FinancialFact.__table__.indexes}
