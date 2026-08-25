'use client';

import { useState } from 'react';
import Link from 'next/link';

export default function Dashboard() {
  const [activeSection, setActiveSection] = useState('contracts');

  const navigation = [
    {
      title: 'Contracts',
      items: [
        { name: 'All Contracts', href: '/dashboard/contracts' },
        { name: 'Reviews', href: '/dashboard/contracts/reviews' },
        { name: 'Versions', href: '/dashboard/contracts/versions' },
      ],
    },
    {
      title: 'AI Analysis',
      items: [
        { name: 'Risk', href: '/dashboard/ai-analysis/risk' },
        { name: 'Clauses', href: '/dashboard/ai-analysis/clauses' },
        { name: 'Findings', href: '/dashboard/ai-analysis/findings' },
      ],
    },
    {
      title: 'Compliance',
      items: [
        { name: 'Policies', href: '/dashboard/compliance/policies' },
        { name: 'Violations', href: '/dashboard/compliance/violations' },
        { name: 'Monitoring', href: '/dashboard/compliance/monitoring' },
      ],
    },
    {
      title: 'Legal Passport',
      items: [{ name: 'Legal Passport', href: '/dashboard/legal-passport' }],
    },
    {
      title: 'Blockchain Proof',
      items: [{ name: 'Blockchain Proof', href: '/dashboard/blockchain-proof' }],
    },
    {
      title: 'Verification',
      items: [{ name: 'Verification', href: '/dashboard/verification' }],
    },
    {
      title: 'Reports',
      items: [{ name: 'Reports', href: '/dashboard/reports' }],
    },
    {
      title: 'Administration',
      items: [{ name: 'Administration', href: '/dashboard/administration' }],
    },
  ];

  return (
    <div className="flex min-h-screen bg-gray-50">
      {/* Sidebar Navigation */}
      <aside className="w-64 bg-gray-900 text-white flex-shrink-0">
        <div className="p-6">
          <h1 className="text-2xl font-bold text-white mb-8">LexProof</h1>
          <p className="text-gray-400 text-sm mb-6">Verifiable Legal Intelligence</p>
        </div>
        <nav className="mt-4">
          {navigation.map((section) => (
            <div key={section.title} className="mb-6">
              <button
                onClick={() => setActiveSection(section.title)}
                className={`w-full flex items-center justify-between px-6 py-3 text-left ${
                  activeSection === section.title ? 'bg-gray-800 text-white' : 'text-gray-300 hover:bg-gray-800'
                }`}
              >
                <span className="font-medium">{section.title}</span>
                <svg
                  className={`w-4 h-4 transition-transform ${
                    activeSection === section.title ? 'rotate-180' : ''
                  }`}
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </button>
              {activeSection === section.title && (
                <div className="pl-6 space-y-1">
                  {section.items.map((item) => (
                    <Link
                      key={item.name}
                      href={item.href}
                      className="block px-4 py-2 text-sm text-gray-400 hover:text-white hover:bg-gray-800 rounded-md transition-colors"
                    >
                      {item.name}
                    </Link>
                  ))}
                </div>
              )}
            </div>
          ))}
        </nav>
      </aside>

      {/* Main Content */}
      <main className="flex-1 p-8">
        <div className="max-w-7xl mx-auto">
          <div className="mb-8">
            <h2 className="text-3xl font-bold text-gray-900">Dashboard</h2>
            <p className="text-gray-600 mt-2">
              Seeded demo snapshot. Select a section from the navigation menu to explore the workflow.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {/* Quick Stats Cards */}
            <div className="bg-white rounded-lg shadow p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-gray-600">Contract records</p>
                  <p className="text-3xl font-bold text-gray-900 mt-2">7</p>
                </div>
                <div className="bg-blue-100 p-3 rounded-full">
                  <svg className="w-6 h-6 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                  </svg>
                </div>
              </div>
            </div>

            <div className="bg-white rounded-lg shadow p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-gray-600">Primary versions</p>
                  <p className="text-3xl font-bold text-gray-900 mt-2">3</p>
                </div>
                <div className="bg-yellow-100 p-3 rounded-full">
                  <svg className="w-6 h-6 text-yellow-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                </div>
              </div>
            </div>

            <div className="bg-white rounded-lg shadow p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-gray-600">Seeded violations</p>
                  <p className="text-3xl font-bold text-gray-900 mt-2">4</p>
                </div>
                <div className="bg-red-100 p-3 rounded-full">
                  <svg className="w-6 h-6 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                  </svg>
                </div>
              </div>
            </div>
          </div>

          {/* Recent Activity Section */}
          <div className="mt-8 bg-white rounded-lg shadow">
            <div className="p-6 border-b border-gray-200">
              <h3 className="text-xl font-semibold text-gray-900">Recent Activity</h3>
            </div>
            <div className="p-6">
              <div className="space-y-4">
                <div className="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
                  <div>
                    <p className="font-medium text-gray-900">CONTRACT-000001 v3 analyzed</p>
                    <p className="text-sm text-gray-600">Seeded risk score: 35/100</p>
                  </div>
                  <span className="text-sm text-gray-500">2 hours ago</span>
                </div>
                <div className="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
                  <div>
                    <p className="font-medium text-gray-900">CPRA scenario loaded</p>
                    <p className="text-sm text-gray-600">4 seeded policy violations</p>
                  </div>
                  <span className="text-sm text-gray-500">5 hours ago</span>
                </div>
                <div className="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
                  <div>
                    <p className="font-medium text-gray-900">Three passport versions available</p>
                    <p className="text-sm text-gray-600">Blockchain anchoring requires configured Sepolia credentials</p>
                  </div>
                  <span className="text-sm text-gray-500">1 day ago</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
