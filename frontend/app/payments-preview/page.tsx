'use client'

import { notFound } from 'next/navigation'
import { PaymentsTab, PAYPAL_DEMO_PAYMENTS, PAYPAL_DEMO_TRANSCRIPT } from '../../components/payments/PaymentsTab'
import { PageContainer } from '../../components/ui/container'
import { PageHeader } from '../../components/ui/page-header'

export default function PaymentsPreviewPage() {
  if (process.env.NODE_ENV === 'production') notFound()
  return (
    <PageContainer>
      <p className="mb-4 rounded border border-amber-300 bg-amber-50 px-3 py-2 text-sm font-semibold text-amber-900" data-testid="mock-data-banner">MOCK DATA</p>
      <PageHeader eyebrow="Contract" title="PayPal Demo MSA" description="Seeded payments preview" />
      <div className="mt-6">
        <PaymentsTab
          roles={['approver', 'contract_owner']}
          actorId="approver-1"
          data={PAYPAL_DEMO_PAYMENTS}
          transcript={PAYPAL_DEMO_TRANSCRIPT}
          onExtract={() => undefined}
          onEdit={() => undefined}
          onApprove={() => undefined}
          onReject={() => undefined}
          onSend={() => undefined}
          onTransition={() => undefined}
          onExecute={() => undefined}
          onVerify={() => undefined}
        />
      </div>
    </PageContainer>
  )
}
