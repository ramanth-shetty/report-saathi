# Shared Module

This directory contains contracts, schema interfaces, and invariants shared across:
1. **Frontend (`frontend/`)**: TypeScript types and constants.
2. **Backend (`backend/`)**: Python types and constants.
3. **API Contracts (`docs/06a-api-contract.md`)**: Formal JSON schemas.

### Invariant Rules
- Any modification to data structures, field names, or API schemas must be reflected here and in `docs/06a-api-contract.md` simultaneously.
- Neither frontend nor backend should define conflicting interfaces for external boundary payloads.
