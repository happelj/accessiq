export type OperatorRole =
  | "security_admin"
  | "iam_admin"
  | "auditor"
  | "helpdesk"
  | "manager"
  | "employee"
  | "administrator"
  | "help_desk";

export interface TokenResponse {
  access_token: string;
  token_type: "bearer" | string;
  expires_in: number;
}

export interface User {
  id: number;
  name: string;
  email: string;
  department: string;
  active: boolean;
  operator_role: OperatorRole;
}

export interface Application {
  id: number;
  name: string;
  slug: string;
}

export interface Entitlement {
  id: number;
  name: string;
  slug: string;
  application_id: number;
}

export interface AccessAssignment {
  id: number;
  user_id: number;
  application_id: number;
  application: string;
  entitlement_id: number;
  entitlement: string;
  status: string;
  granted_at: string;
}

export interface HealthResponse {
  status: string;
  correlation_id: string | null;
  subsystems: Record<string, { status: string; details: Record<string, unknown> }>;
  metrics: Record<string, number>;
}

export interface Connector {
  name: string;
  display_name: string;
  enabled: boolean;
  supported_operations: string[];
}

export interface ConnectorHealth {
  connector: string;
  status: string;
  message: string;
  timestamp: string;
  details: Record<string, unknown>;
}

export interface ProvisioningJob {
  id: number;
  correlation_id: string;
  connector: string;
  operation: string;
  target_type: string;
  target_id: string | null;
  status: string;
  attempt_count: number;
  retry_count: number;
  max_attempts: number;
  retryable: boolean;
  last_error: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  duration_ms: number | null;
}

export interface ProvisioningHistory {
  id: number;
  job_id: number;
  correlation_id: string;
  connector: string;
  operation: string;
  event_type: string;
  status: string;
  message: string;
  attempt: number;
  retryable: boolean;
  duration_ms: number | null;
  details: Record<string, unknown>;
  created_at: string;
}

export interface Campaign {
  id: number;
  name: string;
  description: string | null;
  status: string;
  created_by: number;
  default_reviewer_id: number;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  cancelled_at: string | null;
  total_items: number;
  completed_items: number;
  approval_count: number;
  revocation_count: number;
  abstain_count: number;
  completion_percentage: number;
}

export interface RemediationJob {
  id: number;
  campaign_id: number;
  review_item_id: number;
  provisioning_job_id: number | null;
  correlation_id: string;
  remediation_type: string;
  status: string;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  last_error: string | null;
  initiated_by: number;
}

export interface ScimListResponse<T> {
  schemas: string[];
  totalResults: number;
  startIndex: number;
  itemsPerPage: number;
  Resources: T[];
}

export interface ScimGroup {
  id: string;
  displayName: string;
  members?: Array<{ value: string; display?: string; $ref?: string }>;
  meta?: { resourceType?: string; location?: string; lastModified?: string };
}

export interface GraphCacheStatus {
  enabled: boolean;
  built: boolean;
  node_count: number;
  edge_count: number;
  built_at: string | null;
}

export interface GraphExport {
  nodes?: unknown[];
  edges?: unknown[];
  summary?: Record<string, unknown>;
}

export interface LlmProviderMetadata {
  name: string;
  display_name: string;
  enabled: boolean;
  available: boolean;
  supports_streaming: boolean;
  model: string | null;
  details: Record<string, unknown>;
}

export interface LlmProviderHealth {
  provider: string;
  status: string;
  message: string;
  metadata: LlmProviderMetadata;
}

export interface AIProvidersResponse {
  configured_provider: string;
  enabled: boolean;
  providers: LlmProviderHealth[];
}

export interface Citation {
  id: string;
  title: string;
  reference: string;
  correlation_id: string | null;
}

export interface AIEvidence {
  id: string;
  evidence_type: string;
  title: string;
  description: string;
  reference: string;
  timestamp: string | null;
  correlation_id: string | null;
  relationship_type: string | null;
  node_id: string | null;
  edge_id: string | null;
  distance: number | null;
  priority: number;
  rank_score: number;
  token_estimate: number;
}

export interface AIExplanationResponse {
  answer: string;
  citations: Citation[];
  evidence: AIEvidence[];
  provider: LlmProviderMetadata;
  timing: {
    context_ms: number;
    provider_ms: number;
    total_ms: number;
  };
  intent: {
    intent: string;
    confidence: number;
    matched_rules: string[];
    normalized_question: string;
    user_id: number | null;
    application_id: number | null;
    entitlement_id: number | null;
  };
}

export interface AIExplainPayload {
  question: string;
  provider?: string;
  user_id?: number;
  application_id?: number;
  entitlement_id?: number;
  max_tokens?: number;
}
