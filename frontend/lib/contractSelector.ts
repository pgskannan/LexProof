export type SelectableContract = {
  contract_id: string;
  name?: string | null;
};

export function filterContracts(contracts: SelectableContract[], search: string): SelectableContract[] {
  const query = search.trim().toLowerCase();
  if (!query) return contracts;
  return contracts.filter((contract) =>
    [contract.name, contract.contract_id].some((value) => String(value ?? '').toLowerCase().includes(query)),
  );
}

export function contractSelectionUrl(currentQuery: string, contractId: string): string {
  const params = new URLSearchParams(currentQuery);
  params.set('contract_id', contractId);
  params.delete('version_id');
  params.delete('finding_id');
  return `/dashboard/ai-analysis/findings?${params.toString()}`;
}
