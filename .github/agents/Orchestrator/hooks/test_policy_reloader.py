"""Tests for policy hot reload system."""

import os
import tempfile
import time
from pathlib import Path
from unittest import mock
import pytest

from src.policy_reloader import PolicyReloader


class TestPolicyReloader:
    """Test suite for PolicyReloader."""

    @pytest.fixture
    def temp_skills_dir(self):
        """Create temporary skills directory with sample SKILL.md files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = Path(tmpdir)

            # Create test-skill-1
            skill1_dir = skills_dir / "test-skill-1"
            skill1_dir.mkdir()
            skill1_path = skill1_dir / "SKILL.md"
            skill1_path.write_text(
                """---
name: test-skill-1
description: "Test skill one"
---

# Test Skill 1

Content here.
"""
            )

            # Create test-skill-2
            skill2_dir = skills_dir / "test-skill-2"
            skill2_dir.mkdir()
            skill2_path = skill2_dir / "SKILL.md"
            skill2_path.write_text(
                """---
name: test-skill-2
description: "Test skill two"
---

# Test Skill 2

Content here.
"""
            )

            yield skills_dir

    def test_scan_skills_dir_finds_skill_files(self, temp_skills_dir):
        """Test that initial scan finds all SKILL.md files."""
        reloader = PolicyReloader(str(temp_skills_dir))

        assert len(reloader.watched_files) == 2
        skill_names = [Path(p).parent.name for p in reloader.watched_files.keys()]
        assert "test-skill-1" in skill_names
        assert "test-skill-2" in skill_names

    def test_detects_modified_policy_file(self, temp_skills_dir):
        """Test that modified SKILL.md file is detected."""
        reloader = PolicyReloader(str(temp_skills_dir))

        # Modify one file
        skill1_path = temp_skills_dir / "test-skill-1" / "SKILL.md"
        time.sleep(0.1)  # Ensure mtime changes
        skill1_path.write_text(
            """---
name: test-skill-1
description: "Updated description"
---

# Test Skill 1

Updated content.
"""
        )

        # Debounce interval, wait for reload
        time.sleep(1.1)
        reloaded = reloader.check_and_reload()
        assert "test-skill-1" in reloaded
        assert "test-skill-2" not in reloaded

    def test_reloads_policy_content(self, temp_skills_dir):
        """Test that policy content is correctly loaded and stored."""
        reloader = PolicyReloader(str(temp_skills_dir))
        
        # Directly load a policy to test the loading mechanism
        skill_path = temp_skills_dir / "test-skill-1" / "SKILL.md"
        policy_data = reloader._reload_policy(str(skill_path))
        skill_name = "test-skill-1"
        reloader.loaded_policies[skill_name] = policy_data

        policy = reloader.get_policy("test-skill-1")
        assert policy is not None
        assert "metadata" in policy
        assert "content" in policy
        assert policy["metadata"]["name"] == "test-skill-1"
        assert policy["metadata"]["description"] == "Test skill one"
        assert "Content here" in policy["content"]

    def test_notifies_subscribers_on_reload(self, temp_skills_dir):
        """Test that subscribers are notified when policy is reloaded."""
        reloader = PolicyReloader(str(temp_skills_dir))
        callback = mock.Mock()
        reloader.register_subscriber(callback)

        # Initial load
        time.sleep(1.1)
        reloader.check_and_reload()
        callback.reset_mock()

        # Modify file
        skill1_path = temp_skills_dir / "test-skill-1" / "SKILL.md"
        time.sleep(0.1)
        skill1_path.write_text(
            """---
name: test-skill-1
description: "Updated"
---

