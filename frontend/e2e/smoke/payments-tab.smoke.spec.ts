import { expect, test } from '@playwright/test'

test('payments tab renders seeded PayPal sandbox data', async ({ page }) => {
  await page.goto('/payments-preview')
  await expect(page.getByTestId('paypal-sandbox-badge')).toHaveText('PayPal Sandbox')
  await expect(page.getByText('Kickoff')).toBeVisible()
  await expect(page.getByText('USD 12000.00')).toBeVisible()
  await expect(page.getByTestId('mandate-hash')).not.toHaveText('Mandate not hashed yet')
  await expect(page.getByRole('button', { name: 'Copy hash' })).toBeEnabled()
  await expect(page.getByText('Allowed · create_invoice')).toBeVisible()
  await expect(page.getByText(/Blocked ·/)).toBeVisible()
  await expect(page.getByText(/Needs approval/)).toBeVisible()
  await expect(page.getByRole('button', { name: 'Approve' }).first()).toBeVisible()
  await expect(page.getByTestId('receipt-hash')).toBeVisible()
  await expect(page.getByRole('link', { name: 'Open in PayPal Sandbox' }).first()).toHaveAttribute('href', /sandbox\.paypal\.com/)
  await expect(page.getByText('PayPal error · MISSING_RECIPIENT_EMAIL')).toBeVisible()
})
