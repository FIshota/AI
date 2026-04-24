#!/usr/bin/env bash
# Verify the tamper-evident audit log hash chain.
# Exits 0 if the chain is valid, 2 on any violation (list is printed).

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

LOG_DIR="${1:-${PROJECT_ROOT}/logs/security}"

cd "${PROJECT_ROOT}"
python -m core.audit_chain --verify "${LOG_DIR}"
status=$?

if [ "${status}" -eq 0 ]; then
    exit 0
fi

# Normalise any non-zero exit (including python errors) to 2 per spec.
exit 2
