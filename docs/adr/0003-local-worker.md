# ADR 0003: SQLite-Leased Local Worker

Status: Accepted

The MVP uses a worker process that leases one order at a time from SQLite. Single concurrency makes GPU energy attribution defensible on the development laptop. Leases expire and are recoverable after a crash. Redis and distributed orchestration are deferred until multi-node requirements exist.

