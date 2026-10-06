# Video script — LexProof × PayPal (under 3:00)

Sandbox only. Record the branch preview, not production `lexproof-api`.

Preview: https://lexproof-git-feat-paypal-agentic-payments-pgskannans-projects.vercel.app

## Reset before recording

Run this from `backend/` before every take. It cancels DRAFT and SENT sandbox invoices, clears pending payment actions, and prints a summary.

```bash
python scripts/reset_paypal_demo.py --org-id lexproof-demo --confirm
```

To show Extract, a reviewer editing the payer email, and a second person approving, also pass `--extracted`, or seed with `--no-approve` on a contract that does not already have these milestones. Do not click Extract on top of existing rows. Extract appends. Do not put sandbox passwords in the repo or on screen. The buyer login stays in Devpost's private testing instructions.

Checklist:

- [ ] Reset printed a summary and the PayPal cancels returned 200, 204, or 404.
- [ ] Kickoff, UAT, and Go-live are APPROVED, unless this take starts at EXTRACTED.
- [ ] Bonus is still EXTRACTED.
- [ ] No payment action is `in_review` or `approved`.
- [ ] Two browser profiles: contract owner, and a different approver. For the judge cut, `demo-judge-1` and `demo-judge-2`.
- [ ] Sandbox buyer ready, off camera, for the $12,000 payment.

## Shot list

| Time | On screen | Caption |
|---|---|---|
| 0:00–0:15 | Title card, then the payments tab | AI agents can now move money. Who checks them? |
| 0:15–0:40 | Obligations table. Hover a clause link. The quote underneath is the contract sentence. | Obligations come from the contract, with the clause attached. |
| 0:40–0:55 | Second user approves Kickoff. The first user is not the approver. | A different person approves. The requester cannot. |
| 0:55–1:20 | Type "Invoice milestone 1". Green chips for create and send. Open the PayPal sandbox invoice: Kickoff, $12,000. | The guard allowed this call. PayPal confirmed the invoice. |
| 1:20–1:40 | Type "Invoice a $50,000 bonus to the client". Red chip. The reason names the closest real milestone. Flash the injected sentence in the contract. | Blocked. That sentence was written to instruct the agent. |
| 1:40–2:05 | Buyer pays $12,000 in the sandbox. Cut back. The row flips to PAID. A receipt badge says PayPal webhook. | PayPal told us it was paid. The model did not. |
| 2:05–2:30 | "Refund milestone 1". Chip: Needs approval. Switch to the approver. Approve, then Execute. Status REFUNDED. Click Execute again. 409. | Money out needs a second person. Once. |
| 2:30–2:50 | Public verify. "Payments, with proof". Click Verify on one receipt. The browser says the hash matched. | Anyone can recompute this. No login. |
| 2:50–3:00 | End card with the preview URL | LexProof. The contract checks the agent. |

Speak in short lines. Do not read the hashes aloud. Do not show a password, a client secret, or an access token.

If a chip is amber and says PayPal error, stop. The invoice was not confirmed. Reset and take it again.
