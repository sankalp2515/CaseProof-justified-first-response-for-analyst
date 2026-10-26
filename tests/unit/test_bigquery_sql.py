import re
from types import SimpleNamespace

from caseproof.adapters.bigquery_bank import BigQueryBank


def test_struct_fields_are_named_with_as():
    """BigQuery rejects `STRUCT(expr name)`; real SQL is dry-run by scripts/bigquery_dry_run.py."""
    captured = []
    client = SimpleNamespace(
        table=lambda name: f"`p.d.{name}`",
        query=lambda sql, params: captured.append(sql) or [],
    )
    BigQueryBank(client, "tenant", None).transactions("ACC", "2026-10-17T10:00:00+00:00")
    struct = re.search(r"STRUCT\((.*?)\)\) FROM", captured[0], re.S).group(1)
    fields = [f.strip() for f in re.split(r",\s*(?![^()]*\))", struct) if f.strip()]
    assert fields and all(re.search(r"\sAS\s+\w+$", f) for f in fields), fields
