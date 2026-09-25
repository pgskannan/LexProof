"""Transaction fee parameters for LexProof's Sepolia anchoring transactions.

Both anchoring paths (evidence items via BlockchainService.anchor_evidence and
passport roots via PassportBlockchainService.anchor_passport_root) used to set
``gasPrice = eth.gas_price``: no priority tip above the node's estimate. On a
busy Sepolia that left transactions in the mempool for minutes. On
2026-09-25 a passport-root anchor took ~3 minutes to mine, outlasting the
120s receipt wait, so the request reported failure while the transaction
later succeeded.

``anchoring_fee_params`` returns EIP-1559 fields with a guaranteed minimum
tip, so the transaction is attractive to the next block, and a max fee of
2x the current base fee plus that tip, so a base-fee rise over the next few
blocks doesn't strand it. The account only pays base fee + tip; the max fee
is a cap. Falls back to the plain legacy ``gasPrice`` when the node or a
test double can't answer the EIP-1559 queries.
"""

from __future__ import annotations

from typing import Any, Dict

MIN_PRIORITY_FEE_WEI = 2_000_000_000  # 2 gwei


def anchoring_fee_params(w3: Any) -> Dict[str, int]:
    try:
        base_fee = int(w3.eth.get_block("latest")["baseFeePerGas"])
        try:
            suggested_tip = int(w3.eth.max_priority_fee)
        except Exception:  # noqa: BLE001 - some providers don't implement eth_maxPriorityFeePerGas
            suggested_tip = 0
        tip = max(suggested_tip, MIN_PRIORITY_FEE_WEI)
        if base_fee < 0:
            raise ValueError("negative base fee")
        return {"maxFeePerGas": 2 * base_fee + tip, "maxPriorityFeePerGas": tip}
    except Exception:  # noqa: BLE001 - pre-London chain, mock provider, or RPC hiccup
        return {"gasPrice": int(w3.eth.gas_price)}
