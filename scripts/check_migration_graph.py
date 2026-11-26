"""Fail when Alembic migrations do not end at the expected single head."""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

EXPECTED_HEAD = "0007_questionnaire"


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    script = ScriptDirectory.from_config(config)
    heads = script.get_heads()
    if heads != [EXPECTED_HEAD]:
        raise SystemExit(
            f"Expected one Alembic head {EXPECTED_HEAD!r}, found {heads!r}"
        )
    print(f"Alembic graph has the expected single head: {EXPECTED_HEAD}")


if __name__ == "__main__":
    main()
