'use client';

export default function ContractVersions() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-gray-900">Contract Versions</h1>
        <p className="text-gray-600 mt-2">View and compare contract versions</p>
      </div>

      <div className="bg-white rounded-lg shadow p-6">
        <p className="text-gray-500">Version history will be displayed here</p>
      </div>
    </div>
  );
}
