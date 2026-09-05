import logging
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)


class DuplicateDetector:
    """Detects duplicate/reposted ads by comparing title text similarity."""

    def __init__(self, threshold=0.9):
        self.threshold = threshold
        self._existing_entries = []  # list of (url, title) tuples

    def load_existing(self, rows):
        """
        Load existing sheet data for comparison.
        rows: list of dicts with at least 'URL' and 'Title' keys.
        """
        self._existing_entries = []
        for row in rows:
            url = row.get("URL", "").strip()
            title = row.get("Title", "").strip()
            if url and title:
                self._existing_entries.append((url, title))
        logger.info("Loaded %d existing entries for duplicate detection", len(self._existing_entries))

    def check(self, url, title):
        """
        Check if an ad is a duplicate of any existing entry.

        Returns:
            (is_duplicate: bool, match_type: str, matching_url: str or None)
            match_type is 'url' for exact URL match, 'title' for text similarity match.
        """
        if not url:
            return False, "", None

        for existing_url, existing_title in self._existing_entries:
            if url == existing_url:
                return True, "url", existing_url

        if not title or not title.strip():
            return False, "", None

        for existing_url, existing_title in self._existing_entries:
            if not existing_title:
                continue
            ratio = SequenceMatcher(None, title.strip(), existing_title.strip()).ratio()
            if ratio >= self.threshold:
                logger.info(
                    "Duplicate found (%.1f%% match): %s matches %s",
                    ratio * 100, url, existing_url,
                )
                return True, "title", existing_url

        return False, "", None

    def add_entry(self, url, title):
        """Add a newly scraped entry to the in-memory index for intra-batch dedup."""
        if url and title:
            self._existing_entries.append((url.strip(), title.strip()))
