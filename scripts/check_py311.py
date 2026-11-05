"""Find f-string syntax that needs Python 3.12+ (Databricks Apps run Python 3.11): a backslash or the
enclosing quote character inside a {...} expression."""

import ast
import sys
from pathlib import Path


def problems(path: Path) -> list[str]:
    src = path.read_text()
    out = []
    for node in ast.walk(ast.parse(src)):
        if not isinstance(node, ast.JoinedStr):
            continue
        whole = ast.get_source_segment(src, node) or ""
        body = whole.lstrip("rRbBfF")
        quote = body[:3] if body[:3] in ('"""', "'''") else body[:1]  # a single quote is fine inside ''' or """
        for part in node.values:
            if isinstance(part, ast.FormattedValue):
                expr = ast.get_source_segment(src, part.value) or ""
                if "\\" in expr or (quote and quote in expr):
                    out.append(f"{path}:{part.value.lineno}: {expr[:80]}")
    return out


if __name__ == "__main__":
    found = [p for f in sys.argv[1:] for p in problems(Path(f))]
    print("\n".join(found) or "ok")
    sys.exit(1 if found else 0)
