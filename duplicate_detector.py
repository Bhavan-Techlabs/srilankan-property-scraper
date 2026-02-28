import logging
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)


class DuplicateDetector:
    """Detects duplicate/reposted ads by comparing description text similarity."""

    def __init__(self, threshold=0.9):
        self.threshold = threshold
        self._existing_entries = []  # list of (url, description) tuples

    def load_existing(self, rows):
        """
        Load existing sheet data for comparison.
        rows: list of dicts with at least 'URL' and 'Description' keys.
        """
        self._existing_entries = []
        for row in rows:
            url = row.get("URL", "").strip()
            desc = row.get("Description", "").strip()
            if url and desc:
                self._existing_entries.append((url, desc))
        logger.info("Loaded %d existing entries for duplicate detection", len(self._existing_entries))

    def check(self, url, description):
        """
        Check if an ad is a duplicate of any existing entry.

        Returns:
            (is_duplicate: bool, match_type: str, matching_url: str or None)
            match_type is 'url' for exact URL match, 'description' for text similarity match.
        """
        if not url:
            return False, "", None

        for existing_url, existing_desc in self._existing_entries:
            if url == existing_url:
                return True, "url", existing_url

        if not description or not description.strip():
            return False, "", None

        for existing_url, existing_desc in self._existing_entries:
            if not existing_desc:
                continue
            ratio = SequenceMatcher(None, description.strip(), existing_desc.strip()).ratio()
            if ratio >= self.threshold:
                logger.info(
                    "Duplicate found (%.1f%% match): %s matches %s",
                    ratio * 100, url, existing_url,
                )
                return True, "description", existing_url

        return False, "", None

    def add_entry(self, url, description):
        """Add a newly scraped entry to the in-memory index for intra-batch dedup."""
        if url and description:
            self._existing_entries.append((url.strip(), description.strip()))
