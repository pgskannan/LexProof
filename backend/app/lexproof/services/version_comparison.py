"""
Version Comparison Engine for Contract Time Machine

Detects clause changes between contract versions:
- Added clauses
- Removed clauses
- Modified clauses
- Unchanged clauses

Calculates risk deltas, compliance deltas, and business impact.
"""

from typing import Dict, List, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum


class ClauseChangeType(Enum):
    """Type of clause change"""
    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"
    UNCHANGED = "unchanged"


@dataclass
class Clause:
    """Represents a single clause in a contract"""
    text: str
    hash: str
    risk_score: float
    compliance_score: float
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ClauseChange:
    """Represents a change between two clauses"""
    change_type: ClauseChangeType
    previous: Clause | None
    current: Clause | None
    risk_delta: float
    compliance_delta: float
    business_impact: str


@dataclass
class VersionComparison:
    """Result of comparing two contract versions"""
    contract_id: str
    version_from: int
    version_to: int
    total_clauses: int
    unchanged_clauses: int
    added_clauses: int
    removed_clauses: int
    modified_clauses: int
    clause_changes: List[ClauseChange]
    risk_delta: float
    compliance_delta: float
    policy_delta: str
    business_impact: str
    blockchain_proof_verified: bool = False


class VersionComparisonEngine:
    """
    Engine for comparing contract versions and detecting changes

    Detects:
    - Added clauses
    - Removed clauses
    - Modified clauses
    - Unchanged clauses
    """

    def __init__(self):
        pass

    def compare_versions(
        self,
        contract_id: str,
        version_from: int,
        version_to: int,
        previous_clauses: List[Clause],
        current_clauses: List[Clause],
        previous_policy_version: str,
        current_policy_version: str,
        previous_risk_score: float,
        current_risk_score: float,
        previous_compliance_score: float,
        current_compliance_score: float,
    ) -> VersionComparison:
        """
        Compare two contract versions

        Args:
            contract_id: Contract identifier
            version_from: Previous version number
            version_to: Current version number
            previous_clauses: Clauses in previous version
            current_clauses: Clauses in current version
            previous_policy_version: Previous policy version
            current_policy_version: Current policy version
            previous_risk_score: Previous risk score
            current_risk_score: Current risk score
            previous_compliance_score: Previous compliance score
            current_compliance_score: Current compliance score

        Returns:
            VersionComparison with all changes and deltas
        """
        # Create hash map for quick lookup
        def clause_key(clause: Clause) -> str:
            return str(clause.metadata.get("clause_id", clause.hash))

        previous_clauses_map = {clause_key(clause): clause for clause in previous_clauses}
        current_clauses_map = {clause_key(clause): clause for clause in current_clauses}

        # Find all unique hashes
        all_hashes = set(previous_clauses_map.keys()) | set(current_clauses_map.keys())

        clause_changes = []
        unchanged_clauses = 0
        added_clauses = 0
        removed_clauses = 0
        modified_clauses = 0

        for clause_hash in all_hashes:
            if clause_hash in previous_clauses_map and clause_hash in current_clauses_map:
                # Clause exists in both versions - check if modified
                previous_clause = previous_clauses_map[clause_hash]
                current_clause = current_clauses_map[clause_hash]

                if previous_clause.text == current_clause.text:
                    # Unchanged clause
                    unchanged_clauses += 1
                else:
                    # Modified clause
                    modified_clauses += 1
                    clause_changes.append(ClauseChange(
                        change_type=ClauseChangeType.MODIFIED,
                        previous=previous_clause,
                        current=current_clause,
                        risk_delta=current_clause.risk_score - previous_clause.risk_score,
                        compliance_delta=current_clause.compliance_score - previous_clause.compliance_score,
                        business_impact=self._calculate_business_impact(
                            previous_clause.risk_score,
                            current_clause.risk_score,
                            previous_clause.compliance_score,
                            current_clause.compliance_score
                        )
                    ))
            elif clause_hash in current_clauses_map:
                # Clause added
                added_clauses += 1
                clause_changes.append(ClauseChange(
                    change_type=ClauseChangeType.ADDED,
                    previous=None,
                    current=current_clauses_map[clause_hash],
                    risk_delta=current_clauses_map[clause_hash].risk_score,
                    compliance_delta=current_clauses_map[clause_hash].compliance_score,
                    business_impact="Positive change" if current_clauses_map[clause_hash].risk_score < 50 else "Negative change"
                ))
            else:
                # Clause removed
                removed_clauses += 1
                clause_changes.append(ClauseChange(
                    change_type=ClauseChangeType.REMOVED,
                    previous=previous_clauses_map[clause_hash],
                    current=None,
                    risk_delta=-previous_clauses_map[clause_hash].risk_score,
                    compliance_delta=-previous_clauses_map[clause_hash].compliance_score,
                    business_impact="Positive change" if previous_clauses_map[clause_hash].risk_score < 50 else "Negative change"
                ))

        # Calculate deltas
        risk_delta = current_risk_score - previous_risk_score
        compliance_delta = current_compliance_score - previous_compliance_score

        # Determine business impact
        business_impact = self._calculate_business_impact(
            previous_risk_score,
            current_risk_score,
            previous_compliance_score,
            current_compliance_score
        )

        # Determine policy delta
        policy_delta = self._determine_policy_delta(previous_policy_version, current_policy_version)

        return VersionComparison(
            contract_id=contract_id,
            version_from=version_from,
            version_to=version_to,
            total_clauses=len(all_hashes),
            unchanged_clauses=unchanged_clauses,
            added_clauses=added_clauses,
            removed_clauses=removed_clauses,
            modified_clauses=modified_clauses,
            clause_changes=clause_changes,
            risk_delta=risk_delta,
            compliance_delta=compliance_delta,
            policy_delta=policy_delta,
            business_impact=business_impact
        )

    def _calculate_business_impact(
        self,
        previous_risk_score: float,
        current_risk_score: float,
        previous_compliance_score: float,
        current_compliance_score: float
    ) -> str:
        """
        Calculate business impact based on risk and compliance deltas

        Args:
            previous_risk_score: Previous risk score
            current_risk_score: Current risk score
            previous_compliance_score: Previous compliance score
            current_compliance_score: Current compliance score

        Returns:
            Business impact description
        """
        risk_change = current_risk_score - previous_risk_score
        compliance_change = current_compliance_score - previous_compliance_score

        if risk_change < -10 and compliance_change > 10:
            return "Significant Improvement - Major risk reduction with improved compliance"
        elif risk_change < -5 and compliance_change > 5:
            return "Significant Improvement - Risk reduced, compliance improved"
        elif risk_change > 10 and compliance_change < -10:
            return "Significant Deterioration - Major risk increase with reduced compliance"
        elif risk_change > 5 and compliance_change < -5:
            return "Significant Deterioration - Risk increased, compliance reduced"
        elif risk_change < 0 and compliance_change > 0:
            return "Improvement - Risk decreased, compliance improved"
        elif risk_change > 0 and compliance_change < 0:
            return "Deterioration - Risk increased, compliance reduced"
        elif risk_change == 0 and compliance_change == 0:
            return "No Change - Risk and compliance unchanged"
        else:
            return "Mixed Impact - Partial improvement or deterioration"

    def _determine_policy_delta(self, previous_version: str, current_version: str) -> str:
        """
        Determine policy version delta

        Args:
            previous_version: Previous policy version
            current_version: Current policy version

        Returns:
            Policy delta description
        """
        if previous_version == current_version:
            return "No policy changes"
        else:
            return f"Policy updated from {previous_version} to {current_version}"

    def get_summary(self, comparison: VersionComparison) -> Dict[str, Any]:
        """
        Get summary of comparison

        Args:
            comparison: VersionComparison object

        Returns:
            Dictionary with summary information
        """
        return {
            "contract_id": comparison.contract_id,
            "version_from": comparison.version_from,
            "version_to": comparison.version_to,
            "total_clauses": comparison.total_clauses,
            "unchanged": comparison.unchanged_clauses,
            "added": comparison.added_clauses,
            "removed": comparison.removed_clauses,
            "modified": comparison.modified_clauses,
            "risk_delta": comparison.risk_delta,
            "compliance_delta": comparison.compliance_delta,
            "policy_delta": comparison.policy_delta,
            "business_impact": comparison.business_impact,
            "blockchain_proof_verified": comparison.blockchain_proof_verified
        }

    def get_clause_change_details(self, comparison: VersionComparison) -> List[Dict[str, Any]]:
        """
        Get detailed clause change information

        Args:
            comparison: VersionComparison object

        Returns:
            List of clause change details
        """
        changes = []
        for clause_change in comparison.clause_changes:
            change_detail = {
                "change_type": clause_change.change_type.value,
                "previous_text": clause_change.previous.text if clause_change.previous else None,
                "current_text": clause_change.current.text if clause_change.current else None,
                "previous_risk": clause_change.previous.risk_score if clause_change.previous else None,
                "current_risk": clause_change.current.risk_score if clause_change.current else None,
                "previous_compliance": clause_change.previous.compliance_score if clause_change.previous else None,
                "current_compliance": clause_change.current.compliance_score if clause_change.current else None,
                "risk_delta": clause_change.risk_delta,
                "compliance_delta": clause_change.compliance_delta,
                "business_impact": clause_change.business_impact
            }
            changes.append(change_detail)
        return changes
