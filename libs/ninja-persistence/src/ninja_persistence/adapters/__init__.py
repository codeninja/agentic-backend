"""Persistence adapters for each storage engine."""

MAX_QUERY_LIMIT = 1000
MIN_QUERY_LIMIT = 1


def _validate_limit(limit: int) -> int:
    """Validate and clamp the *limit* parameter for query methods.

    Raises ``ValueError`` for non-positive values.  Values exceeding
    ``MAX_QUERY_LIMIT`` (1000) are silently capped.
    """
    if limit < MIN_QUERY_LIMIT:
        raise ValueError(
            f"limit must be >= {MIN_QUERY_LIMIT}, got {limit}"
        )
    return min(limit, MAX_QUERY_LIMIT)


def _validate_offset(offset: int) -> int:
    """Validate the *offset* parameter for query methods.

    Raises ``ValueError`` for negative values.
    """
    if offset < 0:
        raise ValueError(f"offset must be >= 0, got {offset}")
    return offset
