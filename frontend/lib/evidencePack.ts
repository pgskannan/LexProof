// One-click compliance evidence pack: bundles everything an auditor or
// counterparty would otherwise have to collect by hand (the cryptographic
// proof bundle, the offline verifier, and a human-readable summary of the
// contract's risk/compliance findings) into a single downloadable ZIP.
import { apiFetch } from './api';
import type { Finding } from './findings';

export type EvidencePackAnchor = {
  transaction_hash?: string;
  block_number?: number;
  blockchain_network?: string;
};

export type EvidencePackEvidenceItem = {
  evidence_id: string;
  title: string;
};

export type EvidencePackParams = {
  passportId: string;
  contractId: string;
  contractVersion: number;
  contractName: string;
  passportStatus?: string | null;
  riskScore?: number | null;
  complianceScore?: number | null;
  evidence: EvidencePackEvidenceItem[];
};

export function slugify(value: string): string {
  return (value || 'contract')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/(^-|-$)/g, '') || 'contract';
}

export function dateStamp(): string {
  return new Date().toISOString().slice(0, 10);
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

async function fetchProofPackage(passportId: string): Promise<Record<string, unknown>> {
  const response = await apiFetch(`/api/passports/${encodeURIComponent(passportId)}/proof-package`);
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail || 'Unable to fetch the verification bundle');
  }
  return response.json();
}

async function fetchFindings(contractId: string): Promise<Finding[]> {
  const response = await apiFetch(`/api/findings?contract_id=${encodeURIComponent(contractId)}`);
  if (!response.ok) return [];
  return (await response.json()) as Finding[];
}

async function fetchOfflineVerifierHtml(): Promise<string | null> {
  try {
    const response = await fetch('/verify-offline.html');
    if (!response.ok) return null;
    return await response.text();
  } catch {
    return null;
  }
}

async function fetchAnchors(
  evidence: EvidencePackEvidenceItem[],
): Promise<Record<string, EvidencePackAnchor>> {
  if (evidence.length === 0) return {};
  const results = await Promise.all(
    evidence.map(async (item) => {
      try {
        const response = await apiFetch(`/api/evidence/${encodeURIComponent(item.evidence_id)}/anchor`);
        if (!response.ok) return null;
        return (await response.json()) as EvidencePackAnchor & { evidence_id?: string };
      } catch {
        return null;
      }
    }),
  );
  const anchors: Record<string, EvidencePackAnchor> = {};
  results.forEach((record, index) => {
    if (record?.transaction_hash) {
      anchors[evidence[index].evidence_id] = record;
    }
  });
  return anchors;
}

const severityOrder = ['critical', 'high', 'medium', 'low'];

