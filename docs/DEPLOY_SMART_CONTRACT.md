# Deploy LexProofRegistry Smart Contract to Ethereum Sepolia

## Overview

This guide provides step-by-step instructions for deploying the LexProofRegistry smart contract to the Ethereum Sepolia testnet.

## Prerequisites

### 1. Install Required Tools

#### Node.js and npm
```bash
# Check Node.js version (should be 16+)
node --version

# Install npm packages
npm install --save-dev @openzeppelin/contracts
```

#### Solidity Compiler (solc)
```bash
# Download solc (version 0.8.20+)
# Visit: https://docs.soliditylang.org/

# Or use npm
npm install -g solc
```

#### MetaMask (Browser Extension)
- Install MetaMask from Chrome Web Store
- Create a wallet with Sepolia testnet
- Get test ETH from: https://sepoliafaucet.com/

#### Ethereum Sepolia Faucet
- Get free test ETH for testing
- Recommended faucets:
  - https://sepoliafaucet.com/
  - https://sepolia.dev/faucet/
  - https://faucet.sepolia.dev/

### 2. Prepare Deployment Script

Create a deployment script: `contracts/deploy.js`

```javascript
const hre = require("hardhat");

async function main() {
  console.log("Deploying LexProofRegistry to Sepolia...");

  // Get the deployer account
  const [deployer] = await hre.ethers.getSigners();
  console.log("Deploying with account:", deployer.address);

  // Get account balance
  const balance = await deployer.getBalance();
  console.log("Account balance:", hre.ethers.formatEther(balance), "ETH");

  // Deploy contract
  const LexProofRegistry = await hre.ethers.getContractFactory("LexProofRegistry");
  const registry = await LexProofRegistry.deploy(deployer.address);
  await registry.waitForDeployment();

  const address = await registry.getAddress();
  console.log("LexProofRegistry deployed to:", address);

  // Save contract address to .env file
  const fs = require("fs");
  const envContent = `
# Ethereum Sepolia
ETHEREUM_RPC_URL=https://sepolia.infura.io/v3/YOUR_INFURA_PROJECT_ID
CONTRACT_ADDRESS=${address}
BLOCKCHAIN_PRIVATE_KEY=YOUR_PRIVATE_KEY
`;

  fs.writeFileSync(".env", envContent);
  console.log("Contract address saved to .env file");
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
```

## Deployment Steps

### Step 1: Compile the Smart Contract

```bash
cd contracts

# Compile with optimization
solc --abi --bin LexProofRegistry.sol -o build/ --optimize --overwrite

# Or use Hardhat (recommended)
npm install --save-dev hardhat
npx hardhat compile
```

### Step 2: Prepare Deployment Environment

#### Option A: Hardhat Deployment (Recommended)

```bash
# Install Hardhat
npm install --save-dev hardhat @nomicfoundation/hardhat-toolbox

# Create hardhat.config.js
cat > hardhat.config.js << 'EOF'
require("@nomicfoundation/hardhat-toolbox");

module.exports = {
  solidity: {
    version: "0.8.20",
    settings: {
      optimizer: {
        enabled: true,
        runs: 200
      }
    }
  },
  networks: {
    sepolia: {
      url: process.env.ETHEREUM_RPC_URL || "https://sepolia.infura.io/v3/YOUR_PROJECT_ID",
      accounts: [process.env.PRIVATE_KEY]
    }
  }
};
EOF
```

#### Option B: Direct Deployment

```bash
# Set environment variables
export ETHEREUM_RPC_URL=https://sepolia.infura.io/v3/YOUR_PROJECT_ID
export PRIVATE_KEY=YOUR_PRIVATE_KEY

# Run deployment script
node contracts/deploy.js
```

### Step 3: Deploy to Sepolia Testnet

#### Using Hardhat

```bash
# Deploy to Sepolia
npx hardhat run contracts/deploy.js --network sepolia

# Or use Hardhat console
npx hardhat console --network sepolia

# In console:
const LexProofRegistry = await ethers.getContractFactory("LexProofRegistry");
const registry = await LexProofRegistry.deploy(deployer.address);
await registry.waitForDeployment();
console.log("Contract address:", await registry.getAddress());
```

