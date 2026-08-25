#!/bin/bash

# Compile Solidity smart contract for LexProof Blockchain Proof Registry

echo "Compiling LexProofRegistry.sol..."

# Install OpenZeppelin contracts if not already installed
npm install --save-dev @openzeppelin/contracts

# Create the output directory before compiling
mkdir -p build

# Run solc compiler
solc LexProofRegistry.sol --abi --bin -o build/ --optimize --overwrite

echo "Compilation complete!"
echo "ABI: build/LexProofRegistry.abi"
echo "Binary: build/LexProofRegistry.bin"
