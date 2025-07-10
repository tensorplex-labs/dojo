"""Custom Pylint checker for import rules."""

import os

import astroid
from pylint import checkers
from pylint.checkers import utils

# Custom Plugin Ranges
# Recommended ranges for custom plugins:
#
# C9000-C9999: Custom convention messages
# R9000-R9999: Custom refactoring messages
# W9000-W9999: Custom warning messages
# E9000-E9999: Custom error messages
# F9000-F9999: Custom fatal messages


class ImportRulesChecker(checkers.BaseChecker):
    """Custom checker for import rules."""

    name = "custom-import-rules"
    priority = -1

    msgs = {
        "E9001": (
            'Import "%s" not found in __all__ of module "%s"',
            "import-not-in-all",
            "Used when importing a name that is not declared in the source module's __all__",
        ),
        "E9002": (
            'Import "%s.%s" should be imported from "%s" instead',
            "prefer-shorter-import",
            "Used when a symbol is imported from a deep module but available from a higher level",
        ),
    }

    options = (
        (
            "local-import-prefixes",
            {
                "default": "",
                "type": "csv",
                "metavar": "<comma-separated-list>",
                "help": "Comma-separated list of module prefixes to consider as local modules "
                "(e.g., commons,database,dojo,neurons). If empty, will auto-detect from "
                "top-level directories.",
            },
        ),
    )

    def __init__(self, linter=None):
        super().__init__(linter)
        self.module_all_cache = {}
        self._local_prefixes = None

    def open(self):
        """Called at the beginning of a pylint run."""
        # Get configured prefixes or auto-detect
        configured_prefixes = self.linter.config.local_import_prefixes
        if configured_prefixes:
            self._local_prefixes = tuple(configured_prefixes)
        else:
            self._local_prefixes = self._auto_detect_local_prefixes()

    def _auto_detect_local_prefixes(self):
        """Auto-detect local module prefixes from top-level directories."""
        try:
            # Get current working directory (where pylint is run)
            cwd = os.getcwd()

            # Get all top-level Python packages (directories with __init__.py)
            prefixes = []
            for item in os.listdir(cwd):
                item_path = os.path.join(cwd, item)
                if (
                    os.path.isdir(item_path)
                    and not item.startswith(".")
                    and not item.startswith("_")
                    and item
                    not in (
                        "venv",
                        "env",
                        "node_modules",
                        "build",
                        "dist",
                        "__pycache__",
                    )
                ):
                    # Check if it's a Python package or contains Python files
                    init_file = os.path.join(item_path, "__init__.py")
                    has_py_files = any(
                        f.endswith(".py")
                        for f in os.listdir(item_path)
                        if os.path.isfile(os.path.join(item_path, f))
                    )

                    if os.path.exists(init_file) or has_py_files:
                        prefixes.append(item)

            return tuple(prefixes) if prefixes else ("src",)  # fallback

        except (OSError, PermissionError):
            # Fallback to common patterns if auto-detection fails
            return ("src", "app", "lib", "core")

    def _get_module_all(self, module_name):
        """Get the __all__ list for a module if it exists."""
        if module_name in self.module_all_cache:
            return self.module_all_cache[module_name]

        try:
            module = astroid.MANAGER.ast_from_module_name(module_name)
            all_list = self._extract_all_from_module(module)
            self.module_all_cache[module_name] = all_list
            return all_list

        except astroid.AstroidImportError:
            self.module_all_cache[module_name] = None
            return None

    def _extract_all_from_module(self, module):
        """Extract __all__ list from module AST."""
        for node in module.body:
            if self._is_all_assignment(node):
                return self._get_all_values(node.value)
        return None

    def _is_all_assignment(self, node):
        """Check if node is an __all__ assignment."""
        return (
            isinstance(node, astroid.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], astroid.AssignName)
            and node.targets[0].name == "__all__"
        )

    def _get_all_values(self, value_node):
        """Extract string values from __all__ list/tuple."""
        if not isinstance(value_node, astroid.List | astroid.Tuple):
            return None
        all_list = []
        for elt in value_node.elts:
            if isinstance(elt, astroid.Const) and isinstance(elt.value, str):
                all_list.append(elt.value)
        return all_list

    @utils.only_required_for_messages("import-not-in-all", "prefer-shorter-import")
    def visit_importfrom(self, node):
        """Check import from statements."""
        if not node.modname:
            return

        # Check both relative and absolute imports within your project
        # You can customize this logic based on your project structure
        if node.modname.startswith(".") or self._is_local_module(node.modname):
            # Check for prefer-shorter-import violations
            self._check_prefer_shorter_import(node)

            # Get the __all__ list for the source module
            all_list = self._get_module_all(node.modname)
            if all_list is None:
                return  # No __all__ defined or module not found

            # Check each imported name
            for name, _ in node.names:
                if name == "*":
                    continue  # Skip wildcard imports

                if name not in all_list:
                    self.add_message(
                        "import-not-in-all", node=node, args=(name, node.modname)
                    )

    def _check_prefer_shorter_import(self, node):
        """Check if imports should come from a higher-level module."""
        module_parts = node.modname.split(".")

        # Check all possible parent modules (from immediate parent up to root)
        for i in range(len(module_parts) - 1, 0, -1):
            parent_module = ".".join(module_parts[:i])

            # Skip if parent module is not local to avoid checking external libraries
            if not self._is_local_module(parent_module):
                continue

            parent_all = self._get_module_all(parent_module)
            if parent_all:
                for name, _ in node.names:
                    if name in parent_all:
                        self.add_message(
                            "prefer-shorter-import",
                            node=node,
                            args=(node.modname, name, parent_module),
                        )
                        # Only report the shortest possible import path
                        break
                # If we found a parent with __all__, we don't need to check higher levels
                # for this particular import (to avoid duplicate warnings)
                if any(name in parent_all for name, _ in node.names):
                    break

    def _get_all_parent_modules(self, module_name):
        """Get all parent modules of a given module."""
        parts = module_name.split(".")
        parents = []
        for i in range(len(parts) - 1, 0, -1):
            parent = ".".join(parts[:i])
            parents.append(parent)
        return parents

    def _is_local_module(self, module_name):
        """Check if a module is part of your local project."""
        return any(module_name.startswith(prefix) for prefix in self._local_prefixes)


def register(linter):
    """Register the checker."""
    linter.register_checker(ImportRulesChecker(linter))
