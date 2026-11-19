"""Small Decimal expression parser; never executes Python expressions."""

import re
from decimal import Decimal, DecimalException, localcontext

TOKEN = re.compile(r"\s*(\d+(?:\.\d*)?|\.\d+|[()+*/-])")


def calculate(expression):
    if not isinstance(expression, str) or not 0 < len(expression) <= 512:
        raise ValueError("Invalid expression")
    expression = expression.strip()
    tokens, pos = [], 0
    while pos < len(expression):
        match = TOKEN.match(expression, pos)
        if not match:
            raise ValueError("Invalid expression")
        token = match.group(1)
        if len(token) > 128:
            raise ValueError("Literal too long")
        tokens.append(token)
        pos = match.end()
    if not tokens or len(tokens) > 128:
        raise ValueError("Invalid expression")
    index = 0

    def bounded(value):
        if not value.is_finite() or (value and abs(value.adjusted()) > 100):
            raise ValueError("Result out of bounds")
        return value

    def atom(depth):
        nonlocal index
        if depth > 16 or index >= len(tokens):
            raise ValueError("Invalid expression")
        token = tokens[index]
        index += 1
        if token in ("+", "-"):
            value = atom(depth + 1)
            return value if token == "+" else -value
        if token == "(":
            value = expr(depth + 1)
            if index >= len(tokens) or tokens[index] != ")":
                raise ValueError("Unclosed parentheses")
            index += 1
            return value
        if token in (")", "*", "/"):
            raise ValueError("Expected number")
        return bounded(Decimal(token))

    def term(depth):
        nonlocal index
        value = atom(depth)
        while index < len(tokens) and tokens[index] in ("*", "/"):
            op = tokens[index]
            index += 1
            right = atom(depth)
            value = bounded(value * right if op == "*" else value / right)
        return value

    def expr(depth):
        nonlocal index
        value = term(depth)
        while index < len(tokens) and tokens[index] in ("+", "-"):
            op = tokens[index]
            index += 1
            right = term(depth)
            value = bounded(value + right if op == "+" else value - right)
        return value

    try:
        with localcontext() as context:
            context.prec = 50
            result = expr(0)
            if index != len(tokens):
                raise ValueError("Unexpected token")
            return format(result if result else Decimal(0), "f")
    except DecimalException as exc:
        raise ValueError("Invalid arithmetic") from exc
