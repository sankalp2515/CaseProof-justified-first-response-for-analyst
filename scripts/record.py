import subprocess
import sys
from pathlib import Path

phase, task, nextstep, verification = sys.argv[1:5]
p = Path("docs/PROGRESS.md")
old = p.read_text() if p.exists() else "# Progress\n\nCompleted tasks:\n"
old = "\n".join(
    x for x in old.splitlines() if not x.startswith(("Current phase:", "Next step:", "Verify:"))
)
subprocess.run(["git", "add", "."], check=True)
subprocess.run(["git", "commit", "-m", task], check=True)
commit = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
p.write_text(
    old
    + (
        "\n- Phase "
        f"{phase}"
        ": "
        f"{task}"
        "; commit `"
        f"{commit}"
        "`.\n\nCurrent phase: "
        f"{phase}"
        " / "
        f"{task}"
        "\nNext step: "
        f"{nextstep}"
        "\nVerify: "
        f"{verification}"
        "\n"
    ),
    encoding="utf-8",
)
with Path("docs/build_log.md").open("a", encoding="utf-8") as f:
    f.write(
        f"\n## {task} ({commit})\nFiles: "
        + subprocess.check_output(["git", "show", "--stat", "--oneline", "HEAD"], text=True)
        + f"\nCommands and output: {verification}\nOpen issues: see PROGRESS and decisions.\n"
    )
subprocess.run(["git", "add", "docs/PROGRESS.md", "docs/build_log.md"], check=True)
subprocess.run(["git", "commit", "-m", "docs: record " + task], check=True)