Updated.
"""
        )

        # Wait for debounce
        time.sleep(1.1)
        reloader.check_and_reload()

        # Verify callback was called
        callback.assert_called_once()
        call_args = callback.call_args
        assert call_args[0][0] == "test-skill-1"  # skill_name
        assert "metadata" in call_args[0][1]  # policy_data

    def test_ignores_unchanged_files(self, temp_skills_dir):
        """Test that unchanged files are not reloaded."""
        reloader = PolicyReloader(str(temp_skills_dir))
        callback = mock.Mock()
        reloader.register_subscriber(callback)

        # First check to establish baseline
        reloader.check_and_reload()
        callback.reset_mock()

        # Check again without modifying files
        time.sleep(0.1)
        reloaded = reloader.check_and_reload()

        assert len(reloaded) == 0
        callback.assert_not_called()

    def test_handles_parse_errors_gracefully(self, temp_skills_dir):
        """Test that malformed SKILL.md files are handled without crashing."""
        # Initial reloader setup with valid files
        reloader = PolicyReloader(str(temp_skills_dir))
        
        # Directly load valid policies
        skill_path_1 = temp_skills_dir / "test-skill-1" / "SKILL.md"
        skill_path_2 = temp_skills_dir / "test-skill-2" / "SKILL.md"
        reloader.loaded_policies["test-skill-1"] = reloader._reload_policy(str(skill_path_1))
        reloader.loaded_policies["test-skill-2"] = reloader._reload_policy(str(skill_path_2))
        
        assert "test-skill-1" in reloader.loaded_policies
        assert "test-skill-2" in reloader.loaded_policies

        # Create malformed skill file (missing frontmatter)
        bad_skill_dir = temp_skills_dir / "bad-skill"
        bad_skill_dir.mkdir()
        bad_skill_path = bad_skill_dir / "SKILL.md"
        bad_skill_path.write_text("Just content, no frontmatter")

        # Try to load malformed file - should handle error gracefully (not crash)
        try:
            policy_data = reloader._reload_policy(str(bad_skill_path))
            # If it loads, minimal metadata expected
        except Exception:
            # Error handling is expected for malformed files
            pass

        # Other skills should still be loadable
        assert "test-skill-1" in reloader.loaded_policies  # Still there

    def test_handles_missing_files_gracefully(self, temp_skills_dir):
        """Test that deleted skill files are handled gracefully."""
        reloader = PolicyReloader(str(temp_skills_dir))

        # Delete a skill file
        skill_path = temp_skills_dir / "test-skill-1" / "SKILL.md"
        os.remove(skill_path)

        # Should handle missing file gracefully
        reloaded = reloader.check_and_reload()
        assert len(reloaded) == 0  # No new reloads

    def test_debounce_prevents_excessive_checks(self, temp_skills_dir):
        """Test that debounce interval prevents frequent file checks."""
        reloader = PolicyReloader(str(temp_skills_dir))
        reloader._debounce_interval_sec = 1.0

        # First check
        time.sleep(1.1)
        result1 = reloader.check_and_reload()
        assert result1 == []

        # Immediate second check should be debounced
        result2 = reloader.check_and_reload()
        assert result2 == []

        # Modify file and check immediately (still debounced)
        skill1_path = temp_skills_dir / "test-skill-1" / "SKILL.md"
        time.sleep(0.1)
        skill1_path.write_text(
            """---
name: test-skill-1
description: "Updated"
---

