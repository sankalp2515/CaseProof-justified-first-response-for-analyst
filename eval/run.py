import json
import sqlite3
import time
import uuid
from pathlib import Path

from caseproof.domain.actions import request_state
from caseproof.domain.contracts import Gap, hash_json, now
from caseproof.domain.policy import load_policy
from caseproof.domain.requests import select_requests
from caseproof.pipeline.load import load_case, read_artifact
from caseproof.pipeline.orchestrator import Orchestrator
from eval.arms import fields, input_fingerprint, prediction
from eval.metrics import instrument, score_v2
from eval.replay import reveal_v1, reveal_v2


def freeze(settings, persist=True):
    data = {
        "policy": hash_json(settings.policy_path.read_text(encoding="utf-8")),
        "prompts": {
            p.name: hash_json(p.read_text(encoding="utf-8"))
            for p in Path("caseproof/prompts").glob("*.md")
        },
    }
    if not persist:
        return data
    path = settings.data_dir / "evaluation_freeze.json"
    if path.exists():
        old = json.loads(path.read_text())
        if old["hashes"] != data:
            raise ValueError(
                (
                    "Prompts or policy changed after evaluation freeze; create "
                    "a new documented benchmark version"
                )
            )
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"at": now(), "hashes": data}, indent=2))
    return data


def baseline_checklist(o, snapshot):
    # A and B adapt to observed text/document facts without bank lookup or suppression.
    fs = fields(snapshot)
    gaps = []
    for fact in load_policy(o.s.policy_path)["required_facts"]:
        if fact == "deception_account":
            known = any(
                c.kind == "scam_instruction"
                and c.evidence_state not in ("unresolved", "conflicted")
                for c in snapshot.claims
            )
        else:
            known = fs.get(fact) is not None
        if not known:
            gaps.append(
                Gap(
                    gap_id="gap-" + fact,
                    required_fact=fact,
                    status="conflicting"
                    if any(
                        c.kind == fact and c.evidence_state == "conflicted" for c in snapshot.claims
                    )
                    else "missing",
                )
            )
    history = [
        r
        for r in snapshot.requests
        if r.state in ("accepted", "fulfilled", "unavailable", "skipped")
    ]
    snapshot.requests = select_requests(gaps, history, load_policy(o.s.policy_path))
    return snapshot


class TextOnly:
    def __init__(self):
        from caseproof.adapters.mock_llm import MockLLM

        self.mock = MockLLM()

    def transcribe_image(self, *args):
        from caseproof.domain.contracts import RunMeta

        return [], RunMeta(model_id="arm-A-no-OCR")

    def extract_claims(self, *args):
        return self.mock.extract_claims(*args)


def call_count(settings):
    p = settings.data_dir / "llm.sqlite"
    if not p.exists():
        return 0
    with sqlite3.connect(p) as db:
        return db.execute("SELECT count(*) FROM calls").fetchone()[0]


