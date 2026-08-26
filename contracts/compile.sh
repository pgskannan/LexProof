#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "Compiling LexProofRegistry.sol with solc 0.8.20..."
npm install --save-dev @openzeppelin/contracts@5.0.2
mkdir -p build

npx --yes solc@0.8.20 LexProofRegistry.sol \
	--abi --bin -o build --optimize \
	--base-path . --include-path node_modules

echo "Compilation complete. Artifacts are in contracts/build/."
