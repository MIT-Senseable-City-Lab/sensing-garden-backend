#!/bin/bash
set -euo pipefail

# Build Lambda deployment packages with dependencies
# Usage: ./scripts/build_lambda.sh

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

build_package() {
    local name="$1"
    local src_dir="$REPO_ROOT/$name/src"
    local build_dir="$REPO_ROOT/$name/build"
    local zip_path="$REPO_ROOT/$name/deployment_package.zip"

    echo "Building $name..."
    rm -rf "$build_dir"
    mkdir -p "$build_dir"

    # Install dependencies
    pip3 install -r "$src_dir/requirements.txt" -t "$build_dir" --quiet

    # Copy source files
    cp -r "$src_dir"/*.py "$build_dir/"
    if [ -d "$src_dir/routes" ]; then
        cp -r "$src_dir/routes" "$build_dir/"
    fi

    # Remove unnecessary files
    find "$build_dir" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find "$build_dir" -name "*.pyc" -delete 2>/dev/null || true
    find "$build_dir" -name "*.dist-info" -exec rm -rf {} + 2>/dev/null || true

    # Create zip
    cd "$build_dir"
    zip -r "$zip_path" . --quiet
    cd "$REPO_ROOT"

    rm -rf "$build_dir"
    echo "Built $zip_path"
}

build_package "lambda"
build_package "trigger"

echo "Done."
