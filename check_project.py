import importlib
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parent
    sys.path.insert(0, str(root))
    failures = []
    for path in sorted(root.glob("*.py")):
        if path.name == "check_project.py":
            continue
        try:
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
        except SyntaxError as exc:
            failures.append(f"{path.name}: {exc}")
    for module in ("app", "bot", "database", "config", "security", "verification",
                   "moderation", "tickets", "campaigns", "giveaways", "middleman",
                   "transactions"):
        try:
            importlib.import_module(module)
        except Exception as exc:
            failures.append(f"{module}: {type(exc).__name__}: {exc}")
    if failures:
        print("\n".join(failures))
        return 1
    print("Project syntax and import validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
