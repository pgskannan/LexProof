# LexProof Configuration

The backend reads settings from environment variables or `backend/.env`.
Never commit credentials or private keys.

## Local development

```text
LEXPROOF_CORS_ORIGINS=http://localhost:3000
GOOGLE_CLOUD_PROJECT=lexproof-afc7c
FIREBASE_PROJECT_ID=lexproof-afc7c
FIREBASE_CLIENT_EMAIL=...
FIREBASE_PRIVATE_KEY=...
FIREBASE_STORAGE_BUCKET=...
GEMINI_MODEL=gemini-2.0-flash-001
ETHEREUM_RPC_URL=https://sepolia.infura.io/v3/...
CONTRACT_ADDRESS=0x...
BLOCKCHAIN_PRIVATE_KEY=...
```

`LEXPROOF_CORS_ORIGINS` accepts comma-separated origins. The default is
`http://localhost:3000`. Private API routes require a Firebase ID token in an
`Authorization: Bearer <token>` header; `/verify` remains public.