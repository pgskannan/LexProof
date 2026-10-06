'use client'

import { PaymentsTab, PAYPAL_DEMO_PAYMENTS, PAYPAL_DEMO_TRANSCRIPT } from '../../components/payments/PaymentsTab'
import { PageContainer } from '../../components/ui/container'
import { PageHeader } from '../../components/ui/page-header'

export default function PaymentsPreviewPage() {
  return (
    <PageContainer>
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
