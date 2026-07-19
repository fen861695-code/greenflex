# ADR 0001: Modular Monolith

Status: Accepted

GreenFlex v0.1.0 uses a modular Python application with a separate worker process instead of microservices. This minimizes deployment dependencies while preserving domain ports that can later move behind service boundaries. Modules communicate through application interfaces and persisted state, not direct infrastructure imports.

