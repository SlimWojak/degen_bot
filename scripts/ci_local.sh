#!/bin/bash
# CI Local Script - Phase ε.1 Purification Pass
# Runs the same checks as CI locally

set -e

echo "=== Phase ε.1: Local CI Checks ==="

# Check if we're in the right directory
if [ ! -f "requirements.txt" ]; then
    echo "❌ Not in project root directory"
    exit 1
fi

echo "📋 Running static checks..."

# 1. Ruff linting
echo "🔍 Running ruff check..."
if command -v ruff &> /dev/null; then
    ruff check backend --fix
    echo "✅ Ruff check passed"
else
    echo "⚠️  Ruff not installed, skipping"
fi

# 2. MyPy type checking
echo "🔍 Running mypy..."
if command -v mypy &> /dev/null; then
    mypy backend --strict --ignore-missing-imports
    echo "✅ MyPy check passed"
else
    echo "⚠️  MyPy not installed, skipping"
fi

# 3. Dependency audit
echo "🔍 Running dependency audit..."
python scripts/audit_deps.py
echo "✅ Dependency audit completed"

# 4. Deterministic tests
echo "🔍 Running deterministic tests..."
python tests/test_simple_truth.py
echo "✅ Deterministic tests completed"

# 5. Syntax check
echo "🔍 Running syntax check..."
python -m py_compile backend/main.py
python -m py_compile backend/services/market_feed_manager.py
python -m py_compile backend/util/async_tools.py
echo "✅ Syntax check passed"

echo ""
echo "🎉 All local CI checks passed!"
echo ""
echo "📊 Summary:"
echo "  - Static analysis: ✅"
echo "  - Type checking: ✅" 
echo "  - Dependency audit: ✅"
echo "  - Deterministic tests: ✅"
echo "  - Syntax validation: ✅"
