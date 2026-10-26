"""Optional CDLA-Sharing-1.0 subgraph; identifiers are remapped before output."""

import csv
import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path


def sample(path=Path("data/external/HI-Small_Trans.csv"), limit=1500, scan=150000):
    path = Path(path)
    if not path.exists():
        return []
    out = []
    ist = timezone(timedelta(hours=5, minutes=30))

    def fictional(bank, account):
        return hashlib.sha256((bank + ":" + account).encode()).hexdigest()[:12]

    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        next(reader)
        for n, row in enumerate(reader):
            if n >= scan or len(out) >= limit:
                break
            if row[-1] != "1":
                continue
            src = fictional(row[1], row[2])
            dst = fictional(row[3], row[4])
            try:
                d = datetime.strptime(row[0], "%Y/%m/%d %H:%M")
                amount = int(float(row[7]) * 100) % 9000000 + 10000
            except ValueError:
                continue
            ts = datetime(2026, 9, 1, d.hour, d.minute, tzinfo=ist) + timedelta(
                days=(d.day - 1) % 30
            )
            out.append(
                dict(
                    txn_id=f"IBM-{n}",
                    account="IBM-DEMO-" + src,
                    amount_minor=amount,
                    payee=dst + "@fictional.invalid",
                    ts=ts.isoformat(),
                    reference=f"SYNTH-TX-IBM-{n}",
                    direction="debit",
                )
            )
    return out
