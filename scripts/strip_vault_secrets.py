#!/usr/bin/env python3
"""
Strip Postman Cloud Vault secret references from committed environment files.

When the Postman desktop client syncs environments, it can inject references
to personal vault secrets (e.g. a Supabase service-role key from your account
vault). Even though only a `secretId` lives in the file — not the key value —
both GitHub push protection and Postman desktop will warn on it because the
variable name looks like a real secret.

This script removes any environment value that has either:
  - `secret: true` AND a `source:` block referencing a Postman cloud vault
  - any reference under `source.postman` (vaultId / secretId)
  - a `key` that matches well-known vault-name patterns
    (supabase_, anon_key, service_role, github_pat, etc.)

Idempotent and safe to wire into a pre-commit hook.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    import yaml  # PyYAML
except ImportError:
    print("ERROR: PyYAML is required. Install with: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

ENV_DIR = Path(__file__).resolve().parents[1] / "postman" / "environments"

SUSPICIOUS_KEY_PATTERNS = [
    re.compile(r"supabase", re.I),
    re.compile(r"service[_-]?role", re.I),
    re.compile(r"anon[_-]?key", re.I),
    re.compile(r"github[_-]?pat", re.I),
    re.compile(r"^ghp_", re.I),
    re.compile(r"^pmak[_-]", re.I),
    re.compile(r"openai[_-]?api[_-]?key", re.I),
    re.compile(r"aws[_-]?secret", re.I),
]


def is_vault_reference(value_entry: dict) -> tuple[bool, str]:
    """Return (should_strip, reason)."""
    if not isinstance(value_entry, dict):
        return False, ""

    source = value_entry.get("source")
    if isinstance(source, dict):
        postman = source.get("postman")
        if isinstance(postman, dict) and (postman.get("vaultId") or postman.get("secretId")):
            return True, "postman vault reference"

    if value_entry.get("secret") is True and "source" in value_entry:
        return True, "secret: true with source"

    key = str(value_entry.get("key", ""))
    for pat in SUSPICIOUS_KEY_PATTERNS:
        if pat.search(key):
            return True, f"key matches pattern {pat.pattern}"

    return False, ""


def process_file(path: Path) -> int:
    text = path.read_text()
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        print(f"  ! could not parse {path.name}: {e}", file=sys.stderr)
        return 0
    if not isinstance(data, dict) or "values" not in data:
        return 0

    original_values = data.get("values") or []
    if not isinstance(original_values, list):
        return 0

    kept = []
    removed = 0
    for v in original_values:
        strip, reason = is_vault_reference(v)
        if strip:
            removed += 1
            print(f"  - {path.name}: stripped key={v.get('key')!r} ({reason})")
        else:
            kept.append(v)

    if removed == 0:
        return 0

    data["values"] = kept
    # Preserve a clean, deterministic YAML format
    new_text = yaml.safe_dump(data, sort_keys=False, default_flow_style=False, width=10_000)
    path.write_text(new_text)
    return removed


def main(_argv: list[str]) -> int:
    total = 0
    for path in sorted(ENV_DIR.glob("*.environment.yaml")):
        total += process_file(path)
    if total == 0:
        print("No vault references found. Clean.")
    else:
        print(f"Stripped {total} entries total.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
