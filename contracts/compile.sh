#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "Compiling LexProofRegistry.sol and LexProofPassportRegistry.sol with solc 0.8.20..."
npm install --save-dev @openzeppelin/contracts@5.0.2
mkdir -p build

# Two independent contracts, compiled together so each gets its own ABI/BIN
# artifact (solc's -o output naming is per source file + contract name, so
# this does not merge or otherwise couple the two contracts' artifacts).
# LexProofRegistry.sol (existing per-evidence-item anchor registry) is NOT
# modified by adding LexProofPassportRegistry.sol to this compile step.
npx --yes solc@0.8.20 LexProofRegistry.sol LexProofPassportRegistry.sol \
	--abi --bin -o build --optimize \
	--base-path . --include-path node_modules

echo "Compilation complete. Artifacts are in contracts/build/."
