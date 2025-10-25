# Changelog

All notable changes to the LGDL project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Greeting example game with 3 moves (greeting, farewell, small_talk)
- Golden dialog tests for greeting game (5 scenarios)
- Multi-game validation with concurrent medical + greeting games

### Changed
- Updated README and CLI examples to use greeting game instead of non-existent er_triage
- Fixed game.lgdl confidence thresholds for casual greetings (medium instead of high)

### Planned
- P1-1: Negotiation state management with clarification loops
- v1.0 Grammar: Capability await/timeout, context guards, learning hooks
- IR compiler updates for v1.0 features

---

## [v1.0-alpha-foundation] - 2025-01-25

This is the foundational release establishing security, scalability, and determinism for v1.0.

### Added

#### Template Security (P0-1)
- **AST-based template validation** preventing remote code execution
  - Error taxonomy with codes E001-E499 for different error categories
  - Whitelist validator: only arithmetic operators (+, -, *, /, //, %, unary -)
  - Security constraints: max expression length 256 chars, magnitude ±1e9
  - Forbidden operations: exponentiation (**), attribute access, subscripts, function calls, lambdas, comprehensions
- **Template syntax**:
  - `{var}` - simple variable substitution
  - `{var?fallback}` - variable with fallback value
  - `${expr}` - secure arithmetic expressions
- **Comprehensive error handling** with codes, messages, locations, and hints
- **Test suite**: 63 tests (14 error taxonomy + 49 template functionality)

#### Multi-Game API (P0-2)
- **GameRegistry** for managing multiple LGDL games concurrently
  - File hash tracking for cache invalidation
  - Per-game runtime instances
  - Metadata management (id, name, version, path, file_hash)
- **New API endpoints**:
  - `GET /healthz` - Health check with game count and IDs
  - `GET /games` - List all registered games with metadata
  - `GET /games/{id}` - Get specific game metadata
  - `POST /games/{id}/move` - Execute move in specific game
  - `POST /games/{id}/reload` - Hot reload game from disk (dev mode only)
- **CLI enhancements**:
  - `lgdl serve` command for multi-game API server
  - Game file validation before server start
  - Dev mode with hot reload support
  - Clear error messages for missing files or invalid formats
- **Test suite**: 18 tests (10 registry unit + 8 API integration)

#### Deterministic Embeddings (P1-2)
- **Versioned SQLite cache** for embedding reproducibility
  - Cache key: `(text_hash, model, version)` for deterministic lookups
  - Persistent across runtime restarts
  - Version mismatch warnings (fail-closed: don't cache mismatched versions)
- **Enhanced offline fallback**:
  - TF-IDF character bigram embedding (256 dimensions)
  - Improved from bag-of-letters (26 dimensions)
  - L2 normalized vectors
  - Deterministic across instances
- **Environment configuration**:
  - `OPENAI_EMBEDDING_MODEL` (default: text-embedding-3-small)
  - `OPENAI_EMBEDDING_VERSION` (default: 2025-01)
  - `EMBEDDING_CACHE` (default: 1, set to 0 for in-memory only)
- **Test suite**: 14 tests (cache persistence, versioning, offline determinism)

### Changed
- **Deprecated `/move` endpoint** in favor of `/games/{game_id}/move`
  - Legacy endpoint still functional with `X-Deprecation-Warning` header
  - Will be removed in v2.0
- **Enhanced offline embeddings**: Character bigrams capture local patterns better than single characters
- **Runtime engine**: Now uses secure `TemplateRenderer` instead of string substitution

### Fixed
- Template injection vulnerability via arithmetic expressions
- Non-deterministic confidence scores from embedding model updates
- Single-game API limitation preventing multi-tenant deployments

### Infrastructure
- Added `httpx` to dev dependencies for API testing
- Added `.embeddings_cache/` to `.gitignore`
- Comprehensive test coverage: **97 tests** (increased from 2)
  - All golden dialog tests passing
  - No regressions in existing functionality

### Documentation
- Created `docs/MIGRATION_MVP_TO_V1.md` - Complete migration plan from MVP to v1.0
- Created `docs/P0_P1_CRITICAL_FIXES.md` - Detailed implementation guide for critical fixes
- Error codes documented in `lgdl/errors.py`

---

## [mvp-v0.1] - 2025-01-24

Initial MVP release with basic functionality.

### Features
- Lark-based LGDL parser (grammar v0.1)
- Two-stage pattern matching (lexical + semantic)
- Optional OpenAI embeddings with bag-of-letters fallback
- Single-game FastAPI runtime
- Golden dialog testing framework
- Medical scheduling example game

### Known Limitations
- Single game per API instance
- Template eval without security validation
- Non-deterministic embeddings (model updates)
- No negotiation loops
- No learning pipeline
