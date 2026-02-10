from __future__ import annotations

import json
import os
import pathlib

import pytest
from jinja2 import DictLoader
from jinja2.exceptions import UndefinedError

from schemachange.JinjaTemplateProcessor import JinjaTemplateProcessor


@pytest.fixture()
def processor() -> JinjaTemplateProcessor:
    return JinjaTemplateProcessor(pathlib.Path("."), None)


class TestJinjaTemplateProcessor:
    """Tests for JinjaTemplateProcessor.render() method.

    Note: Tests for BOM removal, empty content validation, comment-only validation,
    and trailing comment no-op appending have been moved to test_script_utils.py
    because those behaviors are now in prepare_script_for_execution().

    The render() method now only handles Jinja template rendering and basic cleanup
    (strip whitespace, remove trailing semicolon) to preserve checksum compatibility.
    """

    def test_render_simple_string(self, processor: JinjaTemplateProcessor):
        # override the default loader
        templates = {"test.sql": "some text"}
        processor.override_loader(DictLoader(templates))

        context = processor.render("test.sql", None)

        assert context == "some text"

    def test_render_simple_string_expecting_variable_that_does_not_exist_should_raise_exception(
        self, processor: JinjaTemplateProcessor
    ):
        # overide the default loader
        templates = {"test.sql": "some text {{ myvar }}"}
        processor.override_loader(DictLoader(templates))

        with pytest.raises(UndefinedError) as e:
            processor.render("test.sql", None)

        assert str(e.value) == "'myvar' is undefined"

    def test_render_simple_string_expecting_variable(self, processor: JinjaTemplateProcessor):
        # overide the default loader
        templates = {"test.sql": "Hello {{ myvar }}!"}
        processor.override_loader(DictLoader(templates))

        variables = json.loads('{"myvar" : "world"}')

        context = processor.render("test.sql", variables)

        assert context == "Hello world!"

    def test_render_from_subfolder(self, tmp_path: pathlib.Path):
        root_folder = tmp_path / "MORE2"

        root_folder.mkdir()
        script_folder = root_folder / "SQL"
        script_folder.mkdir()
        script_file = script_folder / "1.0.0_my_test.sql"
        script_file.write_text("Hello world!")

        processor = JinjaTemplateProcessor(root_folder, None)
        template_path = processor.relpath(script_file)

        context = processor.render(template_path, {})

        assert context == "Hello world!"

    def test_from_environ_not_set(self, processor: JinjaTemplateProcessor):
        # overide the default loader
        templates = {"test.sql": "some text {{ env_var('MYVAR') }}"}
        processor.override_loader(DictLoader(templates))

        with pytest.raises(ValueError) as e:
            processor.render("test.sql", None)

        assert str(e.value) == "Could not find environmental variable MYVAR and no default value was provided"

    def test_from_environ_set(self, processor: JinjaTemplateProcessor):
        # set MYVAR env variable
        os.environ["MYVAR"] = "myvar_from_environment"

        # overide the default loader
        templates = {"test.sql": "some text {{ env_var('MYVAR') }}"}
        processor.override_loader(DictLoader(templates))

        context = processor.render("test.sql", None)

        # unset MYVAR env variable
        del os.environ["MYVAR"]

        assert context == "some text myvar_from_environment"

    def test_from_environ_not_set_default(self, processor: JinjaTemplateProcessor):
        # overide the default loader
        templates = {"test.sql": "some text {{ env_var('MYVAR', 'myvar_default') }}"}
        processor.override_loader(DictLoader(templates))

        context = processor.render("test.sql", None)

        assert context == "some text myvar_default"

    def test_render_valid_content_with_jinja_conditional_should_succeed(self, processor: JinjaTemplateProcessor):
        """Test that valid content with Jinja conditionals works correctly."""
        templates = {
            "test.sql": """
            {% if deploy_env == 'prod' %}
            CREATE TABLE prod_table (id INT);
            {% else %}
            CREATE TABLE dev_table (id INT);
            {% endif %}
            """
        }
        processor.override_loader(DictLoader(templates))

        variables = {"deploy_env": "dev"}
        context = processor.render("test.sql", variables)

        assert "CREATE TABLE dev_table (id INT)" in context
        assert "prod_table" not in context

    def test_render_strips_trailing_semicolon(self, processor: JinjaTemplateProcessor):
        """Test that trailing semicolon is removed from rendered content."""
        templates = {"test.sql": "SELECT 1 FROM dual;"}
        processor.override_loader(DictLoader(templates))

        result = processor.render("test.sql", None)

        assert result == "SELECT 1 FROM dual"

    def test_render_strips_whitespace(self, processor: JinjaTemplateProcessor):
        """Test that leading/trailing whitespace is stripped."""
        templates = {"test.sql": "  \n  SELECT 1 FROM dual  \n  "}
        processor.override_loader(DictLoader(templates))

        result = processor.render("test.sql", None)

        assert result == "SELECT 1 FROM dual"

    def test_render_preserves_bom_for_checksum_compatibility(self, processor: JinjaTemplateProcessor):
        """Test that BOM is NOT stripped by render() - it's handled by prepare_script_for_execution().

        This ensures checksum compatibility: the checksum is calculated on the rendered content
        (which may include BOM), and BOM is stripped only before execution.
        """
        # \ufeff is the UTF-8 BOM (Byte Order Mark) character
        templates = {"test.sql": "\ufeffSELECT 1 FROM dual"}
        processor.override_loader(DictLoader(templates))

        result = processor.render("test.sql", None)

        # BOM should be preserved by render() for checksum compatibility
        assert result.startswith("\ufeff")

    def test_render_does_not_append_noop_for_trailing_comments(self, processor: JinjaTemplateProcessor):
        """Test that render() does NOT append no-op - that's done by prepare_script_for_execution().

        This ensures checksum compatibility: the checksum is calculated on the rendered content
        (without no-op), and no-op is appended only before execution.
        """
        templates = {"test.sql": "CREATE TABLE foo (id INT);\n-- Author: John Doe"}
        processor.override_loader(DictLoader(templates))

        result = processor.render("test.sql", None)

        # No-op should NOT be appended by render()
        assert "SELECT 1; -- schemachange: no-op statement" not in result
        # Original content preserved
        assert "CREATE TABLE foo (id INT)" in result
        assert "Author: John Doe" in result
