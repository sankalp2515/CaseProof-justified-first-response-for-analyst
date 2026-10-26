from caseproof.domain.contracts import RunMeta, Segment


class MockLLM:
    provider = "mock"
    model_id = "rules-v1"

    def transcribe_image(self, case_id, artifact, data, fixture=None):
        # Only renderer-owned transcripts may be used; never answer labels.
        if fixture is None:
            return [], RunMeta(confidence_note="") if False else RunMeta(
                model_id="mock-unreadable-image"
            )
        segments = [
            Segment(
                segment_id=f"seg-{artifact.artifact_id}-{i}",
                artifact_id=artifact.artifact_id,
                text=x["text"],
                box_2d=x.get("box_2d"),
                source="model_ocr",
                ocr_model_id="mock-renderer-transcript",
            )
            for i, x in enumerate(fixture)
        ]
        return segments, RunMeta(model_id="mock-renderer-transcript", input_digest=artifact.sha256)

    def extract_claims(self, case_id, revision, segments):
        from caseproof.adapters.literal_extractor import LiteralExtractor

        return LiteralExtractor().extract_claims(case_id, revision, segments)

    def explain(self, *args):
        return {"can_settle": [], "cannot_prove": ["Caller identity or liability"]}

    def summarise(self, *args):
        return "Synthetic complaint. Sources require reviewer assessment."
