"""Fee parameters for Sepolia anchoring transactions (see services/blockchain_fees.py)."""

from types import SimpleNamespace

from web3 import EthereumTesterProvider, Web3

from app.lexproof.services.blockchain_fees import MIN_PRIORITY_FEE_WEI, anchoring_fee_params


class _Eth:
    def __init__(self, base_fee=None, tip=None, gas_price=10**9, tip_error=False, block_error=False):
        self._base_fee, self._tip, self.gas_price = base_fee, tip, gas_price
        self._tip_error, self._block_error = tip_error, block_error

    def get_block(self, _):
        if self._block_error or self._base_fee is None:
            raise ValueError("no baseFeePerGas on this chain")
        return {"baseFeePerGas": self._base_fee}

    @property
    def max_priority_fee(self):
        if self._tip_error:
            raise ValueError("method not supported")
        return self._tip


def w3(**kwargs):
    return SimpleNamespace(eth=_Eth(**kwargs))


def test_eip1559_fees_use_suggested_tip_when_it_beats_the_floor():
    fees = anchoring_fee_params(w3(base_fee=5 * 10**9, tip=3 * 10**9))
    assert fees == {"maxPriorityFeePerGas": 3 * 10**9, "maxFeePerGas": 2 * 5 * 10**9 + 3 * 10**9}


def test_tip_never_drops_below_the_floor():
    """The original bug: a zero/low tip left anchors unmined for minutes."""
    fees = anchoring_fee_params(w3(base_fee=10**8, tip=1))
    assert fees["maxPriorityFeePerGas"] == MIN_PRIORITY_FEE_WEI
    assert fees["maxFeePerGas"] == 2 * 10**8 + MIN_PRIORITY_FEE_WEI


def test_missing_max_priority_fee_rpc_still_uses_eip1559_with_the_floor():
    fees = anchoring_fee_params(w3(base_fee=10**9, tip_error=True))
    assert fees == {"maxPriorityFeePerGas": MIN_PRIORITY_FEE_WEI, "maxFeePerGas": 2 * 10**9 + MIN_PRIORITY_FEE_WEI}


def test_falls_back_to_legacy_gas_price_without_base_fee():
    assert anchoring_fee_params(w3(block_error=True, gas_price=7)) == {"gasPrice": 7}


def test_real_local_evm_returns_valid_eip1559_fields():
    local = Web3(EthereumTesterProvider())
    fees = anchoring_fee_params(local)
    assert fees["maxPriorityFeePerGas"] >= MIN_PRIORITY_FEE_WEI
    assert fees["maxFeePerGas"] >= fees["maxPriorityFeePerGas"]