async function buildSummaryPdf(
  params: EvidencePackParams,
  proofPackage: Record<string, unknown>,
  findings: Finding[],
  anchors: Record<string, EvidencePackAnchor>,
): Promise<Blob> {
  const { jsPDF } = await import('jspdf');
  const doc = new jsPDF();
  const marginX = 14;
  const pageBottom = 282;
  let y = 18;

  function ensureRoom(rowHeight: number) {
    if (y + rowHeight > pageBottom) {
      doc.addPage();
      y = 18;
    }
  }

  function heading(text: string) {
    ensureRoom(12);
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(13);
    doc.setTextColor(20);
    doc.text(text, marginX, y);
    y += 8;
    doc.setDrawColor(210);
    doc.line(marginX, y - 5, 196, y - 5);
  }

  function keyValueRows(rows: [string, string][]) {
    doc.setFontSize(10);
    for (const [label, value] of rows) {
      const wrapped = doc.splitTextToSize(value || 'Not available', 118);
      const rowHeight = 5.2 * Math.max(1, wrapped.length) + 1.5;
      ensureRoom(rowHeight);
      doc.setFont('helvetica', 'bold');
      doc.setTextColor(80);
      doc.text(label, marginX, y);
      doc.setFont('helvetica', 'normal');
      doc.setTextColor(20);
      doc.text(wrapped, marginX + 62, y);
      y += rowHeight;
    }
    y += 4;
  }

  doc.setFontSize(18);
  doc.setFont('helvetica', 'bold');
  doc.setTextColor(20);
  doc.text('LexProof — Compliance Evidence Pack', marginX, y);
  y += 7;
  doc.setFontSize(10);
  doc.setFont('helvetica', 'normal');
  doc.setTextColor(120);
  doc.text(`Generated ${new Date().toLocaleString()}`, marginX, y);
  y += 10;

  heading('Contract');
  keyValueRows([
    ['Contract', params.contractName],
    ['Contract ID', params.contractId],
    ['Contract version', String(params.contractVersion)],
    ['Passport ID', params.passportId],
    ['Passport status', params.passportStatus || 'Not available'],
    ['Risk score', params.riskScore != null ? `${params.riskScore}/100` : 'Not available'],
    ['Compliance score', params.complianceScore != null ? `${params.complianceScore}/100` : 'Not available'],
  ]);

  const hashes = (proofPackage.hashes as Record<string, string | null>) || {};
  heading('Cryptographic fingerprints (SHA-256)');
  keyValueRows([
    ['Document hash', hashes.document_hash || 'Not available'],
    ['Policy hash', hashes.policy_hash || 'Not available'],
    ['Analysis hash', hashes.analysis_hash || 'Not available'],
    ['Evidence hash', hashes.evidence_hash || 'Not available'],
    ['Passport hash', hashes.passport_hash || 'Not available'],
  ]);

  heading('Evidence & blockchain anchoring');
  if (params.evidence.length === 0) {
    doc.setFontSize(10);
    doc.setFont('helvetica', 'normal');
    doc.setTextColor(90);
    ensureRoom(6);
    doc.text('No evidence items recorded for this passport.', marginX, y);
    y += 8;
  } else {
    for (const item of params.evidence) {
      const anchor = anchors[item.evidence_id];
      const status = anchor?.transaction_hash
        ? `Anchored on ${anchor.blockchain_network || 'chain'} — tx ${anchor.transaction_hash}${anchor.block_number != null ? ` (block ${anchor.block_number})` : ''}`
        : 'Not yet anchored on-chain';
      const wrapped = doc.splitTextToSize(status, 176);
      const rowHeight = 5.2 * (1 + wrapped.length) + 2;
      ensureRoom(rowHeight);
      doc.setFontSize(10);
      doc.setFont('helvetica', 'bold');
      doc.setTextColor(20);
      doc.text(item.title || item.evidence_id, marginX, y);
      y += 5.2;
      doc.setFont('helvetica', 'normal');
      doc.setTextColor(anchor?.transaction_hash ? 30 : 150);
      doc.text(wrapped, marginX, y);
      y += 5.2 * wrapped.length + 2;
    }
  }

  heading('AI risk & compliance findings');
  const counts = severityOrder.reduce<Record<string, number>>((acc, severity) => {
    acc[severity] = findings.filter((f) => f.severity?.toLowerCase() === severity).length;
    return acc;
  }, {});
  doc.setFontSize(10);
  doc.setFont('helvetica', 'normal');
  doc.setTextColor(20);
  ensureRoom(6);
  doc.text(
    `${findings.length} finding(s) — Critical: ${counts.critical}, High: ${counts.high}, Medium: ${counts.medium}, Low: ${counts.low}`,
    marginX,
    y,
  );
  y += 8;

  if (findings.length === 0) {
    ensureRoom(6);
    doc.setTextColor(90);
    doc.text('No findings recorded for this contract.', marginX, y);
    y += 8;
  } else {
    for (const finding of findings) {
      const title = `${(finding.severity || 'medium').toUpperCase()} — ${finding.title || 'Untitled finding'}`;
      const descWrapped = doc.splitTextToSize(finding.description || 'No description recorded.', 176);
      const playbookLine = finding.playbook_alignment
        ? `Playbook: ${finding.playbook_alignment.replace('_', ' ')}${finding.clause_type ? ` (${finding.clause_type})` : ''}`
        : null;
      const piiLine = finding.contains_pii ? 'Contains PII — evidence quote masked in this pack' : null;
      const rowHeight = 6 + 5 * descWrapped.length + (playbookLine ? 5 : 0) + (piiLine ? 5 : 0) + 3;
      ensureRoom(Math.min(rowHeight, pageBottom - 18));
      doc.setFont('helvetica', 'bold');
      doc.setTextColor(20);
      doc.text(title, marginX, y);
      y += 5.5;
      doc.setFont('helvetica', 'normal');
      doc.setTextColor(70);
      doc.text(descWrapped, marginX, y);
      y += 5 * descWrapped.length;
      if (playbookLine) {
        doc.setTextColor(90);
        doc.text(playbookLine, marginX, y);
        y += 5;
      }
      if (piiLine) {
        doc.setTextColor(130, 60, 150);
        doc.text(piiLine, marginX, y);
        y += 5;
      }
      y += 3;
    }
  }

  heading('How to verify this pack');
  const howTo =
    (proofPackage.how_to_verify as string) ||
    'Open verify-offline.html (included in this ZIP) in any browser. Load proof-package.json when prompted. ' +
      'The page recomputes SHA-256 hashes locally and reads the on-chain record from a public Sepolia RPC endpoint — LexProof does not need to be online.';
  doc.setFontSize(10);
  doc.setFont('helvetica', 'normal');
  doc.setTextColor(20);
  const howToWrapped = doc.splitTextToSize(howTo, 182);
  ensureRoom(5 * howToWrapped.length);
  doc.text(howToWrapped, marginX, y);
  y += 5 * howToWrapped.length + 4;

  return doc.output('blob');
}

