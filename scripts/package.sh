#!/bin/bash
# Package the built plugin as out/decky-ssh-warden.zip, the layout Decky's
# "Install plugin from ZIP" (Developer settings) expects. Run `pnpm build` first.
set -euo pipefail
cd "$(dirname "$0")/.."

NAME=decky-ssh-warden
[ -f dist/index.js ] || { echo "dist/index.js missing, run pnpm build first" >&2; exit 1; }

STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT
mkdir -p "$STAGE/$NAME/dist"
cp plugin.json package.json main.py LICENSE README.md "$STAGE/$NAME/"
cp dist/index.js "$STAGE/$NAME/dist/"
rsync -a --exclude '__pycache__' py_modules "$STAGE/$NAME/"

mkdir -p out
rm -f "out/$NAME.zip"
(cd "$STAGE" && COPYFILE_DISABLE=1 zip -qrX "$OLDPWD/out/$NAME.zip" "$NAME")
echo "out/$NAME.zip"
