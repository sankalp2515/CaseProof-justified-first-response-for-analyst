from io import BytesIO

import pytest
from PIL import Image

from caseproof.adapters.local_storage import LocalStorage
from caseproof.adapters.object_validation import validate_evidence


@pytest.mark.parametrize("size", [(10001, 1), (5001, 4000)])
def test_small_compressed_files_cannot_bypass_dimension_or_pixel_limits(size):
    data = BytesIO()
    Image.new("1", size).save(data, format="PNG")
    assert len(data.getvalue()) < 5 * 1024 * 1024
    with pytest.raises(ValueError, match="invalid_image"):
        validate_evidence(data.getvalue(), "image/png")


@pytest.mark.parametrize(
    "key", ["../outside.txt", "aa/" + "a" * 64 + "/../outside.txt", "aa/" + "b" * 64]
)
def test_invalid_object_keys_cannot_read_outside_evidence_storage(tmp_path, key):
    outside = tmp_path / "outside.txt"
    outside.write_text("unchanged")
    with pytest.raises(ValueError, match="invalid_object_key"):
        LocalStorage(tmp_path / "objects").read(key)
    assert outside.read_text() == "unchanged"
