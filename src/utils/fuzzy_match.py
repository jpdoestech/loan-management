"""Fuzzy employee name matching — rapidfuzz preferred, difflib fallback."""
from __future__ import annotations
from typing import List, Tuple

try:
    from rapidfuzz import process as _rf_process, fuzz as _rf_fuzz
    _RAPIDFUZZ = True
except ImportError:
    _RAPIDFUZZ = False
    import difflib

# Default similarity threshold (0-100 scale)
DEFAULT_THRESHOLD: float = 89.0


class FuzzyMatcher:
    """Wraps rapidfuzz (or difflib) for employee name matching.

    All scores are on a 0-100 scale regardless of backend.
    """

    def __init__(self, threshold: float = DEFAULT_THRESHOLD) -> None:
        """Initialise with a configurable similarity *threshold* (0-100)."""
        self.threshold = threshold

    def match(
        self,
        query: str,
        candidates: List[str],
        top_n: int = 3,
    ) -> List[Tuple[str, float, int]]:
        """Return the top *top_n* matches for *query* against *candidates*.

        Returns:
            List of (candidate, score, index) tuples, highest score first.
            Score is 0-100. Index is the position in *candidates*.
        """
        if not candidates or not query:
            return []

        if _RAPIDFUZZ:
            results = _rf_process.extract(
                query,
                candidates,
                scorer=_rf_fuzz.token_sort_ratio,
                limit=top_n,
            )
            # rapidfuzz returns (match, score, index)
            return [(m, float(s), i) for m, s, i in results]
        else:
            # difflib fallback — SequenceMatcher gives 0.0-1.0
            scored = []
            for idx, cand in enumerate(candidates):
                ratio = difflib.SequenceMatcher(None, query.lower(), cand.lower()).ratio()
                scored.append((cand, ratio * 100, idx))
            scored.sort(key=lambda x: x[1], reverse=True)
            return scored[:top_n]

    def best_match(
        self,
        query: str,
        candidates: List[str],
    ) -> Tuple[str, float, int] | None:
        """Return the single best match, or None if candidates is empty."""
        results = self.match(query, candidates, top_n=1)
        return results[0] if results else None

    def is_match(self, query: str, candidates: List[str]) -> bool:
        """Return True if the best score meets or exceeds the threshold."""
        result = self.best_match(query, candidates)
        return result is not None and result[1] >= self.threshold

    @staticmethod
    def backend() -> str:
        """Return the name of the active matching backend."""
        return "rapidfuzz" if _RAPIDFUZZ else "difflib"
