import subprocess
import sys
from pathlib import Path

phase, task, next_step, verify = sys.argv[1:5]
subprocess.run(["git", "add", "-u"], check=True)
new = subprocess.check_output(
    ["git", "ls-files", "--others", "--exclude-standard"], text=True
).splitlines()
for name in new:
    if name not in {"CODEX_FIXUP_PROMPT.md", "docs/RESEARCH.md"}:
        subprocess.run(["git", "add", "--", name], check=True)
subprocess.run(["git", "commit", "-m", phase + ": " + task], check=True)
commit = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
p = Path("docs/PROGRESS_V2.md")
old = p.read_text(encoding="utf-8") if p.exists() else "# V2 progress\n"
old = "\n".join(
    item_l
    for item_l in old.splitlines()
    if not item_l.startswith((("Current phase:"), ("Next step:"), ("Verify:")))
)
p.write_text(
    old
    + (
        "\n- "
        f"{phase}"
        ": "
        f"{task}"
        "; commit `"
        f"{commit}"
        "`.\nCurrent phase: "
        f"{phase}"
        "\nNext step: "
        f"{next_step}"
        "\nVerify: "
        f"{verify}"
        "\n"
    ),
    encoding="utf-8",
)
with Path("docs/build_log.md").open("a", encoding="utf-8") as f:
    f.write(f"\n## {phase}: {task} ({commit})\nVerification: {verify}\nNext: {next_step}\n")
subprocess.run(["git", "add", "docs/PROGRESS_V2.md", "docs/build_log.md"], check=True)
subprocess.run(["git", "commit", "-m", "docs: record " + phase], check=True)
