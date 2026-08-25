"use client"

import { useState, useEffect } from 'react'

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
      const response = await fetch('/api/compliance/command-center')
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

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'active':
        return 'text-green-600'
      case 'pending':
        return 'text-yellow-600'
      case 'resolved':
        return 'text-blue-600'
      case 'rejected':
        return 'text-red-600'
      default:
        return 'text-gray-600'
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

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white shadow">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
          <h1 className="text-3xl font-bold text-gray-900">Compliance Command Center</h1>
          <p className="mt-2 text-gray-600">
            Monitor regulatory changes and track contract compliance status
          </p>
        </div>
      </div>

      {/* Metrics */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {loading ? (
          <div className="text-center py-12">
            <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
            <p className="mt-4 text-gray-600">Loading compliance data...</p>
          </div>
        ) : commandCenter ? (
          <>
            {/* Overview Cards */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-6 mb-8">
              <div className="bg-white rounded-lg shadow p-6">
                <p className="text-sm font-medium text-gray-500">Total Contracts</p>
                <p className="text-3xl font-bold text-gray-900 mt-2">
                  {commandCenter.total_contracts}
                </p>
              </div>

              <div className="bg-white rounded-lg shadow p-6">
                <p className="text-sm font-medium text-gray-500">Affected Contracts</p>
                <p className="text-3xl font-bold text-red-600 mt-2">
                  {commandCenter.total_affected}
                </p>
              </div>

              <div className="bg-white rounded-lg shadow p-6">
                <p className="text-sm font-medium text-gray-500">High Impact</p>
                <p className="text-3xl font-bold text-orange-600 mt-2">
                  {commandCenter.high_impact}
                </p>
              </div>

              <div className="bg-white rounded-lg shadow p-6">
                <p className="text-sm font-medium text-gray-500">Medium Impact</p>
                <p className="text-3xl font-bold text-yellow-600 mt-2">
                  {commandCenter.medium_impact}
                </p>
              </div>

              <div className="bg-white rounded-lg shadow p-6">
                <p className="text-sm font-medium text-gray-500">Low Impact</p>
                <p className="text-3xl font-bold text-green-600 mt-2">
                  {commandCenter.low_impact}
                </p>
              </div>
            </div>

            {/* Events Table */}
            <div className="bg-white rounded-lg shadow overflow-hidden">
              <div className="px-6 py-4 border-b border-gray-200">
                <h2 className="text-lg font-medium text-gray-900">Monitoring Events</h2>
              </div>

              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Title
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Jurisdiction
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Effective Date
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Status
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Affected
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Actions
                      </th>
                    </tr>
                  </thead>
                  <tbody className="bg-white divide-y divide-gray-200">
                    {commandCenter.events.map((event) => (
                      <tr
                        key={event.id}
                        className="hover:bg-gray-50 cursor-pointer"
                        onClick={() => setSelectedEvent(event)}
                      >
                        <td className="px-6 py-4 whitespace-nowrap">
                          <div className="text-sm font-medium text-gray-900">
                            {event.regulatory_change_title}
                          </div>
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap">
                          <div className="text-sm text-gray-900">{event.jurisdiction}</div>
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap">
                          <div className="text-sm text-gray-900">
                            {new Date(event.effective_date).toLocaleDateString()}
                          </div>
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap">
                          <span className={`px-2 inline-flex text-xs leading-5 font-semibold rounded-full ${getStatusColor(
                            event.status
                          )}`}>
                            {getStatusText(event.status)}
                          </span>
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap">
                          <div className="text-sm text-gray-900">{event.total_affected}</div>
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                          <button className="text-blue-600 hover:text-blue-900">
                            View Details
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {commandCenter.events.length === 0 && (
                <div className="px-6 py-12 text-center text-gray-500">
                  No monitoring events yet. Simulate a regulatory change to get started.
                </div>
              )}
            </div>
          </>
        ) : (
          <div className="text-center py-12 text-gray-500">
            No data available
          </div>
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
    </div>
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

  const handleApprove = async (approved: boolean) => {
    try {
      const response = await fetch(`/api/compliance/events/${event.id}/approve?approved=${approved}`, {
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
      <div className="bg-white rounded-lg shadow-xl max-w-4xl w-full mx-4 max-h-[90vh] overflow-hidden">
        {/* Header */}
        <div className="bg-gray-50 px-6 py-4 border-b border-gray-200 flex justify-between items-center">
          <div>
            <h2 className="text-xl font-bold text-gray-900">
              {event.regulatory_change_title}
            </h2>
            <p className="text-sm text-gray-600">
              {event.jurisdiction} • Effective: {new Date(event.effective_date).toLocaleDateString()}
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-gray-700"
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
            <span className={`px-3 py-1 inline-flex text-sm font-semibold rounded-full ${getStatusColor(
              event.status
            )}`}>
              {getStatusText(event.status)}
            </span>
            {event.approved_by && (
              <p className="text-sm text-gray-600 mt-2">
                Approved by {event.approved_by} on {new Date(event.approved_at!).toLocaleDateString()}
              </p>
            )}
          </div>

          {/* Affected Contracts */}
          <h3 className="text-lg font-medium text-gray-900 mb-4">
            Affected Contracts ({event.total_affected})
          </h3>

          <div className="space-y-4">
            {event.affected_contracts.map((contract, index) => (
              <div
                key={index}
                className="border border-gray-200 rounded-lg p-4 hover:shadow-md transition-shadow"
              >
                <div className="flex justify-between items-start mb-2">
                  <div>
                    <h4 className="text-lg font-medium text-gray-900">
                      {contract.contract_name}
                    </h4>
                    <p className="text-sm text-gray-600">ID: {contract.contract_id}</p>
                  </div>
                  <span className={`px-3 py-1 text-sm font-semibold rounded-full ${getImpactColor(
                    contract.impact_level
                  )}`}>
                    {getImpactText(contract.impact_level)}
                  </span>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
                  <div>
                    <p className="text-sm text-gray-500">Impact Reason</p>
                    <p className="text-sm text-gray-900">{contract.impact_reason}</p>
                  </div>

                  {contract.affected_clause && (
                    <div>
                      <p className="text-sm text-gray-500">Affected Clause</p>
                      <p className="text-sm text-gray-900">{contract.affected_clause}</p>
                    </div>
                  )}

                  {contract.missing_requirement && (
                    <div>
                      <p className="text-sm text-gray-500">Missing Requirement</p>
                      <p className="text-sm text-gray-900">{contract.missing_requirement}</p>
                    </div>
                  )}

                  <div className="md:col-span-2">
                    <p className="text-sm text-gray-500">Recommended Action</p>
                    <p className="text-sm text-gray-900">{contract.recommended_action}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Footer */}
        <div className="bg-gray-50 px-6 py-4 border-t border-gray-200 flex justify-end gap-3">
          {event.status === 'pending' && (
            <>
              <button
                onClick={() => setShowApproveModal(true)}
                className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700"
              >
                Reject
              </button>
              <button
                onClick={() => setShowApproveModal(true)}
                className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700"
              >
                Approve
              </button>
            </>
          )}
          <button
            onClick={onClose}
            className="px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  )
}

function getStatusColor(status: string) {
  switch (status) {
    case 'active':
      return 'text-green-600'
    case 'pending':
      return 'text-yellow-600'
    case 'resolved':
      return 'text-blue-600'
    case 'rejected':
      return 'text-red-600'
    default:
      return 'text-gray-600'
  }
}
