"""Create an isolated source snapshot for tests on Linux without Windows bind I/O."""

import subprocess
import tarfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
output = root / "var/journey-validation/source.tar"
output.parent.mkdir(parents=True, exist_ok=True)
names = (
    subprocess.check_output(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=root,
    )
    .decode()
    .split("\0")
)
with tarfile.open(output, "w") as archive:
    for name in sorted(set(names)):
        source = root / name
        if name and source.is_file():
            archive.add(source, arcname=name, recursive=False)
print(f"Regression snapshot: {output.stat().st_size} bytes")
