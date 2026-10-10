# Nebius Judge Preview Deployment

This procedure creates the isolated `lexproof-api-nebius` Cloud Run service and connects the `feat/nebius-nemotron` Vercel preview to it. It does not change `lexproof-api` or `lexproof-api-paypal`.

## 1. Create Secret Manager Versions

From the repository root, ensure `backend\.env` contains `GOOGLE_CLOUD_PROJECT` and `NEBIUS_API_KEY`. `TAVILY_API_KEY` is optional. Then run:

```powershell
powershell -ExecutionPolicy Bypass -File backend\deploy\create-nebius-secrets.ps1
```

The script writes values to Secret Manager through stdin and does not print them. It creates or updates `lexproof-nebius-api-key` and, when configured, `lexproof-tavily-api-key`.

## 2. Deploy the Isolated API

Run from the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File backend\deploy\deploy-cloud-run.ps1 -Service lexproof-api-nebius -Nebius
```

The Nebius deployment uses the `lexproof-api-nebius` runtime service account, sets `LLM_PROVIDER=nebius`, Vertex fallback on, the Ultra/Super model defaults, the branch-preview CORS origin, and `LEXPROOF_JUDGE_CAN_ANALYZE=true`. It requires `lexproof-nebius-api-key`; the optional Tavily secret is attached only when present.

To retrieve and inspect the service URL:

```powershell
$url = (gcloud run services describe lexproof-api-nebius --region us-central1 --format "value(status.url)").Trim()
Invoke-RestMethod "$url/health" | ConvertTo-Json -Depth 5
```

The health response should include `ai.provider: "nebius"`, `ai.analysis_model: "nvidia/Nemotron-3-Ultra-550b-a55b"`, `ai.fast_model: "nvidia/nemotron-3-super-120b-a12b"`, `ai.fallback_to_vertex: true`, and `ai.nebius_configured: true`. It must not contain secret values.

## 3. Configure the Vercel Preview

In Vercel, open the LexProof project settings and add:

- Name: `NEXT_PUBLIC_API_URL`
- Value: the URL printed for `lexproof-api-nebius`, without a trailing slash
- Environments: Preview
- Git branch: `feat/nebius-nemotron`

The expected branch preview host is `lexproof-git-feat-nebius-nemotron-pgskannans-projects.vercel.app`. Confirm preview protection is disabled for this branch, as it is for the PayPal preview. Redeploy the branch preview after saving the environment variable. Add the preview host to Firebase Authentication's authorized domains if it is not already present.

## Judge Demo

Read-only judge users can upload one DOCX, PDF, or TXT file up to 2 MB and analyze only contracts they uploaded. The service permits at most 10 analyses per judge UID per rolling 24 hours and 30 combined Ask/translation calls per rolling hour. Other writes remain blocked. The frontend enables this demo surface only for a read-only `demo-judge-1` account when the API reports Nebius or `NEXT_PUBLIC_JUDGE_CAN_ANALYZE=true` is configured for the preview.