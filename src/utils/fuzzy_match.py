"""Fuzzy employee name matching wrapper.

Tries **rapidfuzz** first (MIT, fast C extension) and falls back to
**fuzzywuzzy** if available, or a pure-Python difflib solution of last resort.

Usage::

    from src.utils.fuzzy_match import FuzzyMatcher

    matcher = FuzzyMatcher(threshold=89)
    results = matcher.match("John Doe", ["John D.", "Jane Doe", "Jon Doe"])
    # [(name, score), ...]
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from src.utils.logger import get_logger

log = get_logger(__name__)

MatchResult = Tuple[str, float, int]  # (candidate, score_0_100, original_index)

try:
    from rapidfuzz import process as rf_process, fuzz as rf_fuzz  # type: ignore
    _BACKEND = "rapidfuzz"
    log.info("FuzzyMatcher: using rapidfuzz backend.")
except ImportError:
    rf_process = None
    rf_fuzz = None
    try:
        from fuzzywuzzy import process as fw_process, fuzz as fw_fuzz  # type: ignore
        _BACKEND = "fuzzywuzzy"
        log.warning("FuzzyMatcher: rapidfuzz not found, using fuzzywuzzy backend.")
    except ImportError:
        fw_process = None
        fw_fuzz = None
        _BACKEND = "difflib"
        log.warning("FuzzyMatcher: no fuzzy library found, using difflib (slow).")
        import difflib


DEFAULT_THRESHOLD = 89  # percent


class FuzzyMatcher:
    """Wraps a fuzzy-matching backend to compare employee name strings.

    Args:
        threshold: Minimum similarity score (0-100) to consider a match.
        scorer:    Scorer name passed to rapidfuzz/fuzzywuzzy. Ignored for
                   difflib backend.  Defaults to ``"WRatio"`` (balanced).
    """

    def __init__(
        self,
        threshold: float = DEFAULT_THRESHOLD,
        scorer: str = "WRatio",
    ) -> None:
        self.threshold = threshold
        self.scorer = scorer

    # ── Public API ────────────────────────────────────────────────────────────

    def match(
        self,
        query: str,
        candidates: List[str],
        top_n: int = 3,
    ) -> List[MatchResult]:
        """Return the top-*n* matches for *query* from *candidates*.

        Args:
            query:      The name to look up.
            candidates: List of candidate strings (employee names / codes).
            top_n:      Maximum number of results to return.

        Returns:
            List of ``(candidate, score, original_index)`` tuples, sorted by
            descending score, length at most *top_n*.
        """
        if not query or not candidates:
            return []

        if _BACKEND == "rapidfuzz":
            return self._match_rapidfuzz(query, candidates, top_n)
        if _BACKEND == "fuzzywuzzy":
            return self._match_fuzzywuzzy(query, candidates, top_n)
        return self._match_difflib(query, candidates, top_n)

    def best_match(
        self,
        query: str,
        candidates: List[str],
    ) -> Optional[MatchResult]:
        """Return the single best match, or ``None`` if below threshold.

        Args:
            query:      The name to look up.
            candidates: List of candidate strings.

        Returns:
            ``(candidate, score, index)`` or ``None``.
        """
        results = self.match(query, candidates, top_n=1)
        if results and results[0][1] >= self.threshold:
            return results[0]
        return None

    def is_match(self, query: str, candidate: str) -> bool:
        """Return ``True`` if *query* and *candidate* are similar enough.

        Args:
            query:     Query string.
            candidate: Candidate string.
        """
        result = self.best_match(query, [candidate])
        return result is not None

    # ── Backends ──────────────────────────────────────────────────────────────

    def _match_rapidfuzz(
        self, query: str, candidates: List[str], top_n: int
    ) -> List[MatchResult]:
        scorer_fn = getattr(rf_fuzz, self.scorer, rf_fuzz.WRatio)
        results = rf_process.extract(
            query,
            candidates,
            scorer=scorer_fn,
            limit=top_n,
        )
        return [(r[0], float(r[1]), r[2]) for r in results]

    def _match_fuzzywuzzy(
        self, query: str, candidates: List[str], top_n: int
    ) -> List[MatchResult]:
        scorer_fn = getattr(fw_fuzz, self.scorer, fw_fuzz.WRatio)
        results = fw_process.extract(query, candidates, scorer=scorer_fn, limit=top_n)
        return [
            (r[0], float(r[1]), candidates.index(r[0])) for r in results
        ]

    def _match_difflib(
        self, query: str, candidates: List[str], top_n: int
    ) -> List[MatchResult]:
        scored: list[MatchResult] = []
        for idx, cand in enumerate(candidates):
            ratio = difflib.SequenceMatcher(None, query.lower(), cand.lower()).ratio()
            scored.append((cand, ratio * 100, idx))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_n]