def run(settings, arm="C", split="heldout", kit="v2", limit=None):
    if settings.llm_mode == "live" and settings.allow_fallback:
        raise ValueError("live eval forbids fallback")
    if (
        arm not in "ABC"
        or len(arm) != 1
        or split not in ("dev", "heldout", "safety")
        or kit not in ("v1", "v2")
    ):
        raise ValueError("invalid arm split or kit")
    root = settings.eval_kit_v2 if kit == "v2" else settings.eval_kit_v1
    manifest = json.loads((root / "inputs" / "manifest.json").read_text(encoding="utf-8"))
    cases = [c for c in manifest["cases"] if c["split"] == split]
    if limit is not None:
        cases = cases[:limit]
    hashes = freeze(settings, persist=split != "dev")
    run_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    directory = settings.data_dir / "evaluations" / kit / arm / split / run_id
    directory.mkdir(parents=True, exist_ok=True)
    config = settings.model_copy(
        update={
            "sqlite_url": "sqlite:///" + str(directory / "cases.sqlite"),
            "object_dir": directory / "objects",
        }
    )
    if kit == "v1" and arm == "C":
        from caseproof.adapters.duckdb_bank import DuckDBBank

        config.duckdb_path = str(settings.data_dir / "v1_bank.duckdb")
        public = json.loads((root / "mock_bank" / "ledger.json").read_text(encoding="utf-8"))
        tx = [
            dict(
                txn_id=r["reference"],
                account=r["customer_id"],
                amount_minor=r["amount_minor"],
                payee=r["payee"],
                ts=r["timestamp"],
                reference=r["reference"],
                direction="debit",
            )
            for r in public
        ]
        DuckDBBank(config.duckdb_path).load(tx, [])
    if arm == "A":
        config.llm_mode = "mock"
    o = Orchestrator(config)
    if arm == "A":
        o.llm = TextOnly()
    before_calls = call_count(settings)
    predictions = []
    fingerprints = {}
    for case in cases:
        cid = case["case_id"]
        fingerprints[cid] = input_fingerprint(root, cid, arm)
        try:
            start = time.perf_counter()
            load_case(o, root, cid)
            s = o.process(cid, investigate=arm == "C")
            if arm in "AB":
                baseline_checklist(o, s)
            p = prediction(s, arm, (time.perf_counter() - start) * 1000)
            if arm == "A":
                p.update(providers=["deterministic"], models=["rules-v1-no-OCR"], modes=["offline"])
            if kit == "v1":
                p["fields"]["amount_minor"] = p["fields"].pop("amount")
            predictions.append(p)
            requests = p["next_request_ids"]
            if not requests:
                continue
            sim = (reveal_v2 if kit == "v2" else reveal_v1)(root, cid, requests[0])
            if not sim.get("available") or not sim.get("artifacts"):
                continue
            # Publish the baseline catalogue choice without leaking future evidence.
            current = o.store.get(cid)
            current.requests = s.requests
            old = current.revision
            current.revision += 1
            o.store.publish(current, old, "eval_request_selected")
            rid = next(
                r.request_id
                for r in current.requests
                if r.catalogue_id == requests[0] and r.state == "proposed"
            )
            request_state(o, cid, rid, "accepted")
            start = time.perf_counter()
            for item in sim["artifacts"]:
                o.intake.add(
                    cid,
                    read_artifact(root, item),
                    item["mime_type"],
                    item["kind"],
                    stage="followup",
                    artifact_id=item["artifact_id"],
                )
            request_state(o, cid, rid, "fulfilled")
            s = o.process(cid, investigate=arm == "C")
            if arm in "AB":
                baseline_checklist(o, s)
            p = prediction(s, arm, (time.perf_counter() - start) * 1000)
            if arm == "A":
                p.update(providers=["deterministic"], models=["rules-v1-no-OCR"], modes=["offline"])
            if kit == "v1":
                p["fields"]["amount_minor"] = p["fields"].pop("amount")
            predictions.append(p)
        except Exception as e:
            stage = (
                "initial" if not any(p["case_id"] == cid for p in predictions) else "after_followup"
            )
            predictions.append(
                {
                    "case_id": cid,
                    "stage_id": stage,
                    "failed": True,
                    "error_type": type(e).__name__,
                    "arm": arm,
                }
            )
    # Score only AFTER all predictions have been written. These are the only label reads.
    predpath = directory / "predictions.jsonl"
    predpath.write_text(
        "\n".join(json.dumps(p, ensure_ascii=False) for p in predictions) + "\n", encoding="utf-8"
    )
    if kit == "v2":
        golds = [
            json.loads((root / "labels" / (c["case_id"] + ".json")).read_text(encoding="utf-8"))
            for c in cases
        ]
        report = score_v2(predictions, golds)
    else:
        from eval_kit_v1.evaluate import score

        if limit is not None:
            raise ValueError("v1 scorer requires the full selected split")
        report = score(predictions, split)
    report.update(instrument(predictions))
    report.update(
        arm=arm,
        kit=kit,
        split=split,
        run_id=run_id,
        at=now(),
        freeze_hashes=hashes,
        configured_provider=settings.llm_provider,
        configured_model=o.llm.model_id if arm != "A" else "none",
        requested_mode=settings.llm_mode,
        new_llm_calls=call_count(settings) - before_calls,
        input_fingerprints=fingerprints,
        prediction_path=str(predpath),
        limitations=[
            "Synthetic authored correlated cases; no real bank validation",
            "A is text-only; B/C use images, B omits ledger/linking",
            "Mock renderer transcripts are idealised, not measured OCR",
            "Missing followup stages remain failures in denominators",
            "Observed safety checks are not production certification",
        ],
    )
    path = directory / "report.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    latest = settings.data_dir / "evaluations" / f"latest_{kit}_{arm}_{split}.json"
    latest.write_text(json.dumps({"path": str(path)}))
    return {
        k: v
        for k, v in report.items()
        if k not in ("per_stage", "input_fingerprints", "limitations")
    } | {"report_path": str(path)}


if __name__ == "__main__":
    from caseproof.config import Settings

    print(json.dumps(run(Settings()), indent=2))
