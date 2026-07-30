from __future__ import annotations

from app.config import migrate_comparison_template_schema


def main() -> None:
    migrated_versions = migrate_comparison_template_schema()
    if migrated_versions:
        print(f"Migrated comparison templates: {', '.join(sorted(migrated_versions))}")


if __name__ == "__main__":
    main()
