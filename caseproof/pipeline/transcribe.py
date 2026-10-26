from typing import Any

from caseproof.domain.contracts import Segment


def segment_text(artifact: Any, data: Any) -> Any:
    """Split an exact text artifact into cited line segments."""
    return [
        Segment(
            segment_id=f"seg-{artifact.artifact_id}-{i}",
            artifact_id=artifact.artifact_id,
            text=line,
        )
        for i, line in enumerate(data.decode("utf-8").splitlines())
        if line.strip()
    ]
