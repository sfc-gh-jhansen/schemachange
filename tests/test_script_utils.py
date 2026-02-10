"""Tests for schemachange.script_utils module."""

from __future__ import annotations

import pytest

from schemachange.script_utils import prepare_script_for_execution


class TestPrepareScriptForExecution:
    """Tests for prepare_script_for_execution() function."""

    def test_simple_sql_unchanged(self):
        """Test that simple SQL passes through unchanged."""
        content = "SELECT 1 FROM dual"
        result = prepare_script_for_execution(content, "test.sql")
        assert result == "SELECT 1 FROM dual"

    def test_multiline_sql_unchanged(self):
        """Test that multi-line SQL without trailing comments passes unchanged."""
        content = "DROP VIEW IF EXISTS foo;\nCREATE VIEW foo AS SELECT * FROM bar"
        result = prepare_script_for_execution(content, "test.sql")
        assert result == content

    # UTF-8 BOM handling tests (issue #250)

    def test_strips_utf8_bom_character(self):
        """Test that UTF-8 BOM character is automatically stripped - issue #250"""
        # \ufeff is the UTF-8 BOM (Byte Order Mark) character
        content = "\ufeffSELECT 1 FROM dual"
        result = prepare_script_for_execution(content, "test.sql")

        assert not result.startswith("\ufeff")
        assert result == "SELECT 1 FROM dual"

    def test_strips_utf8_bom_with_multiline_sql(self):
        """Test that UTF-8 BOM is stripped from multi-line SQL - issue #250"""
        content = "\ufeff-- Comment\nCREATE TABLE foo (id INT);\nSELECT * FROM foo"
        result = prepare_script_for_execution(content, "test.sql")

        # BOM should be stripped, rest preserved (but no-op appended due to trailing comment)
        assert not result.startswith("\ufeff")
        assert "-- Comment" in result
        assert "CREATE TABLE foo (id INT)" in result

    def test_handles_bom_in_middle_of_file(self):
        """Test that BOM in middle of file is not stripped - only leading BOM - issue #250"""
        content = "SELECT '\ufeff' AS bom_char FROM dual"
        result = prepare_script_for_execution(content, "test.sql")

        # Leading BOM removed but BOM in SQL string preserved
        assert not result.startswith("\ufeff")
        assert "'\ufeff'" in result

    # Empty content validation tests (issue #258)

    def test_empty_content_only_whitespace_should_raise_error(self):
        """Test that only whitespace raises ValueError - issue #258"""
        content = "   \n\t  \n   "
        with pytest.raises(ValueError) as e:
            prepare_script_for_execution(content, "test.sql")

        assert "rendered to empty SQL content" in str(e.value)

    def test_empty_string_should_raise_error(self):
        """Test that empty string raises ValueError."""
        with pytest.raises(ValueError) as e:
            prepare_script_for_execution("", "test.sql")

        assert "rendered to empty SQL content" in str(e.value)

    # Comment-only content validation tests (issue #258)

    def test_only_single_line_comments_should_raise_error(self):
        """Test that rendering only SQL comments raises ValueError - issue #258"""
        content = "-- This is a comment\n-- Another comment"
        with pytest.raises(ValueError) as e:
            prepare_script_for_execution(content, "test.sql")

        error_message = str(e.value)
        assert "contains only SQL comments" in error_message
        assert "To fix:" in error_message

    def test_only_multiline_comment_should_raise_error(self):
        """Test that rendering only multi-line comments raises ValueError - issue #258"""
        content = "/* This is a \nmulti-line comment */"
        with pytest.raises(ValueError) as e:
            prepare_script_for_execution(content, "test.sql")

        assert "contains only SQL comments" in str(e.value)

    def test_mixed_comments_only_should_raise_error(self):
        """Test that mixed comment types without SQL raises ValueError - issue #258"""
        content = "-- Single line\n/* Multi-line */\n-- Another line"
        with pytest.raises(ValueError) as e:
            prepare_script_for_execution(content, "test.sql")

        assert "contains only SQL comments" in str(e.value)

    # Trailing comment no-op appending tests (issue #258)

    def test_valid_sql_with_trailing_comment_appends_noop(self):
        """Test that valid SQL with trailing comment gets no-op statement appended - issue #258"""
        content = "CREATE TABLE foo (id INT);\n-- Author: John Doe\n-- Ticket: JIRA-123"
        result = prepare_script_for_execution(content, "test.sql")

        # Original SQL is preserved
        assert "CREATE TABLE foo (id INT)" in result
        # Metadata comments are preserved
        assert "Author: John Doe" in result
        assert "Ticket: JIRA-123" in result
        # No-op statement is appended
        assert "SELECT 1; -- schemachange: no-op statement" in result

    def test_valid_sql_with_trailing_multiline_comment_appends_noop(self):
        """Test that valid SQL ending with multi-line comment gets no-op appended - issue #258"""
        content = "CREATE TABLE bar (id INT);\n/* Metadata block */"
        result = prepare_script_for_execution(content, "test.sql")

        assert "CREATE TABLE bar (id INT)" in result
        assert "/* Metadata block */" in result
        assert "SELECT 1; -- schemachange: no-op statement" in result

    def test_valid_sql_with_inline_comment_no_noop(self):
        """Test that valid SQL with inline comment does not get no-op - issue #258"""
        content = "SELECT 1 /* inline comment */ FROM dual"
        result = prepare_script_for_execution(content, "test.sql")

        assert "SELECT 1" in result
        assert "FROM dual" in result
        # Should NOT append SELECT 1 because last line is not a comment-only line
        assert "no-op statement" not in result

    def test_valid_sql_without_trailing_comment_unchanged(self):
        """Test that valid SQL without trailing comment passes through unchanged - issue #258"""
        content = "DROP VIEW IF EXISTS foo;\nCREATE VIEW foo AS SELECT * FROM bar"
        result = prepare_script_for_execution(content, "test.sql")

        assert result == content
        assert "SELECT 1" not in result

    # Combined BOM + trailing comment test

    def test_bom_and_trailing_comment_handled_together(self):
        """Test that BOM is stripped AND trailing comment gets no-op - issues #250, #258"""
        content = "\ufeffCREATE TABLE test (id INT);\n-- End of script"
        result = prepare_script_for_execution(content, "test.sql")

        # BOM stripped
        assert not result.startswith("\ufeff")
        # Original SQL preserved
        assert "CREATE TABLE test (id INT)" in result
        # Comment preserved
        assert "End of script" in result
        # No-op appended
        assert "SELECT 1; -- schemachange: no-op statement" in result
