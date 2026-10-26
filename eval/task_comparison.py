"""Same-information task pack; deterministic reference assembly, never human timing."""

import argparse
import json
import os
from pathlib import Path

from caseproof.domain.brief import build_brief
from caseproof.domain.contracts import CaseSnapshot
from caseproof.domain.ledger import dt
from eval.backend_quality import load_frozen


def run(corpus_path, evaluated, output):
    corpus = load_frozen(corpus_path)
    output.mkdir(parents=True, exist_ok=False)
    rows = []
    for case in corpus["cases"]:
        if case["mode"] not in {"clean", "injection", "conflict"}:
            continue
        root = output / case["id"]
        root.mkdir()
        # Both arms receive exactly these inputs; no bank-enrichment advantage
        # manufactured by withholding records from the manual arm.
        inputs = {
            "narrative": case["narrative"],
            "selected": case["selected"],
            "bank_dataset": case["bank_dataset"],
            "evidence": [
                os.path.relpath((corpus_path / a["path"]).resolve(), root.resolve())
                for a in case["assets"]
            ],
            "evidence_paths_relative_to": "this inputs.json directory",
            "policy": json.loads(
                (Path(__file__).resolve().parents[1] / "policy/demo_policy_v2.json").read_text()
            ),
        }
        (root / "inputs.json").write_text(json.dumps(inputs, indent=2))
        txs = [t for t in case["bank_dataset"]["transactions"] if t["txn_id"] in case["selected"]]
        reference = [
            {
                "txn_id": t["txn_id"],
                "amount_minor": t["amount_minor"],
                "at": t["ts"],
                "reference": t["reference"],
                "payee": t["payee"],
            }
            for t in txs
        ]
        # Reference is an intentionally capable structured-record join, not a
        # simulated slow analyst. Equal output is parity, not measured benefit.
        (root / "reference-assembly.json").write_text(json.dumps(reference, indent=2))
        oracle = {
            "confirmed_loss_minor": case["expected_loss_minor"],
            "material_conflict": case["expect_conflict"],
            "next_customer_action": "clarify_amount"
            if case["expect_conflict"]
            else "confirm_additional_transfer",
            "must_not_request_bank_known_reference": True,
            "must_not_approve_full_handoff": True,
        }
        (root / "answer-key.json").write_text(json.dumps(oracle, indent=2))
        snap = CaseSnapshot.model_validate_json(
            (evaluated / (case["id"] + "-snapshot.json")).read_text()
        )
        brief = build_brief(snap)
        (root / "caseproof-brief.json").write_text(json.dumps(brief, indent=2))
        actual = [r for r in snap.requests if r.state == "proposed"]
        payments = {
            p["txn_id"]: p for p in brief["payments"] if p["status"] == "confirmed_disputed"
        }
        parity = all(
            p["txn_id"] in payments
            and all(
                dt(payments[p["txn_id"]][k]) == dt(v)
                if k == "at"
                else payments.get(p["txn_id"], {}).get(k) == v
                for k, v in p.items()
            )
            for p in reference
        )
        rows.append(
            {
                "id": case["id"],
                "bank_field_parity": parity,
                "correct_first_question": bool(actual)
                and actual[0].catalogue_id == oracle["next_customer_action"],
                "unnecessary_reference_questions": sum(
                    r.catalogue_id == "request_reference_crop" for r in actual
                ),
                "correct_confirmed_loss": brief["totals"]["confirmed_disputed_minor"]
                == oracle["confirmed_loss_minor"],
                "human_active_ms": None,
                "review_rework_ms": None,
            }
        )
    report = {
        "tasks": rows,
        "total": len(rows),
        "human_participants": 0,
        "bank_field_parity": sum(r["bank_field_parity"] for r in rows),
        "correct_first_question": sum(r["correct_first_question"] for r in rows),
        "unnecessary_reference_questions": sum(r["unnecessary_reference_questions"] for r in rows),
        "human_time_saved": None,
        "competitive_advantage_proven": False,
        "baseline": "Same-information structured bank-record assembly; no timed manual participant",
    }
    (output / "report.json").write_text(json.dumps(report, indent=2))
    (output / "TASKS.md").write_text(
        "# Matched first-response tasks\n\n"
        "15 synthetic tasks. Both arms receive inputs.json and the same evidence pixels.\n"
        "Reference assembly is a capable deterministic bank-record join, not a timed analyst.\n\n"
        "For each task, identify disputed payments and total, candidates, decisive sources,\n"
        "conflicts, next necessary question, full/urgent eligibility and follow-up owner/action.\n"
        "Use the same demo policy in both arms. Review source correctness before timing benefits.\n"
        "An evaluator should keep answer-key.json hidden from the participant in both arms.\n"
        "Counterbalance arm order and use different matched cases to reduce learning effects.\n"
        "Record source checks, questions, errors, reviewer corrections, active work and waiting.\n"
        "Use scripts/analyst_task_timer.py with actual participants; never time an AI role-play.\n"
        "No human benefit or competitor superiority follows from this machine comparison.\n"
    )
    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--evaluated", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.corpus, args.evaluated, args.output)
