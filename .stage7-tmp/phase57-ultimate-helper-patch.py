from pathlib import Path

path = Path('/tmp/phase57-ultimate-run.sh')
lines = path.read_text(encoding='utf-8').splitlines()
replacement = [
    'KEPT_PACKAGES_TEXT="${KEPT_PACKAGES[*]}"',
    'export KEPT_PACKAGES_TEXT',
    'python - <<PY',
    'import os',
    'from pathlib import Path',
    'packages = os.environ.get("KEPT_PACKAGES_TEXT", "")',
]
for index in range(len(lines) - 2):
    if (
        lines[index] == 'python - <<PY'
        and lines[index + 1] == 'from pathlib import Path'
        and lines[index + 2].startswith('packages = ${KEPT_PACKAGES')
    ):
        lines[index:index + 3] = replacement
        path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        break
else:
    raise SystemExit('ultimate_package_text_anchor_missing')
