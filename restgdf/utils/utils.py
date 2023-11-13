import re
from collections.abc import Iterable

ends_with_num_pat = re.compile(r"\d+$")


def ends_with_num(url: str) -> bool:
    """Return True if the given URL ends with a number."""
    return bool(ends_with_num_pat.search(url))


def where_var_in_list(var: str, vals: Iterable[str]) -> str:
    """Return a where clause for a variable in a list of values."""
    vals_str = ", ".join(f"'{val}'" for val in vals)
    return f"{var} In ({vals_str})"
