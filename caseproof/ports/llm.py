from typing import Protocol

from caseproof.domain.contracts import ArtifactRef, ExtractionResult, RunMeta, Segment


class LLMPort(Protocol):
    def transcribe_image(
        self, case_id: str, artifact: ArtifactRef, data: bytes, fixture: list | None = None
    ) -> tuple[list[Segment], RunMeta]: ...
    def extract_claims(
        self,
        case_id: str,
        revision: int,
        segments: list[Segment],
        corrective_action: str | None = None,
    ) -> ExtractionResult: ...
    def explain(self, *args) -> dict: ...
    def summarise(self, *args) -> str: ...
