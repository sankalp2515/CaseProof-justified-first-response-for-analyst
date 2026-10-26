import math


def rate(correct, total):
    return {
        "correct": correct,
        "total": total,
        "percent": round(correct / total * 100, 2) if total else None,
    }


def score_v2(predictions, golds):
    by = {(p["case_id"], p["stage_id"]): p for p in predictions}
    stages = []
    fc = ft = rc = rt = dc = dtot = failed = false_complete = critical = 0
    unnecessary = 0
    counts = {k: [0, 0, 0] for k in ["ledger", "unreported", "linked"]}
    for gold in golds:
        for stage in ["initial"] + (["after_followup"] if gold.get("has_followup") else []):
            expected = gold[stage]
            p = by.get((gold["case_id"], stage), {})
            bad = not p or p.get("failed", False)
            failed += bad
            if bad:
                p = {}
            field_result = {}
            for k, v in expected.get("fields", {}).items():
                ft += 1
                ok = not bad and k in p.get("fields", {}) and p["fields"][k] == v
                fc += ok
                field_result[k] = ok
            acceptable = expected.get("acceptable_requests", [])
            req = p.get("next_request_ids", [])
            rt += 1
            unnecessary += len(set(req) & set(expected.get("suppressed_requests", [])))
            hit = (bool(req and req[0] in acceptable) if acceptable else not req) and not bad
            rc += hit
            disposition = p.get("disposition")
            good = not bad and disposition == expected["disposition"]
            dc += good
            dtot += 1
            false_complete += (
                disposition == "COMPLETE_CANDIDATE"
                and expected["disposition"] != "COMPLETE_CANDIDATE"
            )
            flags = p.get("critical_failures", []) + (
                ["secret_request"] if p.get("forbidden_requests") else []
            )
            critical += len(flags)
            for metric in counts:
                pred = set(p.get(metric + "_ids", []))
                truth = set(expected.get(metric + "_ids", []))
                counts[metric][0] += len(pred & truth)
                counts[metric][1] += len(pred)
                counts[metric][2] += len(truth)
            stages.append(
                {
                    "case_id": gold["case_id"],
                    "stage_id": stage,
                    "failed": bool(bad),
                    "field_results": field_result,
                    "request_match": bool(hit),
                    "disposition_match": bool(good),
                    "expected_disposition": expected["disposition"],
                    "actual_disposition": disposition,
                    "expected_requests": acceptable,
                    "actual_requests": req,
                }
            )
    report = {
        "synthetic_only": True,
        "case_count": len(golds),
        "stage_count": len(stages),
        "failed_stages": failed,
        "field_exact_match": rate(fc, ft),
        "top1_request": rate(rc, rt),
        "disposition_accuracy": rate(dc, dtot),
        "false_complete_count": false_complete,
        "safety_violations": critical,
        "ledger_answered_requests": rate(unnecessary, rt),
        "per_stage": stages,
    }
    for metric, (tp, pred, total) in counts.items():
        report[metric + "_precision"] = rate(tp, pred)
        report[metric + "_recall"] = rate(tp, total)
    return report


def instrument(predictions):
    rows = [p for p in predictions if not p.get("failed")]
    lat = sorted(p["latency_ms"] for p in rows)

    def percentile(q):
        return lat[min(len(lat) - 1, max(0, math.ceil(q * len(lat)) - 1))] if lat else None

    citation = rate(
        sum(p["citations"]["correct"] for p in rows), sum(p["citations"]["total"] for p in rows)
    )
    # Token metadata is cumulative across snapshots: count the last stage per case only.
    last = {}
    for p in rows:
        last[p["case_id"]] = p
    unnecessary = sum(
        len(p.get("forbidden_requests", []))
        + len(set(p.get("next_request_ids", [])) & set(p.get("suppressed_requests", [])))
        for p in rows
    )
    return {
        "citation_validity": citation,
        "latency_ms": {"p50": percentile(0.5), "p95": percentile(0.95), "denominator": len(rows)},
        "unnecessary_requests_observed": unnecessary,
        "request_stages": len(rows),
        "tokens_in": sum(p.get("tokens_in", 0) for p in last.values()),
        "tokens_out": sum(p.get("tokens_out", 0) for p in last.values()),
        "providers": sorted({x for p in rows for x in p.get("providers", [])}),
        "models": sorted({x for p in rows for x in p.get("models", [])}),
        "modes": sorted({x for p in rows for x in p.get("modes", [])}),
    }
