import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { PaymentsTab, type PaymentsData } from './PaymentsTab'

describe('PaymentsTab PayPal transport status', () => {
  it('shows the REST fallback suffix on an allowed tool call', () => {
    const data: PaymentsData = {
      obligations: [],
      mandate_hash: '',
      invoices: [],
      receipts: [],
      checkpoints: [],
      actions: [],
    }
    const html = renderToStaticMarkup(
      <PaymentsTab
        roles={[]}
        data={data}
        transcript={[{ tool: 'create_invoice', decision: 'allow', transport: 'rest_fallback' }]}
      />,
    )
    expect(html).toContain('Allowed · create_invoice')
    expect(html).toContain('via REST fallback')
  })
})