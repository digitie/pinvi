# Juso Legal Dong ETL

## Goal

Implement the first Juso ETL slice that reads `rnaddrkor_*.txt`, stores raw rows,
and rebuilds the legal-dong code dictionary used by later address and geospatial work.

## Scope

- Add DB tables for:
  - `address_raw_juso_road_address`
  - `address_code_standard`
- Add a parser for Juso road-address TXT files
- Add a loader that:
  - preserves raw rows by file hash and row number
  - rebuilds active legal-dong codes
  - rejects conflicting names for the same `legal_dong_code`
- Add integration tests against WSL2 Docker Postgres/PostGIS

## Decisions

- Tests run in WSL2 and connect to Docker Postgres/PostGIS on `localhost:55432`
- Raw ingest is idempotent by `source_file_hash + row_number`
- `change_reason_code = 63` rows are excluded from the active legal-dong dictionary
- The first implementation loads the legal-dong subset before the broader Juso address-serving tables

## Verification

- Parser unit tests
- Loader integration tests on Docker Postgres/PostGIS
- Model metadata test
- Migration contract test
