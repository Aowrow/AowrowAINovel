from pathlib import Path
import sys


def _bootstrap_path() -> None:
    project_root = Path(__file__).resolve().parent
    src_dir = project_root / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))


def main() -> int:
    _bootstrap_path()
    from template_novel_engine.cli import main as cli_main

    return cli_main()


if __name__ == "__main__":
    raise SystemExit(main())

