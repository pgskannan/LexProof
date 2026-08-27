"""Deploy LexProofRegistry to Ethereum Sepolia.

This script only deploys when explicitly run. It never targets mainnet.
Required environment variables: ETHEREUM_RPC_URL and ETHEREUM_PRIVATE_KEY.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from web3 import Web3

SEPOLIA_CHAIN_ID = 11155111
CONTRACT_NAME = "LexProofRegistry"
CONTRACTS_DIR = Path(__file__).resolve().parent


def artifact_path(extension: str) -> Path:
    canonical = CONTRACTS_DIR / "build" / f"{CONTRACT_NAME}.{extension}"
    if canonical.is_file():
        return canonical
    matches = sorted((CONTRACTS_DIR / "build").glob(f"*{CONTRACT_NAME}.{extension}"))
    if matches:
        return matches[0]
    return canonical


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def load_artifact(path: Path) -> str:
    if not path.is_file():
        raise RuntimeError(
            f"Missing compilation artifact: {path}. Run contracts/compile.sh first."
        )
    return path.read_text(encoding="utf-8").strip()


def fee_fields(web3: Web3) -> dict[str, int]:
    """Return EIP-1559 fees when supported, otherwise a legacy gas price."""
    latest_block = web3.eth.get_block("latest")
    base_fee = latest_block.get("baseFeePerGas")
    if base_fee is not None:
        try:
            priority_fee = web3.eth.max_priority_fee
        except Exception:
            priority_fee = 1_500_000_000
        return {
            "maxPriorityFeePerGas": priority_fee,
            "maxFeePerGas": base_fee * 2 + priority_fee,
        }
    return {"gasPrice": web3.eth.gas_price}


def build_deployment_transaction(
    web3: Web3,
    contract: Any,
    deployer_address: str,
    nonce: int,
) -> tuple[dict[str, Any], int]:
    """Build and estimate deployment transaction gas before adding gas."""
    transaction = contract.constructor(deployer_address).build_transaction(
        {
            "from": deployer_address,
            "nonce": nonce,
            "chainId": SEPOLIA_CHAIN_ID,
            **fee_fields(web3),
        }
    )
    transaction.pop("gas", None)
    estimated_gas = web3.eth.estimate_gas(transaction)
    transaction["gas"] = estimated_gas
    return transaction, estimated_gas


def print_preflight(web3: Web3, deployer_address: str, transaction: dict[str, Any], estimated_gas: int) -> None:
    """Print only public deployment preflight information."""
    fee_per_gas = transaction.get("maxFeePerGas", transaction.get("gasPrice"))
    balance = web3.eth.get_balance(deployer_address)
    estimated_cost = estimated_gas * fee_per_gas
    print("rpc_connected=true")
    print(f"chain_id={web3.eth.chain_id}")
    print(f"deployer_address={deployer_address}")
    print(f"deployer_balance_wei={balance}")
    print(f"estimated_gas={estimated_gas}")
    print(f"estimated_deployment_cost_wei={estimated_cost}")


def main(preflight_only: bool = False) -> None:
    load_dotenv(CONTRACTS_DIR.parent / "backend" / ".env")

    rpc_url = require_env("ETHEREUM_RPC_URL")
    private_key = require_env("ETHEREUM_PRIVATE_KEY")
    configured_chain_id = int(os.getenv("ETHEREUM_CHAIN_ID", str(SEPOLIA_CHAIN_ID)))
    if configured_chain_id != SEPOLIA_CHAIN_ID:
        raise RuntimeError(
            f"Refusing deployment: ETHEREUM_CHAIN_ID must be {SEPOLIA_CHAIN_ID}, "
            f"got {configured_chain_id}"
        )

    abi = json.loads(load_artifact(artifact_path("abi")))
    bytecode = load_artifact(artifact_path("bin"))
    if not bytecode.startswith("0x"):
        bytecode = "0x" + bytecode

    web3 = Web3(Web3.HTTPProvider(rpc_url))
    if not web3.is_connected():
        raise RuntimeError("Could not connect to ETHEREUM_RPC_URL")
    chain_id = web3.eth.chain_id
    if chain_id != SEPOLIA_CHAIN_ID:
        raise RuntimeError(
            f"Refusing deployment on chain ID {chain_id}; expected Sepolia ({SEPOLIA_CHAIN_ID})"
        )

    account = web3.eth.account.from_key(private_key)
    contract = web3.eth.contract(abi=abi, bytecode=bytecode)
    nonce = web3.eth.get_transaction_count(account.address)
    transaction, estimated_gas = build_deployment_transaction(
        web3, contract, account.address, nonce
    )
    print_preflight(web3, account.address, transaction, estimated_gas)
    if preflight_only:
        return

    signed = account.sign_transaction(transaction)
    transaction_hash = web3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = web3.eth.wait_for_transaction_receipt(transaction_hash)

    if receipt.status != 1 or not receipt.contractAddress:
        raise RuntimeError("Deployment transaction failed or returned no contract address")

    print(f"deployed_contract_address={receipt.contractAddress}")
    print(f"transaction_hash={transaction_hash.hex()}")
    print(f"chain_id={chain_id}")
    print(f"block_number={receipt.blockNumber}")


if __name__ == "__main__":
    try:
        main(preflight_only="--preflight" in sys.argv[1:])
    except (ValueError, RuntimeError) as error:
        raise SystemExit(f"Deployment failed: {error}") from error
