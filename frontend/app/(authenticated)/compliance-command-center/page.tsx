"use client"

import { useState, useEffect } from 'react'
import { Shield } from 'lucide-react'
import { EmptyState } from '../../../components/EmptyState'
import { Skeleton } from '../../../components/ui/skeleton'
import { Card, CardContent } from '../../../components/ui/card'
import { Badge } from '../../../components/ui/badge'
import { Button } from '../../../components/ui/button'
import { PageHeader } from '../../../components/ui/page-header'
import { PageContainer } from '../../../components/ui/container'
import { apiFetch } from '../../../lib/api'

interface AffectedContract {
  contract_id: string
  contract_name: string
  industry?: string
  jurisdiction?: string
  data_processing?: boolean
  cross_border?: boolean
  compliant?: boolean
  impact_level: 'low' | 'medium' | 'high' | 'critical'
  impact_reason: string
  affected_clause?: string
  missing_requirement?: string
  recommended_action: string
}

interface MonitoringEvent {
  id: string
  regulatory_change_id: string
  regulatory_change_title: string
  jurisdiction: string
  effective_date: string
  affected_contracts: AffectedContract[]
  total_affected: number
  status: string
  created_at: string
  created_by: string
  approved_at?: string
  approved_by?: string
}

interface ComplianceCommandCenter {
  total_contracts: number
  total_affected: number
  high_impact: number
  medium_impact: number
  low_impact: number
  events: MonitoringEvent[]
}

