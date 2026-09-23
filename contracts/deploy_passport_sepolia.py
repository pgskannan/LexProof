"""Deploy LexProofPassportRegistry to Ethereum Sepolia.

This is a dedicated deployment path for the additive passport-root registry.
It never changes or overwrites ETHEREUM_CONTRACT_ADDRESS, which remains the
configuration for the existing LexProofRegistry evidence anchors.

Normal deployment requires ETHEREUM_RPC_URL and ETHEREUM_PRIVATE_KEY. Use
``--validate-only`` to verify the local compiled artifact and constructor
without connecting to a network, reading a private key, or sending a
transaction.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from web3 import Web3

SEPOLIA_CHAIN_ID = 11155111
CONTRACT_NAME = "LexProofPassportRegistry"
PASSPORT_REGISTRY_ENV = "ETHEREUM_PASSPORT_REGISTRY_ADDRESS"
CONTRACTS_DIR = Path(__file__).resolve().parent
BUILD_DIR = CONTRACTS_DIR / "build"


def artifact_path(extension: str) -> Path:
    canonical = BUILD_DIR / f"{CONTRACT_NAME}.{extension}"
    if canonical.is_file():
        return canonical
    matches = sorted(BUILD_DIR.glob(f"*{CONTRACT_NAME}.{extension}"))
    if matches:
        return matches[0]
    return canonical


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def load_artifacts() -> tuple[list[dict[str, Any]], str]:
    abi_path = artifact_path("abi")
    bin_path = artifact_path("bin")
    if not abi_path.is_file() or not bin_path.is_file():
        raise RuntimeError(
            f"Missing compilation artifacts for {CONTRACT_NAME}. "
            "Run contracts/compile.sh first."
        )

    abi = json.loads(abi_path.read_text(encoding="utf-8"))
    bytecode = bin_path.read_text(encoding="utf-8").strip()
    if not bytecode.startswith("0x"):
        bytecode = "0x" + bytecode
    return abi, bytecode


def validate_artifacts() -> tuple[list[dict[str, Any]], str]:
    abi, bytecode = load_artifacts()
    constructor = next(
        (entry for entry in abi if entry.get("type") == "constructor"),
        None,
    )
    constructor_inputs = constructor.get("inputs", []) if constructor else []
    if len(constructor_inputs) != 1 or constructor_inputs[0].get("type") != "address":
        raise RuntimeError(
            f"{CONTRACT_NAME} must have exactly one address constructor parameter (initialOwner)"
        )

    function_names = {
        entry.get("name")
        for entry in abi
        if entry.get("type") == "function"
    }
    required_functions = {
        "anchorPassportRoot",
        "getPassportRoot",
        "verifyPassportRoot",
        "setRegistrar",
        "owner",
        "authorizedRegistrars",
    }
    missing = required_functions - function_names
    if missing:
        raise RuntimeError(
            f"{CONTRACT_NAME} artifact is missing required functions: {sorted(missing)}"
        )
    if not bytecode or bytecode == "0x":
        raise RuntimeError(f"{CONTRACT_NAME} bytecode is empty")
    return abi, bytecode


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
    """Build and estimate the passport-registry deployment transaction."""
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


def print_preflight(
    web3: Web3,
    deployer_address: str,
    transaction: dict[str, Any],
    estimated_gas: int,
) -> None:
    fee_per_gas = transaction.get("maxFeePerGas", transaction.get("gasPrice"))
    balance = web3.eth.get_balance(deployer_address)
    estimated_cost = estimated_gas * fee_per_gas
    print("registry=LexProofPassportRegistry")
    print(f"rpc_connected=true")
    print(f"chain_id={web3.eth.chain_id}")
    print(f"deployer_address={deployer_address}")
    print(f"deployer_balance_wei={balance}")
    print(f"estimated_gas={estimated_gas}")
    print(f"estimated_deployment_cost_wei={estimated_cost}")
    print(f"address_configuration={PASSPORT_REGISTRY_ENV}")


def verify_deployed_contract(
    web3: Web3,
    abi: list[dict[str, Any]],
    deployed_address: str,
    initial_owner: str,
) -> None:
    """Verify the deployed passport registry and its bootstrap authorization."""
    if web3.eth.chain_id != SEPOLIA_CHAIN_ID:
        raise RuntimeError(
            f"Post-deployment verification saw chain ID {web3.eth.chain_id}; "
            f"expected Sepolia ({SEPOLIA_CHAIN_ID})"
        )

    checksum_address = Web3.to_checksum_address(deployed_address)
    code = web3.eth.get_code(checksum_address)
    if not code or code == b"\x00":
        raise RuntimeError(
            f"No contract bytecode found at deployed passport registry address {checksum_address}"
        )

    contract = web3.eth.contract(address=checksum_address, abi=abi)
    owner = Web3.to_checksum_address(contract.functions.owner().call())
    expected_owner = Web3.to_checksum_address(initial_owner)
    if owner != expected_owner:
        raise RuntimeError(
            f"Passport registry owner mismatch: expected {expected_owner}, got {owner}"
        )
    if not contract.functions.authorizedRegistrars(expected_owner).call():
        raise RuntimeError(
            f"Initial owner {expected_owner} is not authorized as a passport registrar"
        )

    print("post_deployment_verification=passed")
    print(f"verified_chain_id={web3.eth.chain_id}")
    print(f"verified_contract_address={checksum_address}")
    print(f"verified_owner={owner}")
    print(f"verified_initial_owner_registrar=true")
    print("verified_contract_code_exists=true")


def main(validate_only: bool = False) -> None:
    validate_artifacts()
    if validate_only:
        print(f"validated_contract={CONTRACT_NAME}")
        print(f"address_configuration={PASSPORT_REGISTRY_ENV}")
        print(f"chain_id={SEPOLIA_CHAIN_ID}")
        print("network_access=false")
        print("transaction_sent=false")
        return

    load_dotenv(CONTRACTS_DIR.parent / "backend" / ".env")
    rpc_url = require_env("ETHEREUM_RPC_URL")
    private_key = require_env("ETHEREUM_PRIVATE_KEY")
    configured_chain_id = int(os.getenv("ETHEREUM_CHAIN_ID", str(SEPOLIA_CHAIN_ID)))
    if configured_chain_id != SEPOLIA_CHAIN_ID:
        raise RuntimeError(
            f"Refusing deployment: ETHEREUM_CHAIN_ID must be {SEPOLIA_CHAIN_ID}, "
            f"got {configured_chain_id}"
        )

    abi, bytecode = load_artifacts()
    web3 = Web3(Web3.HTTPProvider(rpc_url))
    if not web3.is_connected():
        raise RuntimeError("Could not connect to ETHEREUM_RPC_URL")
    if web3.eth.chain_id != SEPOLIA_CHAIN_ID:
        raise RuntimeError(
            f"Refusing deployment on chain ID {web3.eth.chain_id}; "
            f"expected Sepolia ({SEPOLIA_CHAIN_ID})"
        )

    account = web3.eth.account.from_key(private_key)
    contract = web3.eth.contract(abi=abi, bytecode=bytecode)
    transaction, estimated_gas = build_deployment_transaction(
        web3,
        contract,
        account.address,
        web3.eth.get_transaction_count(account.address),
    )
    print_preflight(web3, account.address, transaction, estimated_gas)

    signed = account.sign_transaction(transaction)
    transaction_hash = web3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = web3.eth.wait_for_transaction_receipt(transaction_hash)
    if receipt.status != 1 or not receipt.contractAddress:
        raise RuntimeError("Passport registry deployment failed or returned no contract address")

    deployed_address = Web3.to_checksum_address(receipt.contractAddress)
    verify_deployed_contract(web3, abi, deployed_address, account.address)
    print(f"{PASSPORT_REGISTRY_ENV}={deployed_address}")
    print(f"transaction_hash={transaction_hash.hex()}")
    print(f"chain_id={web3.eth.chain_id}")
    print(f"block_number={receipt.blockNumber}")
    print("initial_owner_is_registrar=true")
    print("existing_evidence_registry_address_unchanged=true")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate local artifacts without network access or a transaction",
    )
    args = parser.parse_args()
    main(validate_only=args.validate_only)
