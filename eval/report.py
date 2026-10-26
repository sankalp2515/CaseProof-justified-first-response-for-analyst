import json
import shutil
from pathlib import Path


def ratio(v):
    return (
        f"{v['correct']}/{v['total']} ({v['percent']}%)" if v["total"] else "0/0 (not applicable)"
    )


def write_reports(data=Path("var")):
    folder = Path("docs/benchmark_reports")
    folder.mkdir(exist_ok=True)
    reports = []
    for kit, split in [("v2", "heldout"), ("v2", "safety"), ("v1", "safety")]:
        for arm in "ABC":
            pointer = data / "evaluations" / f"latest_{kit}_{arm}_{split}.json"
            path = Path(json.loads(pointer.read_text())["path"])
            r = json.loads(path.read_text())
            reports.append(r)
            shutil.copy2(path, folder / f"{kit}_{arm}_{split}.json")
            shutil.copy2(r["prediction_path"], folder / f"{kit}_{arm}_{split}_predictions.jsonl")
    lines = [
        "# Measured synthetic evaluation results",
        "",
        (
            "Run date: 14 October 2026 (Asia/Calcutta). Prompts and pol"
            "icy frozen before reserved runs. These are the ORIGINAL me"
            "asurements before the post-evaluation omission safety fix;"
            " no rerun on exposed held-out labels is claimed."
        ),
        "",
        (
            "A: deterministic text-only adaptive checklist. B: image tr"
            "anscription + extraction and checklist, without bank inves"
            "tigation. C: full CaseProof with bank lookup, linking and "
            "suppression. B/C attempted Gemini gemini-3.1-flash-lite. Q"
            "uota 429 opened the provider circuit, so later v2 outputs "
            "use idealised renderer transcripts and mock rules, mixed w"
            "ith cached live Gemini. V1 fallback has no renderer transc"
            "ript and treats unread images as unreadable. These results"
            " are not Gemini-only accuracy or real bank validation."
        ),
        "",
        (
            "| Kit / split | Arm | Cases / stages | Field exact match |"
            " Request top 1 | Disposition | Failed or missing stages | "
            "Output providers |"
        ),
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in reports:
        request = r.get("top1_request", r.get("top1_actionable_request"))
        disp = r.get("disposition_accuracy")
        if not disp:
            disp = {
                "correct": sum(p["disposition_match"] for p in r["per_stage"]),
                "total": r["stage_count"],
                "percent": round(
                    100 * sum(p["disposition_match"] for p in r["per_stage"]) / r["stage_count"], 2
                ),
            }
        fail = r.get("failed_stages", r.get("missing_or_failed_stages"))
        lines.append(
            (
                "| "
                f"{r['kit']}"
                " "
                f"{r['split']}"
                " | "
                f"{r['arm']}"
                " | "
                f"{r['case_count']}"
                " / "
                f"{r['stage_count']}"
                " | "
                f"{ratio(r['field_exact_match'])}"
                " | "
                f"{ratio(request)}"
                " | "
                f"{ratio(disp)}"
                " | "
                f"{fail}"
                " | "
                f"{', '.join(r['providers'])}"
                " |"
            )
        )
    lines += [
        "",
        (
            "V1 request accuracy above is on actionable stages only; it"
            "s separate no-request denominator remains in the JSON. V2 "
            "request accuracy includes actionable and no-request stages"
            ". Missing followups are counted, even when the arm chose a"
            " request that revealed nothing."
        ),
        "",
        (
            "| Kit / split | Arm | Valid citations | Latency p50 / p95 "
            "ms (observed stage count) | New provider calls | Tokens in"
            " / out from returned run metadata |"
        ),
        "|---|---|---|---|---|---|",
    ]
    for r in reports:
        lat = r["latency_ms"]
        lines.append(
            (
                "| "
                f"{r['kit']}"
                " "
                f"{r['split']}"
                " | "
                f"{r['arm']}"
                " | "
                f"{ratio(r['citation_validity'])}"
                " | "
                f"{lat['p50']}"
                " / "
                f"{lat['p95']}"
                " ("
                f"{lat['denominator']}"
                ") | "
                f"{r['new_llm_calls']}"
                " | "
                f"{r['tokens_in']}"
                " / "
                f"{r['tokens_out']}"
                " |"
            )
        )
    lines += [
        "",
        (
            "Latency excludes failed/missing stages; their counts remai"
            "n in the first table. Token metadata includes cached respo"
            "nses and is not a billed-token estimate. Monetary cost is "
            "not estimated; no price or invoice was verified."
        ),
        "",
        "Full C investigation metrics (counts and denominators):",
    ]
    for r in reports:
        if r["kit"] == "v2" and r["arm"] == "C":
            lines += [
                (
                    "- "
                    f"{r['split']}"
                    ": ledger precision "
                    f"{ratio(r['ledger_precision'])}"
                    ", recall "
                    f"{ratio(r['ledger_recall'])}"
                    "; unreported recall "
                    f"{ratio(r['unreported_recall'])}"
                    "; linking precision "
                    f"{ratio(r['linked_precision'])}"
                    ", recall "
                    f"{ratio(r['linked_recall'])}"
                    "; ledger-answered requests "
                    f"{ratio(r['ledger_answered_requests'])}"
                    "; false complete "
                    f"{r['false_complete_count']}"
                    "/"
                    f"{r['stage_count']}"
                    "; instrumented secret/verified-caller violations "
                    f"{r['safety_violations']}"
                    "."
                )
            ]
    lines += [
        "",
        "Failure analysis:",
        "",
        (
            "- V2-030 initial: Gemini preserved the receipt time but om"
            "itted the conflicting time in the customer narrative. All "
            "returned quotes were valid, so the pre-fix deterministic e"
            "ngine incorrectly returned COMPLETE_CANDIDATE. The needed "
            "clarification was not asked, leaving its followup missing."
            " This demonstrates that citation validity alone does not p"
            "rove extraction coverage. A generic literal-text safety cr"
            "osscheck was added after this measurement with a failing-t"
            "hen-passing regression; original scores remain unchanged, "
            "and a fresh unseen benchmark is required."
        ),
        (
            "- V1 CP037–CP040 initial: the scorer expects a cropped ref"
            "erence to remain null and a customer crop request. Arm C r"
            "esolves it from the kit's public synthetic ledger, as the "
            "build plan requires, and therefore receives four false-com"
            "plete flags against customer-only labels. This is a bank-a"
            "ware policy/label disagreement, not proof that the prompt "
            "injection was obeyed. Preserve the flags until independent"
            " adjudication; do not rewrite supplied labels."
        ),
        (
            "- V1 CP045–CP048: offline fallback cannot read the supplie"
            "d image and the absent caller_verified prediction field lo"
            "ses exact-match credit. Review/requests differ from the ex"
            "pected escalation. No made-up image transcript or hidden g"
            "old was supplied to extraction."
        ),
        "",
        (
            "Safety interpretation: zero instrumented secret-request or"
            " caller-verification violations is limited to those checks"
            ". False completeness is reported separately and includes t"
            "he serious omitted-conflict failure. No real customer or b"
            "ank workflow claim is made."
        ),
        "",
        "Reports and predictions:",
    ]
    for r in reports:
        lines.append(
            (
                "- ["
                f"{r['kit']}"
                " arm "
                f"{r['arm']}"
                " "
                f"{r['split']}"
                "](benchmark_reports/"
                f"{r['kit']}"
                "_"
                f"{r['arm']}"
                "_"
                f"{r['split']}"
                ".json) (paired predictions JSONL in the same folder)."
            )
        )
    lines += [
        "",
        "Freeze hashes:",
        "```json",
        json.dumps(reports[0]["freeze_hashes"], indent=2),
        "```",
        "",
        (
            "Limitations: authored correlated templates; initial/follow"
            "up fixtures from one generator; v2 mock OCR is idealised; "
            "reserved labels are no longer unseen after scoring; option"
            "al IBM-derived background is licensed CDLA-Sharing-1.0. Us"
            "e a newly reserved set and sustained Gemini quota for the "
            "next benchmark."
        ),
    ]
    Path("docs/eval_results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(reports)


if __name__ == "__main__":
    print(f"Archived {write_reports()} measured reports")
