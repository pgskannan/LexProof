// Phase 3J-A: required E2E environment variables, validated up front with a
// clear, specific error rather than letting a test fail deep in a login
// attempt with a confusing message. Never hard-code credentials here.

export type E2EEnv = {
  baseURL: string
  userEmail: string
  userPassword: string
}

function required(name: string): string {
  const value = process.env[name]
  if (!value) {
    throw new Error(
      `Missing required E2E environment variable: ${name}. ` +
        `Set it in your shell or in frontend/.env.e2e.local (copy frontend/.env.e2e.local.example). ` +
        `See frontend/e2e/README.md.`,
    )
  }
  return value
}

export function getE2EEnv(): E2EEnv {
  return {
    baseURL: process.env.E2E_BASE_URL || 'http://localhost:3000',
    userEmail: required('E2E_USER_EMAIL'),
    userPassword: required('E2E_USER_PASSWORD'),
  }
}

// Phase 3K-A: the golden-path role-separated workflow test needs THREE
// distinct real Firebase-authenticated identities -- contract_owner,
// reviewer, and approver -- never the admin account (see e2e/README.md and
// the Phase 3K-A report for why: proving real separation-of-duties requires
// logging in as each role's own Firebase user, not bypassing it). Kept as a
// separate function/type from getE2EEnv() above so the existing smoke test
// is completely untouched.

export type WorkflowE2EEnv = {
  baseURL: string
  ownerEmail: string
  ownerPassword: string
  reviewerEmail: string
  reviewerPassword: string
  // Added for the E2E workflow audit's negative/security tests (Phase 4B,
  // "unauthorized reviewer"): demo-approver-1 is a real org member who does
  // NOT hold the reviewer role, so attempting the real "Approve" action as
  // this identity is a genuine, backend-enforced authorization denial, not
  // a fabricated one. Optional (not `required()`) so the existing golden-path
  // test, which never reads it, keeps working even if a .env.e2e.local
  // predates this addition.
  approverEmail?: string
  approverPassword?: string
}

export function getWorkflowE2EEnv(): WorkflowE2EEnv {
  return {
    baseURL: process.env.E2E_BASE_URL || 'http://localhost:3000',
    ownerEmail: required('E2E_OWNER_EMAIL'),
    ownerPassword: required('E2E_OWNER_PASSWORD'),
    reviewerEmail: required('E2E_REVIEWER_EMAIL'),
    reviewerPassword: required('E2E_REVIEWER_PASSWORD'),
    approverEmail: process.env.E2E_APPROVER_EMAIL,
    approverPassword: process.env.E2E_APPROVER_PASSWORD,
  }
}

// Separate, explicit required() accessor for tests that specifically need
// the approver identity (Phase 4B) -- fails with the same clear error as
// every other required() call rather than a confusing "undefined" deep
// inside a login attempt.
export function getApproverCredentials(): { approverEmail: string; approverPassword: string } {
  return {
    approverEmail: required('E2E_APPROVER_EMAIL'),
    approverPassword: required('E2E_APPROVER_PASSWORD'),
  }
}

// Used only by the audit-trail verification step of the full real-upload
// lifecycle test (Phase 6): the audit log page (/dashboard/admin/audit-log)
// is gated to admin/auditor roles (api/audit_log.py's require_roles), and
// demo-admin-1 is the existing demo admin identity already provisioned in
// an earlier phase (backend/scripts/provision_demo_admin_email_password.py)
// -- not a new identity, not the real developer's own personal account.
export function getAdminCredentials(): { adminEmail: string; adminPassword: string } {
  return {
    adminEmail: required('E2E_ADMIN_EMAIL'),
    adminPassword: required('E2E_ADMIN_PASSWORD'),
  }
}


// E2E security/workflow follow-up, Phase 2 (cross-tenant isolation): a
// genuinely SEPARATE second org ("Tenant B") needs its own real
// owner/reviewer Firebase identities -- see
// backend/scripts/provision_e2e_security_identities.py and
// create_approval_demo_fixture.py's create_cross_tenant_isolation_fixture().
export function getTenantBCredentials(): {
  tenantBOwnerEmail: string
  tenantBOwnerPassword: string
  tenantBReviewerEmail: string
  tenantBReviewerPassword: string
} {
  return {
    tenantBOwnerEmail: required('E2E_TENANT_B_OWNER_EMAIL'),
    tenantBOwnerPassword: required('E2E_TENANT_B_OWNER_PASSWORD'),
    tenantBReviewerEmail: required('E2E_TENANT_B_REVIEWER_EMAIL'),
    tenantBReviewerPassword: required('E2E_TENANT_B_REVIEWER_PASSWORD'),
  }
}

// E2E security/workflow follow-up, Phase 3 (dual-role separation-of-duty):
// a single real identity holding BOTH contract_owner and reviewer -- see
// create_approval_demo_fixture.py's create_dual_role_sod_fixture().
export function getDualRoleCredentials(): { dualRoleEmail: string; dualRolePassword: string } {
  return {
    dualRoleEmail: required('E2E_DUAL_ROLE_EMAIL'),
    dualRolePassword: required('E2E_DUAL_ROLE_PASSWORD'),
  }
}
