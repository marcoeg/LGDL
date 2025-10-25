"""
Tests for embedding cache with versioning and offline fallback.

Copyright (c) 2025 Graziano Labs Corp.
"""

import os, sqlite3, tempfile
import pytest
import numpy as np
from pathlib import Path
from lgdl.runtime.matcher import EmbeddingClient, cosine


@pytest.fixture
def clean_env(monkeypatch, tmp_path):
    """Clean environment for testing with temporary cache directory."""
    # Set environment variables
    monkeypatch.setenv("EMBEDDING_CACHE", "1")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    # Change to temp directory for consistent cache location
    original_cwd = os.getcwd()
    os.chdir(tmp_path)

    yield tmp_path / ".embeddings_cache"

    # Restore original directory
    os.chdir(original_cwd)


def test_cache_persistence(clean_env):
    """Embeddings cached and retrieved correctly."""
    client = EmbeddingClient()
    vec1 = client.embed("test phrase")
    vec2 = client.embed("test phrase")
    assert vec1 == vec2  # Same from cache


def test_offline_deterministic(clean_env):
    """Offline embeddings are deterministic across instances."""
    client1 = EmbeddingClient()
    client2 = EmbeddingClient()

    vec1 = client1.embed("hello world")
    vec2 = client2.embed("hello world")

    assert vec1 == vec2
    assert len(vec1) == 256  # Expected dimensionality


def test_offline_different_texts(clean_env):
    """Different texts produce different embeddings."""
    client = EmbeddingClient()

    vec_hello = client.embed("hello world")
    vec_goodbye = client.embed("goodbye world")

    assert vec_hello != vec_goodbye


def test_offline_similarity_properties(clean_env):
    """Offline embeddings have reasonable similarity properties."""
    client = EmbeddingClient()

    vec_hello1 = client.embed("hello world")
    vec_hello2 = client.embed("hello world")
    vec_goodbye = client.embed("goodbye world")

    # Same text should be identical
    sim_same = cosine(vec_hello1, vec_hello2)
    assert sim_same == 1.0

    # Different texts should have lower similarity
    sim_diff = cosine(vec_hello1, vec_goodbye)
    assert sim_diff < 1.0


def test_cache_versioning(clean_env):
    """Cache keys include model and version."""
    client = EmbeddingClient()
    vec = client.embed("test")

    conn = sqlite3.connect(client.cache_db)
    cursor = conn.execute(
        "SELECT model, version FROM embeddings WHERE text = ?",
        ("test",)
    )
    row = cursor.fetchone()
    conn.close()

    assert row is not None
    assert row[0] == client.model
    assert row[1] == client.version_lock


def test_cache_db_created(clean_env):
    """Cache database file is created."""
    client = EmbeddingClient()
    assert client.cache_db.exists()
    assert client.cache_db.suffix == ".db"


def test_cache_survives_restart(clean_env):
    """Cache persists across client instances."""
    client1 = EmbeddingClient()
    vec1 = client1.embed("persistence test")

    # Create new client (simulates restart)
    client2 = EmbeddingClient()
    vec2 = client2.embed("persistence test")

    assert vec1 == vec2


def test_cache_disabled(monkeypatch, tmp_path):
    """In-memory cache works when SQLite cache disabled."""
    monkeypatch.setenv("EMBEDDING_CACHE", "0")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    # Change to temp directory
    original_cwd = os.getcwd()
    os.chdir(tmp_path)

    try:
        client = EmbeddingClient()
        vec1 = client.embed("test")
        vec2 = client.embed("test")

        assert vec1 == vec2
        assert not client.cache_enabled
        assert not hasattr(client, 'cache_db') or not client.cache_db.exists()
    finally:
        os.chdir(original_cwd)


def test_embedding_normalization(clean_env):
    """Offline embeddings are L2 normalized."""
    client = EmbeddingClient()
    vec = client.embed("normalization test")

    norm = np.linalg.norm(vec)
    assert abs(norm - 1.0) < 1e-6  # Should be ~1.0


def test_bigram_features(clean_env):
    """Offline embedding uses character bigrams."""
    client = EmbeddingClient()

    # Similar texts should have higher similarity due to shared bigrams
    vec_test1 = client.embed("testing")
    vec_test2 = client.embed("test")
    vec_unrelated = client.embed("xyzabc")

    sim_related = cosine(vec_test1, vec_test2)
    sim_unrelated = cosine(vec_test1, vec_unrelated)

    # test1 and test2 share bigrams like "te", "es", "st"
    # so similarity should be higher than with unrelated text
    assert sim_related > sim_unrelated


def test_empty_text_handling(clean_env):
    """Handle empty and short text gracefully."""
    client = EmbeddingClient()

    vec_empty = client.embed("")
    vec_single = client.embed("a")

    assert len(vec_empty) == 256
    assert len(vec_single) == 256
    assert np.linalg.norm(vec_empty) > 0  # Should be normalized
    assert np.linalg.norm(vec_single) > 0


def test_model_and_version_configuration(monkeypatch, clean_env):
    """Model and version can be configured via environment variables."""
    monkeypatch.setenv("OPENAI_EMBEDDING_MODEL", "custom-model")
    monkeypatch.setenv("OPENAI_EMBEDDING_VERSION", "2025-02")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    client = EmbeddingClient()

    assert client.model == "custom-model"
    assert client.version_lock == "2025-02"
    assert "custom-model_2025-02.db" in str(client.cache_db)


def test_cache_key_generation(clean_env):
    """Cache keys are SHA256 hashes of text."""
    import hashlib

    client = EmbeddingClient()
    text = "test text"

    expected_key = hashlib.sha256(text.encode("utf-8")).hexdigest()
    actual_key = client._key(text)

    assert actual_key == expected_key


def test_different_versions_different_cache(monkeypatch, tmp_path):
    """Different versions use separate cache entries."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    original_cwd = os.getcwd()
    os.chdir(tmp_path)

    try:
        # Create first client with version 2025-01
        monkeypatch.setenv("OPENAI_EMBEDDING_VERSION", "2025-01")
        monkeypatch.setenv("EMBEDDING_CACHE", "1")
        client1 = EmbeddingClient()
        vec1 = client1.embed("test")

        # Create second client with version 2025-02
        monkeypatch.setenv("OPENAI_EMBEDDING_VERSION", "2025-02")
        client2 = EmbeddingClient()
        vec2 = client2.embed("test")

        # Both should get same offline embedding (deterministic)
        # but they'll be cached separately
        assert vec1 == vec2

        # Verify different cache files were created
        assert client1.cache_db != client2.cache_db
        assert client1.cache_db.exists()
        assert client2.cache_db.exists()
    finally:
        os.chdir(original_cwd)
