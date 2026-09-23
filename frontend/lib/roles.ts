export type OrgRole = 'admin' | 'contract_owner' | 'reviewer' | 'approver' | 'auditor'

export const ALL_ROLES: OrgRole[] = ['admin', 'contract_owner', 'reviewer', 'approver', 'auditor']

export const ROLE_LABELS: Record<OrgRole, string> = {
  admin: 'Admin',
  contract_owner: 'Contract owner',
  reviewer: 'Reviewer',
  approver: 'Approver',
  auditor: 'Auditor',
}

export function isOrgRole(value: string): value is OrgRole {
  return ALL_ROLES.includes(value as OrgRole)
}

export function hasRole(roles: string[] | undefined, role: OrgRole): boolean {
  return (roles || []).includes(role)
}

export function isAdmin(roles: string[] | undefined): boolean {
  return hasRole(roles, 'admin')
}

export function canAccessEvaluation(roles: string[] | undefined): boolean {
  return hasRole(roles, 'admin') || hasRole(roles, 'reviewer') || hasRole(roles, 'auditor')
}
