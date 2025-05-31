"""Pylint extension to check for functions returning parameters unchanged."""

from typing import TYPE_CHECKING

from astroid import nodes
from pylint.checkers import BaseChecker

if TYPE_CHECKING:
    from pylint.lint import PyLinter


class ParameterReturnChecker(BaseChecker):
    """Checker for functions that return parameters unchanged."""

    name = "parameter-return"
    msgs = {
        "W9003": (
            "Function returns parameter '%s' unchanged",
            "return-parameter-unchanged",
            "Consider if returning the parameter unchanged is necessary. "
            "This might indicate the parameter could be processed differently "
            "or the function design could be simplified.",
        ),
    }

    def visit_functiondef(self, node: nodes.FunctionDef) -> None:
        """Check function definitions for returned parameters."""
        if not node.args or not node.args.args:
            return

        # Get parameter names (excluding 'self')
        param_names = {arg.name for arg in node.args.args if arg.name != "self"}

        # Check if function has any substantial logic beyond just returning
        if self._has_substantial_logic(node):
            # If function has substantial logic, assume parameters might be modified
            return

        # Check all return statements for simple cases
        for child in node.nodes_of_class(nodes.Return):
            if child.value:
                self._check_return_value(child.value, param_names, child)

    def _has_substantial_logic(self, node: nodes.FunctionDef) -> bool:
        """Check if function has substantial logic that might modify parameters."""
        # Count non-trivial statements (excluding docstrings and simple returns)
        statements = []

        for child in node.body:
            if isinstance(child, nodes.Expr):
                # Skip docstrings (string expressions)
                if isinstance(child.value, nodes.Const) and isinstance(
                    child.value.value, str
                ):
                    continue
            elif isinstance(child, nodes.Return):
                # Skip simple return statements for now
                continue
            elif isinstance(child, nodes.Pass):
                # Skip pass statements
                continue

            statements.append(child)

        # If there are any non-trivial statements, assume the function might modify parameters
        if statements:
            return True

        # Additional checks for modification patterns
        for child in node.nodes_of_class(
            (
                nodes.Assign,
                nodes.AnnAssign,
                nodes.AugAssign,
                nodes.Call,
                nodes.For,
                nodes.While,
                nodes.If,
            )
        ):
            if isinstance(child, nodes.Assign | nodes.AnnAssign | nodes.AugAssign):
                # Any assignment might modify parameters
                return True
            elif isinstance(child, nodes.Call):
                # Method calls might modify parameters
                if isinstance(child.func, nodes.Attribute):
                    return True
            elif isinstance(child, nodes.For | nodes.While | nodes.If):
                # Control flow suggests non-trivial logic
                return True

        return False

    def _check_return_value(self, return_value, param_names, return_node):
        """Check if return value contains unchanged parameters."""
        if isinstance(return_value, nodes.Name):
            # Simple return: return param
            if return_value.name in param_names:
                self.add_message(
                    "return-parameter-unchanged",
                    node=return_node,
                    args=(return_value.name,),
                )
        elif isinstance(return_value, nodes.Tuple | nodes.List):
            # Tuple/list return: return (x, param, y)
            for element in return_value.elts:
                if isinstance(element, nodes.Name) and element.name in param_names:
                    self.add_message(
                        "return-parameter-unchanged",
                        node=return_node,
                        args=(element.name,),
                    )
        elif isinstance(return_value, nodes.Dict):
            # Dict return: return {"key": param}
            for value in return_value.values:
                if isinstance(value, nodes.Name) and value.name in param_names:
                    self.add_message(
                        "return-parameter-unchanged",
                        node=return_node,
                        args=(value.name,),
                    )


def register(linter: "PyLinter") -> None:
    """Register the checker with pylint."""
    linter.register_checker(ParameterReturnChecker(linter))
