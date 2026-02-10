from __future__ import annotations

from pathlib import Path
from typing import Any

import jinja2
import jinja2.ext
from jinja2.loaders import BaseLoader

from schemachange.JinjaEnvVar import JinjaEnvVar


class JinjaTemplateProcessor:
    _env_args = {
        "undefined": jinja2.StrictUndefined,
        "autoescape": False,
        "extensions": [JinjaEnvVar],
    }

    def __init__(self, project_root: Path, modules_folder: Path = None):
        loader: BaseLoader
        if modules_folder:
            loader = jinja2.ChoiceLoader(
                [
                    jinja2.FileSystemLoader(project_root),
                    jinja2.PrefixLoader({"modules": jinja2.FileSystemLoader(modules_folder)}),
                ]
            )
        else:
            loader = jinja2.FileSystemLoader(project_root)
        self.__environment = jinja2.Environment(loader=loader, **self._env_args)
        self.__project_root = project_root

    def list(self):
        return self.__environment.list_templates()

    def override_loader(self, loader: jinja2.BaseLoader):
        # to make unit testing easier
        self.__environment = jinja2.Environment(loader=loader, **self._env_args)

    def render(self, script: str, variables: dict[str, Any] | None) -> str:
        """
        Renders a Jinja template script with the provided variables.

        This method performs Jinja template rendering and basic cleanup (strip whitespace,
        remove trailing semicolon). It does NOT apply execution-time transformations like
        BOM removal or no-op statement appending - those are handled separately by
        prepare_script_for_execution() to preserve checksum compatibility.

        Args:
            script: Path to the script file (relative to project root)
            variables: Dictionary of variables to pass to Jinja template

        Returns:
            The rendered script content (suitable for checksum calculation)
        """
        if not variables:
            variables = {}
        # jinja needs posix path
        posix_path = Path(script).as_posix()
        template = self.__environment.get_template(posix_path)
        content = template.render(**variables).strip()
        content = content[:-1] if content.endswith(";") else content
        return content

    def relpath(self, file_path: Path):
        return file_path.relative_to(self.__project_root)
