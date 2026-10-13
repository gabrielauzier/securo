"""AD-004 guard: bulk writes to transactions must refresh the bills they touch.

Bill aggregates are stored (AD-003), so a write path that changes card rows or
bill payments without calling `bill_service` leaves them stale. This test scans
the source of `app/services` and `app/api` and fails when a function holds a
bulk `update(Transaction)` / `delete(Transaction)` statement, or applies rule
actions to existing rows, without also calling a bill refresh in the same
function. A function that is safe for another reason goes in `ALLOWED`, with
the reason.
"""

import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"
SCANNED = ("services", "api")

# Calls that recompute stored bill aggregates.
REFRESH_CALLS = {
    "touch",
    "refresh_bills",
    "refresh_workspace_bills",
    "link_account_transactions",
    "relink_account",
    "_sync_card_bills",
    "_sync_account_bills",
}
# Core statement builders, under their usual import names.
BULK_BUILDERS = {"update", "delete", "sa_update", "sa_delete"}
# In-place mutators that set `category_id` / `is_ignored` on a transaction.
ROW_MUTATORS = {"apply_rule_actions"}

# "module:function" -> why it needs no bill refresh of its own.
ALLOWED = {
    "services/admin_service.py:delete_user":
        "deletes the user's accounts in the same call; their bills cascade with them",
    "services/bill_service.py:delete_bill":
        "unlinks rows from the bill it deletes; no stored aggregate is left to refresh",
    "services/import_service.py:enrich_with_category_suggestions":
        "applies rules to an unsaved proxy row for the import preview; nothing is written",
    "services/payee_service.py:delete_payee":
        "clears payee fields only, which no bill aggregate reads",
    "services/payee_service.py:bulk_delete_payees":
        "clears payee fields only, which no bill aggregate reads",
    "services/payee_service.py:merge_payees":
        "repoints payee fields only, which no bill aggregate reads",
    "services/rule_service.py:apply_rules_to_transaction":
        "runs on one row its caller creates or previews; the caller links it to its bill",
    "services/rule_service.py:preview_rule":
        "applies actions to an unsaved draft copy for the preview; nothing is written",
}


def _call_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _transaction_aliases(func: ast.AST) -> set[str]:
    """`Transaction`, plus loop variables iterating over a tuple that holds it."""
    aliases = {"Transaction"}
    for node in ast.walk(func):
        if (
            isinstance(node, ast.For)
            and isinstance(node.target, ast.Name)
            and isinstance(node.iter, (ast.Tuple, ast.List))
            and any(isinstance(e, ast.Name) and e.id == "Transaction" for e in node.iter.elts)
        ):
            aliases.add(node.target.id)
    return aliases


def _writes_and_refreshes(func: ast.AST) -> tuple[list[int], bool]:
    aliases = _transaction_aliases(func)
    writes: list[int] = []
    refreshes = False
    for node in ast.walk(func):
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node)
        if name in REFRESH_CALLS:
            refreshes = True
        elif name in ROW_MUTATORS:
            writes.append(node.lineno)
        elif (
            name in BULK_BUILDERS
            and node.args
            and isinstance(node.args[0], ast.Name)
            and node.args[0].id in aliases
        ):
            writes.append(node.lineno)
    return writes, refreshes


def _functions(tree: ast.Module):
    """Top-level functions and methods; nested defs count with their parent."""
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node
        elif isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    yield item


def find_unrefreshed_writes(app_dir: Path = APP) -> dict[str, list[int]]:
    """Every `module:function` with a transaction write and no bill refresh."""
    found: dict[str, list[int]] = {}
    for folder in SCANNED:
        for path in sorted((app_dir / folder).rglob("*.py")):
            tree = ast.parse(path.read_text(), filename=str(path))
            for func in _functions(tree):
                writes, refreshes = _writes_and_refreshes(func)
                if writes and not refreshes:
                    key = f"{path.relative_to(app_dir).as_posix()}:{func.name}"
                    found[key] = writes
    return found


def test_every_bulk_transaction_write_refreshes_bills():
    unrefreshed = find_unrefreshed_writes()
    offenders = {key: lines for key, lines in unrefreshed.items() if key not in ALLOWED}
    assert offenders == {}, (
        "These functions write transactions without calling bill_service "
        "(AD-004). Refresh the bills, or add the function to ALLOWED with a reason."
    )


def test_every_allowed_entry_still_matches_and_has_a_reason():
    unrefreshed = find_unrefreshed_writes()
    for key, reason in ALLOWED.items():
        assert reason.strip(), f"{key} needs a reason"
        assert key in unrefreshed, f"{key} no longer needs an exception; remove it"