export default function ComplianceCommandCenter() {
  const [commandCenter, setCommandCenter] = useState<ComplianceCommandCenter | null>(null)
  const [selectedEvent, setSelectedEvent] = useState<MonitoringEvent | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchCommandCenter()
  }, [])

  const fetchCommandCenter = async () => {
    try {
      const response = await apiFetch('/api/compliance/command-center')
      if (!response.ok) throw new Error('Failed to fetch command center')
      const data = await response.json()
      setCommandCenter(data)
    } catch (error) {
      console.error('Error fetching command center:', error)
    } finally {
      setLoading(false)
    }
  }

  const getImpactColor = (level: string) => {
    switch (level) {
      case 'critical':
        return 'bg-red-500'
      case 'high':
        return 'bg-orange-500'
      case 'medium':
        return 'bg-yellow-500'
      case 'low':
        return 'bg-green-500'
      default:
        return 'bg-gray-500'
    }
  }

  const getImpactText = (level: string) => {
    switch (level) {
      case 'critical':
        return 'Critical'
      case 'high':
        return 'High'
      case 'medium':
        return 'Medium'
      case 'low':
        return 'Low'
      default:
        return level
    }
  }

  const getStatusText = (status: string) => {
    switch (status) {
      case 'active':
        return 'Active'
      case 'pending':
        return 'Pending'
      case 'resolved':
        return 'Resolved'
      case 'rejected':
        return 'Rejected'
      default:
        return status
    }
  }

  // Phase 4: status text now renders through the shared Badge component
  // instead of a page-specific colored span. active/pending/resolved/
  // rejected map onto Badge's existing variant set (no new colors
  // introduced): active reads as the normal "still being tracked" state,
  // pending as needing action, resolved as neutral/done, rejected as a
  // problem state.
  const statusBadgeVariant = (status: string): 'verified' | 'pending' | 'secondary' | 'tampered' => {
    switch (status) {
      case 'active':
        return 'verified'
      case 'pending':
        return 'pending'
      case 'resolved':
        return 'secondary'
      case 'rejected':
        return 'tampered'
      default:
        return 'secondary'
    }
  }

  return (
    <PageContainer>
      <PageHeader
        eyebrow="Compliance"
        title="Compliance Command Center"
        description="Monitor regulatory changes and track contract compliance status."
      />

      <div className="mt-6">
        {loading ? (
          <div className="space-y-4">
            <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-5">
              {Array.from({ length: 5 }).map((_, index) => (
                <div key={index} className="rounded-[var(--radius-lg,0.75rem)] border border-gray-200 p-6 dark:border-gray-700">
                  <Skeleton className="h-3.5 w-24" />
                  <Skeleton className="mt-3 h-8 w-16" />
                </div>
              ))}
            </div>
            <Skeleton className="h-64 w-full" />
          </div>
        ) : commandCenter ? (
          <>
            {/* Overview Cards */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-6 mb-8">
              <Card>
                <CardContent>
                  <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Total Contracts</p>
                  <p className="text-3xl font-bold text-gray-900 dark:text-gray-100 mt-2">
                    {commandCenter.total_contracts}
                  </p>
                </CardContent>
              </Card>

              <Card>
                <CardContent>
                  <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Affected Contracts</p>
                  <p className="text-3xl font-bold text-red-600 dark:text-red-400 mt-2">
                    {commandCenter.total_affected}
                  </p>
                </CardContent>
              </Card>

              <Card>
                <CardContent>
                  <p className="text-sm font-medium text-gray-500 dark:text-gray-400">High Impact</p>
                  <p className="text-3xl font-bold text-orange-600 dark:text-orange-400 mt-2">
                    {commandCenter.high_impact}
                  </p>
                </CardContent>
              </Card>

              <Card>
                <CardContent>
                  <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Medium Impact</p>
                  <p className="text-3xl font-bold text-amber-600 dark:text-amber-400 mt-2">
                    {commandCenter.medium_impact}
                  </p>
                </CardContent>
              </Card>

              <Card>
                <CardContent>
                  <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Low Impact</p>
                  <p className="text-3xl font-bold text-green-600 dark:text-green-400 mt-2">
                    {commandCenter.low_impact}
                  </p>
                </CardContent>
              </Card>
            </div>

            {/* Events Table */}
            <Card className="overflow-hidden">
              <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700">
                <h2 className="text-lg font-medium text-gray-900 dark:text-gray-100">Monitoring Events</h2>
              </div>

              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                  <thead className="bg-gray-50 dark:bg-gray-700/40">
                    <tr>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                        Title
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                        Jurisdiction
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                        Effective Date
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                        Status
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                        Affected
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                        Actions
                      </th>
                    </tr>
                  </thead>
                  <tbody className="bg-white divide-y divide-gray-200 dark:bg-gray-800 dark:divide-gray-700">
                    {commandCenter.events.map((event) => (
                      <tr
                        key={event.id}
                        className="hover:bg-gray-50 dark:hover:bg-gray-700/40 cursor-pointer"
                        onClick={() => setSelectedEvent(event)}
                      >
                        <td className="px-6 py-4 whitespace-nowrap">
                          <div className="text-sm font-medium text-gray-900 dark:text-gray-100">
                            {event.regulatory_change_title}
                          </div>
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap">
                          <div className="text-sm text-gray-900 dark:text-gray-200">{event.jurisdiction}</div>
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap">
                          <div className="text-sm text-gray-900 dark:text-gray-200">
                            {new Date(event.effective_date).toLocaleDateString()}
                          </div>
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap">
                          <Badge variant={statusBadgeVariant(event.status)}>{getStatusText(event.status)}</Badge>
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap">
                          <div className="text-sm text-gray-900 dark:text-gray-200">{event.total_affected}</div>
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                          <button className="text-[var(--brand-primary,#2563eb)] hover:underline">
                            View Details
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {commandCenter.events.length === 0 && (
                <div className="px-6 py-8">
                  <EmptyState
                    compact
                    title="No monitoring events yet"
                    description="Regulatory tracking runs as contracts are analyzed. Simulate a regulatory change to populate this list."
                    icon={<Shield className="h-4 w-4" />}
                  />
                </div>
              )}
            </Card>
          </>
        ) : (
          <EmptyState
            title="No compliance data yet"
            description="This page shows regulatory-change impact across your contracts. Simulate a regulatory change, or return here after contracts have been analyzed, to populate the command center."
            icon={<Shield className="h-6 w-6" />}
          />
        )}
      </div>

      {/* Event Details Modal */}
      {selectedEvent && (
        <EventDetailsModal
          event={selectedEvent}
          onClose={() => setSelectedEvent(null)}
          onRefresh={fetchCommandCenter}
        />
      )}
    </PageContainer>
  )
}

function EventDetailsModal({
  event,
  onClose,
  onRefresh,
}: {
  event: MonitoringEvent
  onClose: () => void
  onRefresh: () => void
}) {
  const [showApproveModal, setShowApproveModal] = useState(false)

  const getStatusText = (status: string) => {
    switch (status) {
      case 'active':
        return 'Active'
      case 'pending':
        return 'Pending'
      case 'resolved':
        return 'Resolved'
      case 'rejected':
        return 'Rejected'
      default:
        return status
    }
  }

  // Phase 4: same status->variant mapping as the parent component's
  // statusBadgeVariant -- duplicated here since this is a separate
  // component and cannot close over the parent's local const.
  const statusBadgeVariant = (status: string): 'verified' | 'pending' | 'secondary' | 'tampered' => {
    switch (status) {
      case 'active':
        return 'verified'
      case 'pending':
        return 'pending'
      case 'resolved':
        return 'secondary'
      case 'rejected':
        return 'tampered'
      default:
        return 'secondary'
    }
  }

  // Impact levels map directly onto Badge's existing critical/high/medium/low
  // variants -- no page-specific color needed.
  const impactBadgeVariant = (level: string): 'critical' | 'high' | 'medium' | 'low' | 'secondary' => {
    switch (level) {
      case 'critical':
        return 'critical'
      case 'high':
        return 'high'
      case 'medium':
        return 'medium'
      case 'low':
        return 'low'
      default:
        return 'secondary'
    }
  }

  const getImpactText = (level: string) => {
    switch (level) {
      case 'critical':
        return 'Critical'
      case 'high':
        return 'High'
      case 'medium':
        return 'Medium'
      case 'low':
        return 'Low'
      default:
        return level
    }
  }

  const handleApprove = async (approved: boolean) => {
    try {
      const response = await apiFetch(`/api/compliance/events/${event.id}/approve?approved=${approved}`, {
        method: 'POST',
      })
      if (!response.ok) throw new Error('Failed to approve event')
      onRefresh()
      onClose()
    } catch (error) {
      console.error('Error approving event:', error)
    }
  }

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-[var(--radius-lg,0.75rem)] shadow-[var(--shadow-lg)] max-w-4xl w-full mx-4 max-h-[90vh] overflow-hidden dark:bg-gray-800">
        {/* Header */}
        <div className="bg-gray-50 px-6 py-4 border-b border-gray-200 flex justify-between items-center dark:bg-gray-700/40 dark:border-gray-700">
          <div>
            <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100">
              {event.regulatory_change_title}
            </h2>
            <p className="text-sm text-gray-600 dark:text-gray-400">
              {event.jurisdiction} • Effective: {new Date(event.effective_date).toLocaleDateString()}
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
          >
            <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Content */}
        <div className="px-6 py-4 overflow-y-auto max-h-[60vh]">
          {/* Status */}
          <div className="mb-6">
            <Badge variant={statusBadgeVariant(event.status)}>{getStatusText(event.status)}</Badge>
            {event.approved_by && (
              <p className="text-sm text-gray-600 mt-2 dark:text-gray-400">
                Approved by {event.approved_by} on {new Date(event.approved_at!).toLocaleDateString()}
              </p>
            )}
          </div>

          {/* Affected Contracts */}
          <h3 className="text-lg font-medium text-gray-900 mb-4 dark:text-gray-100">
            Affected Contracts ({event.total_affected})
          </h3>

          <div className="space-y-4">
            {event.affected_contracts.map((contract, index) => (
              <div
                key={index}
                className="border border-gray-200 rounded-[var(--radius-md,0.5rem)] p-4 hover:shadow-[var(--shadow-sm)] transition-shadow dark:border-gray-700"
              >
                <div className="flex justify-between items-start mb-2">
                  <div>
                    <h4 className="text-lg font-medium text-gray-900 dark:text-gray-100">
                      {contract.contract_name}
                    </h4>
                    <p className="text-sm text-gray-600 dark:text-gray-400">ID: {contract.contract_id}</p>
                  </div>
                  <Badge variant={impactBadgeVariant(contract.impact_level)}>{getImpactText(contract.impact_level)}</Badge>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
                  <div>
                    <p className="text-sm text-gray-500 dark:text-gray-400">Impact Reason</p>
                    <p className="text-sm text-gray-900 dark:text-gray-200">{contract.impact_reason}</p>
                  </div>

                  {contract.affected_clause && (
                    <div>
                      <p className="text-sm text-gray-500 dark:text-gray-400">Affected Clause</p>
                      <p className="text-sm text-gray-900 dark:text-gray-200">{contract.affected_clause}</p>
                    </div>
                  )}

                  {contract.missing_requirement && (
                    <div>
                      <p className="text-sm text-gray-500 dark:text-gray-400">Missing Requirement</p>
                      <p className="text-sm text-gray-900 dark:text-gray-200">{contract.missing_requirement}</p>
                    </div>
                  )}

                  <div className="md:col-span-2">
                    <p className="text-sm text-gray-500 dark:text-gray-400">Recommended Action</p>
                    <p className="text-sm text-gray-900 dark:text-gray-200">{contract.recommended_action}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Footer */}
        <div className="bg-gray-50 px-6 py-4 border-t border-gray-200 flex justify-end gap-3 dark:bg-gray-700/40 dark:border-gray-700">
          {event.status === 'pending' && (
            <>
              <Button type="button" variant="destructive" onClick={() => setShowApproveModal(true)}>
                Reject
              </Button>
              <Button type="button" onClick={() => setShowApproveModal(true)}>
                Approve
              </Button>
            </>
          )}
          <Button type="button" variant="secondary" onClick={onClose}>
            Close
          </Button>
        </div>
      </div>
    </div>
  )
}