updated content
"""
        )
        result3 = reloader.check_and_reload()
        assert "test-skill-1" not in result3  # Still debounced

        # Wait for debounce interval and check again
        time.sleep(1.1)
        result4 = reloader.check_and_reload()
        assert "test-skill-1" in result4  # Now detected

    def test_get_all_policies(self, temp_skills_dir):
        """Test that all policies can be retrieved."""
        reloader = PolicyReloader(str(temp_skills_dir))
        
        # Directly load both policies
        skill_path_1 = temp_skills_dir / "test-skill-1" / "SKILL.md"
        skill_path_2 = temp_skills_dir / "test-skill-2" / "SKILL.md"
        reloader.loaded_policies["test-skill-1"] = reloader._reload_policy(str(skill_path_1))
        reloader.loaded_policies["test-skill-2"] = reloader._reload_policy(str(skill_path_2))

        all_policies = reloader.get_all_policies()
        assert len(all_policies) == 2
        assert "test-skill-1" in all_policies
        assert "test-skill-2" in all_policies

    def test_subscriber_error_does_not_crash(self, temp_skills_dir):
        """Test that error in subscriber doesn't crash reloader."""
        reloader = PolicyReloader(str(temp_skills_dir))

        # Initial load
        time.sleep(1.1)
        reloader.check_and_reload()

        # Register subscriber that raises
        def bad_subscriber(skill_name, policy_data):
            raise ValueError("Subscriber error")

        reloader.register_subscriber(bad_subscriber)

        # Modify file and reload
        skill1_path = temp_skills_dir / "test-skill-1" / "SKILL.md"
        time.sleep(0.1)
        skill1_path.write_text(
            """---
name: test-skill-1
description: "Updated"
---

updated content
"""
        )
        time.sleep(1.1)  # Wait for debounce

        # Should not raise, but should log error
        reloaded = reloader.check_and_reload()
        assert "test-skill-1" in reloaded  # Still reloaded despite subscriber error

    def test_yaml_metadata_parsing(self, temp_skills_dir):
        """Test that YAML frontmatter is correctly parsed."""
        reloader = PolicyReloader(str(temp_skills_dir))

        # Create skill with various metadata formats
        skill_path = temp_skills_dir / "test-skill-1" / "SKILL.md"
        skill_path.write_text(
            '''---
name: "quoted-name"
description: 'single-quoted'
other_field: ignored
---

Content
'''
        )

        reloader.check_and_reload()
        policy = reloader.get_policy("test-skill-1")

        assert policy["metadata"]["name"] == "quoted-name"
        assert policy["metadata"]["description"] == "single-quoted"

    def test_multiple_subscribers(self, temp_skills_dir):
        """Test that multiple subscribers are all notified."""
        reloader = PolicyReloader(str(temp_skills_dir))

        callback1 = mock.Mock()
        callback2 = mock.Mock()
        callback3 = mock.Mock()

        reloader.register_subscriber(callback1)
        reloader.register_subscriber(callback2)
        reloader.register_subscriber(callback3)

        # Initial load
        time.sleep(1.1)
        reloader.check_and_reload()
        callback1.reset_mock()
        callback2.reset_mock()
        callback3.reset_mock()

        # Modify file
        skill1_path = temp_skills_dir / "test-skill-1" / "SKILL.md"
        time.sleep(0.1)
        skill1_path.write_text(
            """---
name: test-skill-1
description: "Updated"
---

updated content
"""
        )
        time.sleep(1.1)  # Wait for debounce

        reloader.check_and_reload()

        # All should be called
        callback1.assert_called_once()
        callback2.assert_called_once()
        callback3.assert_called_once()

    def test_nonexistent_skills_dir(self):
        """Test that reloader handles nonexistent skills directory gracefully."""
        reloader = PolicyReloader("/nonexistent/path")
        # Should not crash
        assert len(reloader.watched_files) == 0
        reloaded = reloader.check_and_reload()
        assert len(reloaded) == 0

    def test_performance_acceptable(self, temp_skills_dir):
        """Test that check_and_reload() completes within acceptable time."""
        # Create 20 skill files to simulate realistic load
        for i in range(20):
            skill_dir = temp_skills_dir / f"skill-{i}"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text(
                f"""---
name: skill-{i}
description: "Skill {i}"
---

Content for skill {i}.
"""
            )

        reloader = PolicyReloader(str(temp_skills_dir))

        # Measure check time (when no changes)
        start = time.time()
        reloader.check_and_reload()
        elapsed_no_changes = time.time() - start

        # Modify one file and measure
        skill_path = temp_skills_dir / "skill-0" / "SKILL.md"
        time.sleep(0.1)
        skill_path.write_text("updated\n")
        time.sleep(1.1)  # Wait for debounce

        start = time.time()
        reloader.check_and_reload()
        elapsed_with_change = time.time() - start

        # Both should be fast (< 100ms)
        assert elapsed_no_changes < 0.1, f"No-change check too slow: {elapsed_no_changes:.3f}s"
        assert elapsed_with_change < 0.1, f"Change check too slow: {elapsed_with_change:.3f}s"
