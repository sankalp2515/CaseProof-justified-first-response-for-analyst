import json
from pathlib import Path

from caseproof.adapters.provider import ProviderError
from eval import backend_quality


def test_provider_failures_remain_in_both_case_and_field_denominators(tmp_path, monkeypatch):
    corpus = Path(__file__).resolve().parents[2] / "eval/corpora/novel_v1"
    expected = sum(
        len(case["expected_fields"])
        for case in json.loads((corpus / "corpus.json").read_text())["cases"]
    )

    def unavailable(_):
        raise ProviderError("LOCAL_OCR_ERROR")

    monkeypatch.setattr(backend_quality, "runtime", unavailable)
    report = backend_quality.evaluate(corpus, tmp_path / "failed-provider")
    assert report["provider_errors"] == report["total"] == 30
    assert report["passed"] == 0
    assert report["field_counts"] == {"tp": 0, "fp": 0, "fn": expected}
    assert report["field_recall"] == 0
