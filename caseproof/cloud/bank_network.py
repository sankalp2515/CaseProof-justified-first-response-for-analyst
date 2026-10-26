"""Persist synthetic bank worlds in Firestore; publish records through bank ingestion."""

from caseproof.adapters.firestore_casestore import identity
from caseproof.adapters.sqlite_casestore import ConflictError
from caseproof.api.bank_contracts import BankBatch
from local_services.bank_network import BankNetwork
from local_services.demo_world import BANKS, NAMES, incident


class CloudBankNetwork(BankNetwork):
    def __init__(self, o):
        self.o = o

    def read(self, network_id, actor):
        row = self.o.store.documents.get(
            "synthetic_networks/" + identity(actor.tenant_id, network_id)
        )
        if not row:
            raise KeyError("bank network missing")
        return row["data"]

    def create(self, network_id, seed, actor, minutes_ago=30, position=None):
        if actor.role != "admin" or not self.o.s.demo_mode:
            raise PermissionError("synthetic network administrator required")
        path = "synthetic_networks/" + identity(actor.tenant_id, network_id)
        generated = self._generate(network_id, seed, actor.tenant_id, minutes_ago)
        # Position in the tenant picks distinct names/banks; random seeds may collide.
        index = seed % 6 if position is None else position % 6
        import json

        raw = json.dumps(generated).replace("Lotus Demo Bank", BANKS[1 + index * 2 % 9])
        raw = raw.replace("Tulip Demo Bank", BANKS[1 + (index * 2 + 1) % 9])
        generated = json.loads(raw)
        for position, customer in enumerate(generated["dataset"]["customers"]):
            customer["display_name"] = NAMES[index * 2 + position] + " (synthetic)"
            for account in generated["dataset"]["accounts"]:
                if account["id"] == customer["account"]:
                    account["label"] = customer["display_name"].removesuffix(" (synthetic)")
        # The catalogue reads the manifest; it must carry the same distinct names.
        generated["manifest"]["customers"] = generated["dataset"]["customers"]

        def create(tx):
            row = tx.get(path)
            if row and row["data"]["seed"] != seed:
                raise ConflictError("network_id_seed_conflict")
            if row:
                return row["data"]
            tx.set(
                path,
                {"tenant": actor.tenant_id, "network_id": network_id, "data": generated},
                create=True,
            )
            return generated

        saved = self.o.store.documents.transact(create)
        result = self.o.bank_ingestion.ingest(BankBatch.model_validate(saved["dataset"]), actor)
        return {**saved["manifest"], "publication_id": result["publication_id"]}

    def seed_tenant(self, actor, minutes_ago=30, seeds=None):
        """seeds: one per network; practice sessions pass fresh random seeds so every
        visitor gets different amounts and money-movement shapes."""
        seeds = seeds or [36 + index for index in range(6)]
        manifests = [
            self.create(f"PRELOADED-{index}", seed, actor, minutes_ago, index)
            for index, seed in enumerate(seeds)
        ]
        return {
            "version": 5,
            "banks": BANKS,
            "customers": [
                {
                    **customer,
                    "network_id": m["network_id"],
                    "bank": m["bank"],
                    "publication_id": m["publication_id"],
                    **incident(m, customer),
                }
                for m in manifests
                for customer in m["customers"]
            ],
            "synthetic": True,
        }

    def publish_reports(self, network_id, actor, *, refresh=False):
        import copy
        from datetime import datetime, timezone

        if actor.role != "admin":
            raise PermissionError("synthetic bank administrator required")
        saved = self.read(network_id, actor)
        reports = list(saved["reports"])
        if refresh:
            observed = datetime.now(timezone.utc).isoformat()
            suffix = "-REFRESH-" + identity(observed)[:20]
            batch = copy.deepcopy(saved["dataset"])
            batch["batch_id"] += suffix
            batch["transactions"] = []
            for cover in batch["coverage"]:
                cover.update(as_of=observed, end=observed)
            batch_publication = self.o.bank_ingestion.ingest(
                BankBatch.model_validate(batch), actor
            )["publication_id"]
            due = cash_outs(saved, observed)
            # Each withdrawal gets one fixed report (stable id and content, so a later
            # refresh re-sends it as a duplicate); refreshes carry only the balance.
            running = {r["account"]: r["balance_minor"] for r in reports}
            banks = {r["account"]: r["reporting_bank"] for r in reports}
            cash_reports = []
            for w in due:
                account = w["from_account"]
                running[account] -= w["amount_minor"]
                update_id = w["txn_id"] + "-RPT"
                cash_reports.append(
                    dict(
                        update_id=update_id,
                        account=account,
                        reporting_bank=banks[account],
                        reported_at=w["ts"],
                        balance_minor=running[account],
                        credit_received=[],
                        onward_transfers=[{**w, "source": "cfcfrms_update:" + update_id}],
                    )
                )
            refreshed = [
                dict(
                    update_id=r["update_id"] + suffix,
                    account=r["account"],
                    reporting_bank=r["reporting_bank"],
                    reported_at=observed,
                    balance_minor=running[r["account"]],
                    credit_received=[],
                    onward_transfers=[],
                )
                for r in reports
            ]
            reports += cash_reports
            reports += refreshed
        return {
            "publications": [self.o.bank_ingestion.downstream(r, actor) for r in reports],
            "bank_publication": batch_publication if refresh else None,
            "synthetic": True,
        }


# Mules cash out while the bank waits: the scenario schedules ATM withdrawals at
# fixed minutes after the scam debit, and a refresh reports only those already due.
CASH_OUT_PLAN = ((0, 20, 2), (1, 30, 2), (0, 45, 1), (1, 55, 1))  # (report, minute, 1/n)


def cash_outs(saved, observed):
    from datetime import datetime, timedelta

    reports = saved["reports"]
    base = reports[0]
    atm = next(
        (t["to_account"] for t in base["onward_transfers"] if t.get("channel") == "ATM"), None
    )
    scam = next((t for t in saved["dataset"]["transactions"] if t["txn_id"].endswith("-T1")), None)
    if not atm or not scam:
        return []
    start, now = datetime.fromisoformat(scam["ts"]), datetime.fromisoformat(observed)
    remaining = {i: reports[i]["balance_minor"] for i in (0, 1) if i < len(reports)}
    out = []
    for step, (index, minute, share) in enumerate(CASH_OUT_PLAN, 1):
        if index not in remaining:
            continue
        flows = reports[index]["credit_received"] + reports[index]["onward_transfers"]
        latest = max((datetime.fromisoformat(t["ts"]) for t in flows), default=start)
        # Never before the money reached this account: scenarios scale flow times.
        at = max(start + timedelta(minutes=minute), latest + timedelta(minutes=1))
        amount = remaining[index] // share
        remaining[index] -= amount
        if at > now or amount <= 0:
            continue
        account = reports[index]["account"]
        out.append(
            dict(
                txn_id=f"{account}-ATM{step}",
                ts=at.isoformat(),
                from_account=account,
                to_account=atm,
                amount_minor=amount,
                channel="ATM",
                reference=f"{account}-ATM{step}-REF",
                source="",
            )
        )
    return out
