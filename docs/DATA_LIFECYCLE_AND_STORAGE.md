# OMIP v0.4.3 Data Lifecycle and Storage Guide

## Recommended operating sequence

1. Run acquisition normally.
2. Review Storage Summary regularly.
3. Create a background Mission export after important experiments.
4. Create a database backup before cleanup or deletion.
5. Use Cleanup Preview to inspect eligible data.
6. Execute cleanup only when the preview is understood.
7. Run WAL Checkpoint and `ANALYZE` during quiet periods.
8. Use `VACUUM` only after stopping acquisition.

## Cleanup is manual

OMIP does not schedule or automatically execute retention cleanup. The policy describes eligibility only. This prevents an incorrect configuration from silently deleting research data.

## Export versus backup

A Mission export is portable research data for a single Mission. A database backup is a full recovery copy of the complete OMIP SQLite database. Important experiments should normally have both.

## SQLite considerations

SQLite is appropriate for the current local starter platform. As data volume and concurrent writers grow, measure write latency, query latency, database size and WAL behaviour. Moving to PostgreSQL or a time-series database should be considered before the local database becomes an operational bottleneck.
