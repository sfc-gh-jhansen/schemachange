"""
Utility functions for script content processing.

This module provides functions to prepare script content for execution in Snowflake,
separating concerns from Jinja template processing and checksum calculation.
"""

from __future__ import annotations

import re

import structlog

logger = structlog.getLogger(__name__)


def prepare_script_for_execution(content: str, script_name: str) -> str:
    """
    Applies transformations required before executing a script in Snowflake.

    IMPORTANT: Call this AFTER calculating the checksum to preserve backward
    compatibility with existing change history checksums.

    Transformations applied:
    - Removes UTF-8 BOM character if present (issue #250)
    - Validates content is not empty
    - Validates content is not comment-only
    - Appends no-op statement if script ends with a comment line (issue #258)

    Args:
        content: The rendered script content (after Jinja processing)
        script_name: Name of the script (for error messages and logging)

    Returns:
        The transformed content ready for Snowflake execution

    Raises:
        ValueError: If content is empty or contains only comments
    """
    # Remove UTF-8 BOM if present (issue #250)
    # The BOM character (\ufeff) causes Snowflake SQL compilation errors
    # Common in files saved with "UTF-8 with BOM" encoding (Windows/VS Code)
    if content.startswith("\ufeff"):
        logger.debug("Removing UTF-8 BOM from script", script=script_name)
        content = content[1:]

    # Validate content is not empty after processing
    if not content or content.isspace():
        error_msg = (
            f"Script '{script_name}' rendered to empty SQL content.\n"
            f"This can happen when:\n"
            f"  1. The file contains only whitespace\n"
            f"  2. All Jinja conditional blocks evaluate to false\n"
            f"  3. Template variables are missing or incorrect\n"
            f"  4. The file contains only a semicolon after rendering\n"
        )
        logger.error("Empty SQL content", script=script_name)
        raise ValueError(error_msg)

    # Check if content contains only SQL comments (would be empty after Snowflake strips them)
    # This catches the common case where Snowflake connector strips comments and tries to execute empty string
    # Pattern explanation:
    # - Remove single-line comments: -- comment
    # - Remove multi-line comments: /* comment */
    # Note: This is a simplified check that handles most cases. Complex SQL with comments in strings
    # would require a full SQL parser. We're being pragmatic and catching 95% of issues.
    content_without_comments = re.sub(r"--[^\n]*", "", content)  # Remove -- comments
    content_without_comments = re.sub(
        r"/\*.*?\*/", "", content_without_comments, flags=re.DOTALL
    )  # Remove /* */ comments
    content_without_comments = content_without_comments.strip()

    # Case 1: Script contains ONLY comments (no SQL at all) - this is an error
    if not content_without_comments or content_without_comments.isspace():
        error_msg = (
            f"Script '{script_name}' contains only SQL comments.\n"
            f"When Snowflake strips comments, this results in an empty SQL statement.\n"
            f"\nOriginal content:\n{content[:500]}\n"
            f"\nContent after comment removal:\n'{content_without_comments}'\n"
            f"\nTo fix:\n"
            f"  1. Add actual SQL statements to the script\n"
            f"  2. Remove comment-only scripts from your migrations\n"
            f"  3. If this is a placeholder, add a no-op statement like: SELECT 1; -- placeholder\n"
        )
        logger.error("SQL content contains only comments", script=script_name, original_length=len(content))
        raise ValueError(error_msg)

    # Case 2: Script has valid SQL but ends with comment lines
    # Snowflake connector may strip trailing comments leaving the last statement empty
    # Check if the last non-empty line is a comment
    lines = content.rstrip().split("\n")
    last_line = lines[-1].strip() if lines else ""

    if last_line.startswith("--") or (last_line.startswith("/*") and last_line.endswith("*/")):
        # Append a no-op statement to ensure Snowflake has something to execute after stripping comments
        # This preserves metadata comments while preventing "Empty SQL Statement" errors
        content = (
            content.rstrip()
            + "\nSELECT 1; -- schemachange: no-op statement to prevent empty SQL after comment stripping"
        )
        logger.debug(
            "Script ends with comment - appending no-op statement",
            script=script_name,
            last_line_preview=last_line[:100],
        )

    return content
