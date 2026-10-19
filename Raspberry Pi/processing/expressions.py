"""Free-form formulas over the named signals, e.g. ``pressure * exposure_15 / 300``.

The text is parsed with ``ast`` and only a small whitelist of nodes is walked - no eval, no attribute access, no
calls except the functions below. A result is a grid (when any cell signal is used) or one number. Like the weighted
indices these are engineering formulas the user writes, not validated scores.
"""

import ast
import operator

import numpy as np

from processing.signals import SIGNALS, WINDOWS_MIN, read_signal

MAX_LENGTH = 300
MAX_NODES = 80

FUNCTIONS = {
    "abs": np.abs, "sqrt": np.sqrt, "log": np.log, "exp": np.exp,
    "min": np.minimum, "max": np.maximum, "clip": np.clip, "where": np.where,
}
ARITY = {"abs": 1, "sqrt": 1, "log": 1, "exp": 1, "min": 2, "max": 2, "clip": 3, "where": 3}
BINARY = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
          ast.Pow: operator.pow, ast.Mod: operator.mod}
COMPARE = {ast.Gt: operator.gt, ast.GtE: operator.ge, ast.Lt: operator.lt, ast.LtE: operator.le,
           ast.Eq: operator.eq, ast.NotEq: operator.ne}
EXAMPLES = (
    "pressure",
    "pressure * exposure_15 / 300",
    "pressure / max(longest_hotspot, 1)",
    "where(pressure > 20, since_relief / 60, 0)",
    "burden * (1 - relief_percent_15 / 100)",
    "clip(loaded_time / 3600, 0, 1)",
    "active_hotspots + repositions_60",
)


def variables():
    """{name: (signal key, window in minutes or None)} for every name a formula may use"""
    names = {}
    for key, signal in SIGNALS.items():
        names[key] = (key, None)
        if signal.windowed:
            for minutes in WINDOWS_MIN:
                if minutes is not None:
                    names[f"{key}_{minutes}"] = (key, minutes)
    return names


class Expression:
    """A validated formula; evaluate() it against a signals Context"""

    def __init__(self, text, tree, used):
        self.text = text
        self._tree = tree
        self.used = used  # variable names the formula reads

    def evaluate(self, context):
        """A grid (NaN where unknown) or a float; None while there is no pressure frame"""
        if context.pressure is None:
            return None
        cache = {}

        def read(name):
            if name not in cache:
                key, minutes = variables()[name]
                cache[name] = np.asarray(read_signal(key, context, minutes), dtype=float)  # 0-d: x/0 gives inf, not an error
            return cache[name]

        with np.errstate(all="ignore"):
            value = self._walk(self._tree.body, read)
        value = np.asarray(value, dtype=float)
        value = np.where(np.isfinite(value), value, np.nan)
        return float(value) if value.ndim == 0 else value

    def _walk(self, node, read):
        if isinstance(node, ast.Constant):
            return np.float64(node.value)
        if isinstance(node, ast.Name):
            return read(node.id)
        if isinstance(node, ast.UnaryOp):
            value = self._walk(node.operand, read)
            return -value if isinstance(node.op, ast.USub) else value
        if isinstance(node, ast.BinOp):
            return BINARY[type(node.op)](self._walk(node.left, read), self._walk(node.right, read))
        if isinstance(node, ast.Compare):
            left, result = self._walk(node.left, read), True
            for op, right in zip(node.ops, node.comparators):
                right = self._walk(right, read)
                result = np.logical_and(result, COMPARE[type(op)](left, right))
                left = right
            return result.astype(float)
        if isinstance(node, ast.BoolOp):
            join = np.logical_and if isinstance(node.op, ast.And) else np.logical_or
            values = [self._walk(item, read) != 0 for item in node.values]
            result = values[0]
            for item in values[1:]:
                result = join(result, item)
            return result.astype(float)
        if isinstance(node, ast.IfExp):
            return np.where(self._walk(node.test, read) != 0, self._walk(node.body, read),
                            self._walk(node.orelse, read))
        # the only other node compile_expression lets through is a whitelisted Call
        return FUNCTIONS[node.func.id](*[self._walk(arg, read) for arg in node.args])


def compile_expression(text):
    """Parse and check a formula; raises ValueError with a message the user can act on"""
    text = (text or "").strip()
    if not text:
        raise ValueError("Type a formula, for example pressure * 2")
    if len(text) > MAX_LENGTH:
        raise ValueError(f"Formula is longer than {MAX_LENGTH} characters")
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as error:
        raise ValueError(f"Cannot read the formula (check the brackets and operators): {error.msg}") from error
    known, used = variables(), set()
    nodes = list(ast.walk(tree))
    if len(nodes) > MAX_NODES:
        raise ValueError("Formula is too long")
    for node in nodes:
        if isinstance(node, (ast.Expression, ast.Load, ast.UnaryOp, ast.USub, ast.UAdd, ast.BinOp, ast.Compare,
                             ast.BoolOp, ast.And, ast.Or, ast.IfExp, *BINARY, *COMPARE)):
            continue
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
                raise ValueError("Only numbers can be written in a formula")
        elif isinstance(node, ast.Name):
            if node.id in FUNCTIONS and not _is_function(tree, node):
                raise ValueError(f"'{node.id}' is a function: write {node.id}(...)")
            if node.id not in known and not _is_function(tree, node):
                raise ValueError(f"Unknown name '{node.id}' - pick one from the list")
            if node.id in known:
                used.add(node.id)
        elif isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in FUNCTIONS or node.keywords:
                raise ValueError("Only these functions can be called: " + ", ".join(FUNCTIONS))
            if len(node.args) != ARITY[node.func.id]:
                raise ValueError(f"{node.func.id}() takes {ARITY[node.func.id]} value(s)")
        else:
            raise ValueError(f"'{type(node).__name__}' is not allowed in a formula")
    return Expression(text, tree, used)


def _is_function(tree, name_node):
    return any(isinstance(node, ast.Call) and node.func is name_node for node in ast.walk(tree))
