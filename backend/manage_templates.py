from __future__ import annotations

import argparse

from app.config import (
    TemplateResolutionError,
    publish_comparison_template_version,
    rollback_comparison_template_version,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Publica o reverteix plantilles PDF.")
    parser.add_argument("action", choices=("publish", "rollback"))
    parser.add_argument("template_id", choices=("comparison",))
    parser.add_argument("version", help="Versio amb format vN, per exemple v1.")
    args = parser.parse_args()

    try:
        if args.action == "publish":
            publish_comparison_template_version(args.version)
        else:
            rollback_comparison_template_version(args.version)
    except TemplateResolutionError as exc:
        parser.error(str(exc))

    print(f"La versio {args.version} de la plantilla {args.template_id} esta publicada.")


if __name__ == "__main__":
    main()
