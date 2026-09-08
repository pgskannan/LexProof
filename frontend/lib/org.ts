export type OrgMembership = {
  org_id: string
  name?: string | null
  status?: string | null
  roles: string[]
  member_status?: string | null
}

export type MeResponse = {
  user_id: string
  email?: string | null
  display_name?: string | null
  orgs: OrgMembership[]
}

export type OrgMember = {
  user_id: string
  org_id: string
  email?: string | null
  display_name?: string | null
  roles: string[]
  status: string
}

export type WorkflowState = {
  id: string
  name: string
  is_initial?: boolean
  is_terminal?: boolean
}

export type WorkflowTransition = {
  id: string
  from_state: string
  to_state: string
  action_name: string
  allowed_roles: string[]
  requires_not_actor?: string[]
}

export type WorkflowDefinition = {
  definition_id: string
  org_id: string
  name: string
  version: number
  is_active: boolean
  states: WorkflowState[]
  transitions: WorkflowTransition[]
  created_by?: string | null
  created_at?: string | null
}

export type WorkflowInstance = {
  instance_id: string
  org_id: string
  definition_id: string
  definition_version?: number
  entity_type: string
  entity_id: string
  current_state: string
  status: string
  available_roles?: string[]
  created_by?: string | null
  created_at?: string | null
  updated_at?: string | null
  metadata?: { contract_id?: string }
}

export type WorkflowHistoryEvent = {
  event_id?: string
  transition_id: string
  from_state: string
  to_state: string
  actor_id: string
  actor_roles_at_time?: string[]
  comment?: string | null
  occurred_at?: string | null
}
