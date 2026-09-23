'use client';

import React from 'react';
import { useEffect, useMemo, useState } from 'react';
import { ChevronDown, Search } from 'lucide-react';
import { apiFetch } from '../../../lib/api';
import { useOrg } from '../../OrgProvider';
import { filterContracts, type SelectableContract } from '../../../lib/contractSelector';

export interface Contract extends SelectableContract {
  contract_id: string;
  status?: string;
  risk_level?: string;
  version?: string;
}

export interface ContractSelectorProps {
  selectedContractId: string;
  onContractSelect: (contractId: string) => void;
  disabled?: boolean;
}

export function ContractSelector({ selectedContractId, onContractSelect, disabled = false }: ContractSelectorProps) {
  const { currentOrg, loading: orgLoading } = useOrg();
  const [contracts, setContracts] = useState<Contract[]>([]);
  const [search, setSearch] = useState('');
  const [isOpen, setIsOpen] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Wait for OrgProvider so /api/contracts is sent with X-Org-Id. A first-paint
    // fetch with no org streams every contracts/versions/passports/proposals
    // document, which left this picker showing "No contracts match" through the
    // golden-path E2E's 15s wait for demo-golden-path-master-services-agreement.
    if (orgLoading) return;
    let cancelled = false;
    async function loadContracts() {
      if (!currentOrg?.org_id) {
        setContracts([]);
        setLoading(false);
        return;
      }
      setLoading(true);
      try {
        const response = await apiFetch('/api/contracts');
        if (!cancelled && response.ok) {
          setContracts(await response.json());
        }
      } catch (error) {
        console.error('Failed to load contracts:', error);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void loadContracts();
    return () => {
      cancelled = true;
    };
  }, [orgLoading, currentOrg?.org_id]);

  const filteredContracts = useMemo(() => {
    return filterContracts(contracts, search);
  }, [contracts, search]);

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        disabled={disabled}
        className="flex w-full items-center gap-2 rounded-[var(--radius-md,0.5rem)] border border-gray-300 bg-white px-3 py-2.5 text-left text-sm text-gray-700 shadow-sm transition hover:border-blue-500 hover:shadow dark:border-gray-600 dark:bg-gray-900 dark:text-gray-200 disabled:opacity-50"
        aria-label="Select a contract"
        aria-haspopup="listbox"
        aria-expanded={isOpen}
      >
        <Search className="h-4 w-4 text-gray-400" />
        {selectedContractId ? (
          <span className="flex-1 truncate">{contracts.find((c) => c.contract_id === selectedContractId)?.name || selectedContractId}</span>
        ) : (
          <span className="flex-1 truncate text-gray-400">Select a contract to view findings and redlines</span>
        )}
        <ChevronDown className={`h-4 w-4 shrink-0 text-gray-500 transition-transform ${isOpen ? 'rotate-180' : ''}`} aria-hidden="true" />
      </button>

      {isOpen && (
        <div className="absolute z-50 mt-1 max-h-80 w-full overflow-hidden rounded-lg border border-gray-200 bg-white shadow-lg dark:border-gray-700 dark:bg-gray-900">
          <div className="border-b border-gray-100 px-3 py-2">
            <label className="flex items-center gap-2 rounded border border-gray-300 px-3 dark:border-gray-600">
              <Search className="h-4 w-4 text-gray-400" />
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search by name or contract ID"
                className="w-full bg-transparent py-1 text-sm outline-none"
                autoFocus
              />
            </label>
          </div>
          <div className="max-h-60 overflow-y-auto py-1">
            {loading ? (
              <div className="px-3 py-4 text-center text-sm text-gray-500">Loading contracts...</div>
            ) : filteredContracts.length === 0 ? (
              <div className="px-3 py-4 text-center text-sm text-gray-500">No contracts match</div>
            ) : (
              filteredContracts.map((contract) => (
                <button
                  key={contract.contract_id}
                  type="button"
                  onClick={() => {
                    onContractSelect(contract.contract_id);
                    setIsOpen(false);
                  }}
                  className="w-full px-3 py-2 text-left text-sm hover:bg-gray-50 dark:hover:bg-gray-800"
                >
                  <p className="truncate font-medium">{contract.name}</p>
                  <p className="mt-0.5 truncate font-mono text-xs text-gray-400">{contract.contract_id}</p>
                </button>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
