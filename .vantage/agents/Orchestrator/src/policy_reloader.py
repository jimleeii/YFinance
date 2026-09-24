"""Policy Hot Reload System.

Watches skill policy files (SKILL.md) for changes and reloads them without
requiring agent restart. Enables rapid iteration on policy changes during
development and debugging.
"""

import os
import re
import logging
from pathlib import Path
from typing import Dict, List, Callable, Optional, Any
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class PolicyReloader:
    """Watch policy files and reload on change.

    Monitors all SKILL.md files in the skills directory and reloads them
    when modified. Notifies subscribers of policy changes.

    Usage:
        reloader = PolicyReloader(skills_dir=".github/agents/Orchestrator/skills")
        reloader.register_subscriber(on_policy_reload)
        reloader.check_and_reload()  # Call periodically
    """

    def __init__(self, skills_dir: str):
        """Initialize the policy reloader.

        Args:
            skills_dir: Path to the skills directory containing SKILL.md files.
        """
        self.skills_dir = Path(skills_dir)
        self.watched_files: Dict[str, float] = {}  # path → mtime
        self.loaded_policies: Dict[str, Dict[str, Any]] = {}  # skill_name → policy data
        self.subscribers: List[Callable[[str, Dict[str, Any]], None]] = []
        self.last_check_time: Optional[datetime] = None
        self._debounce_interval_sec = 1.0  # Minimum time between checks
        self._scan_skills_dir()

    def _scan_skills_dir(self):
        """Find all SKILL.md files and record their mtimes."""
        if not self.skills_dir.exists():
            logger.warning(f"Skills directory does not exist: {self.skills_dir}")
            return

        for skill_path in self.skills_dir.glob("*/SKILL.md"):
            try:
                mtime = os.path.getmtime(str(skill_path))
                self.watched_files[str(skill_path)] = mtime
                logger.debug(f"Watching skill: {skill_path.parent.name}")
            except OSError as e:
                logger.warning(f"Failed to stat {skill_path}: {e}")

    def check_and_reload(self) -> List[str]:
        """Check for modified policies and reload them.

        Returns:
            List of skill names that were reloaded.

        This method is safe to call frequently. It debounces checks to avoid
        excessive file I/O.
        """
        now = datetime.now(timezone.utc)

        # Debounce: skip if last check was recent
        if self.last_check_time:
            elapsed = (now - self.last_check_time).total_seconds()
            if elapsed < self._debounce_interval_sec:
                return []

        self.last_check_time = now
        reloaded = []

        for file_path, last_mtime in list(self.watched_files.items()):
            if not os.path.exists(file_path):
                logger.debug(f"Watched file no longer exists: {file_path}")
                continue

            try:
                current_mtime = os.path.getmtime(file_path)
            except OSError as e:
                logger.warning(f"Failed to stat {file_path}: {e}")
                continue

            if current_mtime > last_mtime:
                skill_name = Path(file_path).parent.name
                try:
                    policy_data = self._reload_policy(file_path)
                    self.watched_files[file_path] = current_mtime
                    self.loaded_policies[skill_name] = policy_data
                    reloaded.append(skill_name)

                    logger.info(f"✓ Reloaded policy: {skill_name}")
                    self._notify_subscribers(skill_name, policy_data)
                except Exception as e:
                    logger.error(f"✗ Failed to reload {skill_name}: {e}", exc_info=True)

        return reloaded

    def _reload_policy(self, file_path: str) -> Dict[str, Any]:
        """Load and parse a SKILL.md file.

        Args:
            file_path: Path to the SKILL.md file.

        Returns:
            Dictionary with 'metadata', 'content', and 'loaded_at' keys.

        Raises:
            ValueError: If file format is invalid.
            IOError: If file cannot be read.
        """
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Parse YAML frontmatter (delimited by ---)
        parts = content.split("---")
        if len(parts) < 3:
            raise ValueError(
                f"Invalid SKILL.md format: expected YAML frontmatter. File: {file_path}"
            )

        frontmatter_text = parts[1]
        body = "---".join(parts[2:]).strip()

        # Parse YAML metadata (simplified — extract key fields)
        metadata = self._parse_yaml_metadata(frontmatter_text)

        return {
            "metadata": metadata,
            "content": body,
            "file_path": file_path,
            "loaded_at": datetime.now(timezone.utc).isoformat(),
        }

    def _parse_yaml_metadata(self, yaml_text: str) -> Dict[str, str]:
        """Parse basic YAML metadata from frontmatter.

        Extracts name and description fields. Does not use full YAML parser
        for simplicity and to avoid heavy dependencies.

        Args:
            yaml_text: YAML frontmatter text.

        Returns:
            Dictionary of key-value pairs.
        """
        metadata = {}

        # Extract name
        name_match = re.search(r'^name\s*:\s*["\']?([^"\'\n]+)["\']?$', yaml_text, re.MULTILINE)
        if name_match:
            metadata["name"] = name_match.group(1).strip()

        # Extract description
        desc_match = re.search(
            r'^description\s*:\s*["\']([^"\']*)["\']', yaml_text, re.MULTILINE
        )
        if desc_match:
            metadata["description"] = desc_match.group(1).strip()

        return metadata

    def register_subscriber(
        self, callback: Callable[[str, Dict[str, Any]], None]
    ) -> None:
        """Subscribe to policy reload events.

        Args:
            callback: Function called on reload. Signature: (skill_name, policy_data) -> None
        """
        self.subscribers.append(callback)

    def _notify_subscribers(self, skill_name: str, policy_data: Dict[str, Any]) -> None:
        """Notify all subscribers of a policy reload.

        Args:
            skill_name: Name of the skill that was reloaded.
            policy_data: Policy data (metadata, content, etc).
        """
        for callback in self.subscribers:
            try:
                callback(skill_name, policy_data)
            except Exception as e:
                logger.error(f"Subscriber callback error for {skill_name}: {e}", exc_info=True)

    def get_policy(self, skill_name: str) -> Optional[Dict[str, Any]]:
        """Get loaded policy for a skill.

        Args:
            skill_name: Name of the skill (directory name).

        Returns:
            Policy data dict, or None if not loaded.
        """
        return self.loaded_policies.get(skill_name)

    def get_all_policies(self) -> Dict[str, Dict[str, Any]]:
        """Get all loaded policies.

        Returns:
            Dictionary mapping skill names to policy data.
        """
        return dict(self.loaded_policies)
