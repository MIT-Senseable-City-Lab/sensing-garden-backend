#!/bin/bash
set -euo pipefail

# Build Lambda deployment packages with dependencies
# Usage: ./scripts/build_lambda.sh [lambda|trigger ...]

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

build_package() {
    local name="$1"
    local src_dir="$REPO_ROOT/$name/src"
    local build_dir="$REPO_ROOT/$name/build"
    local zip_path="$REPO_ROOT/$name/deployment_package.zip"

    echo "Building $name..."
    rm -rf "$build_dir"
    mkdir -p "$build_dir"

    # Install dependencies targeting Lambda runtime (Amazon Linux x86_64, Python 3.11)
    pip3 install -r "$src_dir/requirements.txt" -t "$build_dir" \
        --platform manylinux2014_x86_64 \
        --only-binary=:all: \
        --python-version 3.11 \
        --implementation cp \
        --no-cache-dir \
        --quiet

    # Copy source files. -L: dereference symlinks (schemas.py is symlinked to
    # shared/schemas.py -- plain `cp -r` preserves symlinks as-is for recursive
    # copies, which would ship a broken relative link inside the zip instead of
    # the file).
    cp -rL "$src_dir"/*.py "$build_dir/"
    if [ -d "$src_dir/routes" ]; then
        cp -rL "$src_dir/routes" "$build_dir/"
    fi

    # Remove unnecessary files
    find "$build_dir" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find "$build_dir" -name "*.pyc" -delete 2>/dev/null || true
    find "$build_dir" -name "*.dist-info" -exec rm -rf {} + 2>/dev/null || true

    # Create zip
    rm -f "$zip_path"
    (cd "$build_dir" && python3 -m zipfile -c "$zip_path" .)

    rm -rf "$build_dir"
    echo "Built $zip_path"
}

packages=("$@")
if [ ${#packages[@]} -eq 0 ]; then
    packages=("lambda" "trigger")
fi

for package in "${packages[@]}"; do
    if [ "$package" != "lambda" ] && [ "$package" != "trigger" ]; then
        echo "Unknown package: $package" >&2
        exit 1
    fi
    build_package "$package"
done

echo "Done."