/**
 * Builds and downloads a single ZIP containing the cryptographic proof
 * bundle, the offline verifier page, a machine-readable findings export, and
 * a human-readable PDF summary — everything needed to hand this contract's
 * compliance evidence to an auditor or counterparty in one file.
 */
export async function buildAndDownloadEvidencePack(params: EvidencePackParams): Promise<void> {
  const [proofPackage, findings, verifierHtml, anchors] = await Promise.all([
    fetchProofPackage(params.passportId),
    fetchFindings(params.contractId),
    fetchOfflineVerifierHtml(),
    fetchAnchors(params.evidence),
  ]);

  const summaryPdf = await buildSummaryPdf(params, proofPackage, findings, anchors);

  const JSZip = (await import('jszip')).default;
  const zip = new JSZip();
  zip.file('compliance-summary.pdf', summaryPdf);
  zip.file('proof-package.json', JSON.stringify(proofPackage, null, 2));
  zip.file('findings.json', JSON.stringify(findings, null, 2));
  if (verifierHtml) {
    zip.file('verify-offline.html', verifierHtml);
  }
  zip.file(
    'README.txt',
    'LexProof Compliance Evidence Pack\n' +
      '==================================\n\n' +
      `Contract: ${params.contractName} (${params.contractId}), version ${params.contractVersion}\n` +
      `Passport: ${params.passportId}\n` +
      `Generated: ${new Date().toISOString()}\n\n` +
      'Contents:\n' +
      '- compliance-summary.pdf  Human-readable summary: hashes, anchoring status, and AI findings\n' +
      '- proof-package.json      Machine-readable cryptographic proof bundle\n' +
      '- findings.json           Full AI risk & compliance findings for this contract\n' +
      (verifierHtml ? '- verify-offline.html     Offline verifier — open in any browser, load proof-package.json\n' : '') +
      '\nThis pack requires no LexProof account or server access to verify. See compliance-summary.pdf ' +
      '("How to verify this pack") for details.\n',
  );

  const blob = await zip.generateAsync({ type: 'blob' });
  downloadBlob(blob, `lexproof-evidence-pack-${slugify(params.contractName)}-${dateStamp()}.zip`);
}
