"""External data collectors.

Collector implementations should only fetch and normalize source responses. Database
writes belong in :mod:`loaders` so collection and persistence can be retried separately.
"""
