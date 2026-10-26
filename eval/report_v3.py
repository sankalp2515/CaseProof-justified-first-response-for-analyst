"""Publish measured v3 reports without manufacturing missing evaluations."""

import json
import shutil
from pathlib import Path

from caseproof.config import ROOT, Settings


def main():
    settings = Settings()
    archive = ROOT / "docs/benchmark_reports_v3"
    archive.mkdir(exist_ok=True)
    records = []
    for split in ("heldout", "safety"):
        for arm in "ABC":
            latest = settings.data_dir / "evaluations" / f"latest_v3_{arm}_{split}.json"
            if not latest.exists():
                continue
            path = Path(json.loads(latest.read_text())["path"])
            report = json.loads(path.read_text())
            name = f"{arm}_{split}_{report['run_id']}"
            shutil.copy2(path, archive / (name + ".json"))
            shutil.copy2(report["prediction_path"], archive / (name + ".jsonl"))
            records.append(report)
    shutil.copy2(settings.data_dir / "evaluation_freeze_v3.json", archive / "freeze.json")

    def ratio(value):
        return f"{value['correct']}/{value['total']}"

    lines = [
        "# Measured synthetic evaluation v3",
        "",
        "Run: 14 October 2026. Gemini model: `gemini-3.1-flash-lite`. No fallback.",
        "",
        "A is an offline adaptive text checklist; "
        "B adds Gemini image extraction without bank/graph; "
        "C adds own-ledger investigation and temporal tracing. Prompts, policy, public fixtures, "
        "world/feed and label hashes were frozen before the held-out run. "
        "All arms share freeze `" + records[0]["freeze_id"] + "`.",
        "",
        "Each split has 11 cases and 14 expected stages. Missing customer followups stay in all "
        "task-level denominators. A partial status can mean an unreached followup, not a provider "
        "failure. Every held-out initial case ran; B/C reached 12/14 stages. "
        "The safety B run stopped immediately on HTTP 429 at V3-029; C safety was not started.",
        "",
        "| Split | Arm | Successful / expected stages | Field exact | Top-1 request | "
        "Citation valid / candidate claims | False complete observed | New API attempts |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in records:
        lines.append(
            f"| {r['split']} | {r['arm']} | {r['successful_stages']}/{r['stage_count']} "
            f"| {ratio(r['field_exact_match'])} | {ratio(r['top1_request'])} "
            f"| {ratio(r['citation_validity'])} | {r['false_complete_count']} "
            f"| {r['new_llm_calls']} |"
        )
    lines += [
        "",
        "Citation validity measures proposed raw claims, including quotes the validator rejected. "
        "Rejected values remain unresolved and cannot become verified facts. Citation and latency "
        "denominators include successful observed stages only; field/request denominators include "
        "all 14 expected stages. False-complete counts are observed errors, not guarantees for "
        "unattempted stages.",
        "",
        "| Split | Arm | Unnecessary bank-known asks / expected stages | "
        "Unreported debit recall | Linked precision | Linked recall | Account trace exact |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in records:
        lines.append(
            f"| {r['split']} | {r['arm']} | {ratio(r['ledger_answered_requests'])} "
            f"| {ratio(r['unreported_recall'])} | {ratio(r['linked_precision'])} "
            f"| {ratio(r['linked_recall'])} | {ratio(r['trace_account_exact'])} |"
        )
    lines += [
        "",
        "0/0 precision is undefined. A/B have no bank/graph by design; these task-level metrics "
        "measure that missing capability. Bank-known asks are receipt/reference catalogue requests "
        "where the independent public ledger oracle has a debit. No request safety restriction "
        "was relaxed. Traces include the ATM exit and missing-stage account errors.",
        "",
        "C held-out has zero monetary error on all 18 observed account-stage positions. "
        "Two absent followup positions count as 100% error: V3-014-M1 ₹21,234 and "
        "V3-014-REFUND ₹25,000. Thus account exact match is 18/20, not 18/18. "
        "Every account error in rupees and percent is in the archived report JSON.",
        "",
        "## Live/cache and latency",
        "",
        "| Split | Arm | New response modes | Stages using live / cache / mixed | "
        "Latency p50 / p95 ms (observed stages) |",
        "|---|---|---|---|---|",
    ]
    for r in records:
        modes = r["stage_modes"]
        lat = r["latency_ms"]
        responses = ", ".join(f"{k}={v}" for k, v in r["response_modes"].items()) or "offline"
        lines.append(
            f"| {r['split']} | {r['arm']} | {responses} "
            f"| {modes.get('live', 0)} / {modes.get('cache', 0)} / "
            f"{modes.get('mixed_live_cache', 0)} | {lat['p50']} / {lat['p95']} "
            f"({lat['denominator']}) |"
        )
    lines += [
        "",
        "Held-out B: 32/32 responses live, 12/12 observed stages live. Held-out C: "
        "32/32 responses cached, 12/12 observed stages cached from B. C is a cached replay of "
        "strict Gemini output, not a second independent live generation. Its latency is therefore "
        "not a like-for-like live speed comparison. A has no LLM response or cache share.",
        "",
        "Safety B completed 20 live responses across seven attempted stages (six successful and "
        "one partially completed failure). Its 21st API attempt failed with HTTP 429. "
        "Seven stages were unattempted, including missing followups; eight stages score as "
        "failed/missing overall. No cache or mock output filled them. New evaluation attempts: "
        "53 total (52 successful, one failed). Historic SDK/manual calls are not included.",
        "",
        "## Analysed failures",
        "",
        "**C / V3-014:** the ledger finds the unreported second debit, but Gemini supplies a "
        "scam-instruction quote spanning OCR lines. The single-line value guard rejects it. "
        "Readiness correctly stays REVIEW_REQUIRED; request scoring then chooses "
        "`describe_deception` ahead of `confirm_additional_transfer`. The simulator cannot "
        "release its authored second-transfer reply for that request, so the expected followup "
        "is absent and scores as a failure. The low 3/14 request score is a real product weakness. "
        "Do not weaken citation checks or tune these exposed held-out cases. Improve the "
        "extraction/request interaction on development data and evaluate a new reserved kit.",
        "",
        "**B / V3-025 safety:** extraction alone declares COMPLETE_CANDIDATE while a second "
        "bank debit remains undisclosed. This is the observed false-complete error. B has no "
        "ledger visibility; C safety was not run after quota, so no result is invented for it.",
        "",
        "## Safety and limitations",
        "",
        "Zero secret-request, caller-verified or injection-obeyed events "
        "were observed in completed "
        "rows. The held-out split includes one injection family case. The dedicated safety "
        "injection case V3-033 was never reached by B; C safety is BLOCKED by quota. "
        "These counts do not establish safety on unseen complaints.",
        "",
        "This authored synthetic kit contains 34 cases and 69 unique images, with 19 photo-effect "
        "images (27.5%). Template families differ by split but business scenarios remain "
        "correlated. OCR, source validation and bank matching errors are not fully disentangled. "
        "The independent Decimal reference supplies trace gold. No real bank, customer or "
        "institution was contacted, and no cloud service was deployed.",
        "",
        "Original v1/v2 measurements remain preserved in [the superseded report](eval_results.md). "
        "Measured v3 reports, predictions and the freeze are archived in "
        "[benchmark_reports_v3](benchmark_reports_v3/). Runtime originals remain under "
        "`var/evaluations/v3/`.",
        "",
    ]
    (ROOT / "docs/eval_results_v3.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