#### Using Remix (Alternative)

1. Go to [Remix IDE](https://remix.ethereum.org/)
2. Create new file `LexProofRegistry.sol`
3. Paste contract code
4. Go to "Deploy & Run Transactions" tab
5. Select "Sepolia Testnet" as environment
6. Enter your deployer account
7. Click "Deploy"

### Step 4: Verify Contract on Etherscan

#### Using Hardhat

```bash
# Install Etherscan plugin
npm install --save-dev @nomicfoundation/hardhat-etherscan

# Add to hardhat.config.js
require("@nomicfoundation/hardhat-toolbox");
require("@nomicfoundation/hardhat-etherscan");

module.exports = {
  // ... existing config
  etherscan: {
    apiKey: {
      sepolia: process.env.ETHERSCAN_API_KEY
    }
  }
};
```

```bash
# Verify contract
npx hardhat verify --network sepolia \
  <CONTRACT_ADDRESS> \
  <DEPLOYER_ADDRESS>
```

#### Using Remix

1. Go to "Verify and Publish" tab
2. Select "Sepolia" as network
3. Fill in required fields:
   - Compiler version: 0.8.20
   - Optimization: Checked
   - Runs: 200
   - Constructor arguments: Deployer address
4. Click "Verify and Publish"

### Step 5: Test Contract Deployment

```javascript
// Test contract functions
const { ethers } = require("hardhat");

async function testContract() {
  const [signer] = await ethers.getSigners();

  // Get contract instance
  const contract = await ethers.getContractAt(
    "LexProofRegistry",
    process.env.CONTRACT_ADDRESS
  );

  console.log("Contract address:", await contract.getAddress());

  // Test registerProof
  const tx = await contract.registerProof(
    ethers.ZeroHash,
    ethers.ZeroHash,
    ethers.ZeroHash,
    ethers.ZeroHash,
    75,
    85,
    "1.0.0",
    3
  );

  console.log("Transaction hash:", tx.hash);
  console.log("Waiting for confirmation...");
  await tx.wait();
  console.log("Transaction confirmed!");
}

testContract().catch(console.error);
```

### Step 6: Configure Backend

#### Update Environment Variables

Create or update `.env` file:

```bash
# Ethereum Sepolia
ETHEREUM_RPC_URL=https://sepolia.infura.io/v3/YOUR_PROJECT_ID
CONTRACT_ADDRESS=0x1234567890123456789012345678901234567890
BLOCKCHAIN_PRIVATE_KEY=YOUR_PRIVATE_KEY

# Optional: Google Secret Manager for production
# SECRET_MANAGER_PROJECT_ID=your-project
# SECRET_MANAGER_KEY=blockchain-private-key
```

#### Update Backend Configuration

```python
# backend/app/lexproof/config/settings.py

class BlockchainSettings(BaseSettings):
    """Blockchain configuration"""

    ethereum_rpc_url: str = Field(
        default="https://sepolia.infura.io/v3/YOUR_PROJECT_ID",
        description="Ethereum RPC URL"
    )
    contract_address: str = Field(
        default="0x1234567890123456789012345678901234567890",
        description="LexProofRegistry contract address"
    )
    blockchain_private_key: SecretStr = Field(
        default=SecretStr(""),
        description="Private key for signing transactions (never commit to source control)"
    )
```

### Step 7: Test Backend Integration

```bash
# Run health check
curl http://localhost:8000/api/blockchain/health

# Test anchoring a proof
curl -X POST http://localhost:8000/api/blockchain/passports/{passport_id}/anchor \
  -H "Content-Type: application/json" \
  -d '{
    "contract_id": "test-contract",
    "contract_hash": "0x1234567890abcdef...",
    "policy_hash": "0xabcdef123456...",
    "analysis_hash": "0x9876543210fedcba...",
    "evidence_hash": "0xfedcba098765...",
    "risk_score": 75,
    "compliance_score": 85,
    "policy_version": "1.0.0",
    "evidence_count": 3
  }'
```

## Security Considerations

### 1. Private Key Security

**NEVER** commit private keys to source control:

```bash
# .gitignore
.env
*.pem
*.key
```

### 2. Key Management

#### Development
- Use environment variables
- Never hardcode private keys

#### Production
- Use Google Secret Manager
- Rotate keys regularly
- Use key rotation policies
- Implement access controls

### 3. Access Control

The contract has built-in access control:

```solidity
contract LexProofRegistry is Ownable, ReentrancyGuard {
    // Only owner can update proof status
    function updateProofStatus(...) external onlyOwner { ... }
}
```

### 4. Gas Optimization

The contract uses:
- `ReentrancyGuard` to prevent reentrancy attacks
- `Ownable` for access control
- Optimized bytecode for lower gas costs

## Troubleshooting

### Issue: Insufficient Test ETH

**Error**: "insufficient funds for gas"

**Solution**:
1. Get more test ETH from faucets
2. Check your account balance on Sepolia
3. Ensure you're using the correct network

### Issue: Transaction Reverts

**Error**: "execution reverted"

**Solution**:
1. Check gas limit is sufficient
2. Verify contract deployment address
3. Check contract initialization
4. Review transaction parameters

### Issue: Contract Verification Failed

**Error**: "Contract verification failed"

**Solution**:
1. Verify compiler version matches
2. Check optimization settings
3. Ensure constructor arguments are correct
4. Try verifying with different method

### Issue: Backend Connection Error

**Error**: "Failed to connect to Ethereum RPC"

**Solution**:
1. Check RPC URL is correct
2. Verify Infura project ID
3. Check network connectivity
4. Ensure RPC endpoint is not rate-limited

## Post-Deployment Checklist

- [ ] Contract deployed to Sepolia
- [ ] Contract verified on Etherscan
- [ ] Backend configured with contract address
- [ ] Private key loaded securely
- [ ] Health endpoint responding
- [ ] Proof anchoring working
- [ ] Proof verification working
- [ ] Transaction monitoring active
- [ ] Gas price alerts configured
- [ ] Backup procedures in place

## Monitoring

### Key Metrics to Monitor

1. **Transaction Success Rate**
   - Target: > 95%
   - Alert on: < 90%

2. **Average Confirmation Time**
   - Target: < 2 minutes
   - Alert on: > 5 minutes

3. **Gas Price Trends**
   - Monitor for optimal gas prices
   - Set up alerts for high gas

4. **Contract Interactions**
   - Track proof registrations
   - Monitor verification calls
   - Alert on unusual patterns

### Recommended Tools

- **Etherscan**: Contract monitoring
- **Grafana**: Custom metrics dashboard
- **Alertmanager**: Alert notifications
- **Prometheus**: Metrics collection

## Cost Estimation

### Sepolia Testnet (Free)

- Deployment cost: ~0.001 ETH (testnet)
- Gas for proof registration: ~0.00005 ETH
- Gas for verification: ~0.00001 ETH

### Mainnet (Real Costs)

- Deployment cost: ~$50-100
- Gas per proof: ~$1-5 (depending on gas price)
- Gas per verification: ~$0.50-1

## Next Steps

1. **Test Thoroughly**: Run comprehensive tests
2. **Monitor**: Set up monitoring and alerting
3. **Document**: Update team with deployment details
4. **Train**: Train team on usage and security
5. **Plan Mainnet**: Plan for mainnet deployment

## Support

For issues or questions:

- Check [Ethereum Sepolia Documentation](https://sepolia.dev/)
- Review [OpenZeppelin Contracts](https://docs.openzeppelin.com/contracts/)
- Check [Web3.py Documentation](https://web3py.readthedocs.io/)
- Open an issue in the LexProof repository

## References

- [Solidity Documentation](https://docs.soliditylang.org/)
- [OpenZeppelin Contracts](https://docs.openzeppelin.com/contracts/)
- [Hardhat Documentation](https://hardhat.org/docs)
- [Ethereum Sepolia Testnet](https://sepolia.dev/)
- [Etherscan Sepolia](https://sepolia.etherscan.io/)
- [Web3.py](https://web3py.readthedocs.io/)
