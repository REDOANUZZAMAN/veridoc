/** Shapes returned by the FastAPI backend. Kept narrow on purpose: panels read
 *  the fields they display, and unknown extras pass through untouched. */

export type RiskBand = "low_concern" | "review_recommended" | "high_concern";
export type Severity = "info" | "low" | "medium" | "high" | "critical";
export type FindingStatus = "open" | "confirmed" | "dismissed" | "information_requested";
export type FindingKind =
  | "forensic"
  | "aigc"
  | "tampering"
  | "consistency"
  | "cross_document";

export interface Region {
  x: number;
  y: number;
  width: number;
  height: number;
  unit?: string;
}

export interface UserRef {
  id: string;
  full_name: string;
  email: string;
  role_name?: string | null;
  initials?: string | null;
}

export interface SessionUser extends UserRef {
  role_label?: string | null;
  job_title?: string | null;
  team?: string | null;
  permissions: string[];
  must_change_password?: boolean;
  is_active?: boolean;
  last_login_at?: string | null;
  created_at?: string | null;
}

export interface Finding {
  finding_id: string;
  kind: FindingKind;
  kind_label: string;
  category: string;
  code: string;
  severity: Severity;
  confidence: number;
  title: string;
  description: string;
  detector: string;
  model_version: string;
  status: FindingStatus;
  page: number | null;
  region: Region | null;
  evidence: Record<string, unknown>;
  recommendation: string | null;
  created_at: string | null;
  review_reason: string | null;
  provenance: string;
  // kind-specific extras
  tamper_type?: string;
  affected_field?: string | null;
  affected_value?: string | null;
  provider_key?: string;
  provider_label?: string;
  is_demo_provider?: boolean;
  likelihood_band?: string;
  indicator_scores?: Record<string, number>;
  rule_code?: string;
  fields_involved?: string[];
  expected?: string | null;
  actual?: string | null;
  field_key?: string;
  value_a?: string | null;
  value_b?: string | null;
  similarity?: number | null;
  counterpart_document_id?: string | null;
  signal_group?: string;
}

export interface RiskSignal {
  code: string;
  label: string;
  category: string;
  category_label: string;
  severity: Severity;
  confidence: number;
  weight: number;
  contribution: number;
  source: string;
  detector?: string | null;
  model_version?: string | null;
  finding_kind?: string | null;
  finding_id?: string | null;
  human_confirmed: boolean;
  page?: number | null;
}

export interface RiskAssessment {
  id: string;
  score: number;
  band: RiskBand;
  band_label: string;
  weights_version: string;
  signals: RiskSignal[];
  category_scores: Record<
    string,
    { label: string; raw_contribution: number; cap: number; saturated_score: number; signal_count: number }
  >;
  top_reasons: Array<{
    code: string;
    label: string;
    category: string;
    severity: Severity;
    confidence: number;
    contribution: number;
    source: string;
    finding_id?: string | null;
    page?: number | null;
  }>;
  explanation: string;
  interpretation_note: string;
  coverage: Record<string, unknown> & { degraded_stages?: string[]; mitigations?: unknown[] };
  created_at: string;
}

export interface Stage {
  key: string;
  label: string;
  status: "pending" | "running" | "completed" | "skipped" | "unavailable" | "failed";
  message: string;
  duration_ms: number;
  findings: number;
  provider: Record<string, unknown> | null;
  detail: Record<string, any>;
  started_at: string | null;
  finished_at: string | null;
}

export interface AnalysisRun {
  id: string;
  status: string;
  queue_mode: string;
  queue_job_id: string | null;
  pipeline_version: string;
  rules_version: string;
  stages: Stage[];
  provider_snapshot: Record<string, any>;
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number | null;
  findings_count: number;
  error: string | null;
  created_at: string;
}

export interface DocumentPage {
  page_number: number;
  width: number;
  height: number;
  render_dpi: number;
  has_text_layer: boolean;
  text_char_count: number;
  layers: string[];
}

export interface ExtractedField {
  field_key: string;
  field_label: string;
  value_raw: string | null;
  value: string | null;
  value_type: string;
  confidence: number;
  page: number | null;
  bbox: Region | null;
  source: string;
  required: boolean;
  group: string | null;
}

export interface VerificationResultBody {
  outcome: "match" | "partial_match" | "mismatch" | "not_found" | "unavailable";
  summary: string;
  checks: Array<{
    key: string;
    label: string;
    expected: string | null;
    actual: string | null;
    passed: boolean | null;
    note: string;
  }>;
  latency_ms: number;
  reference_id: string | null;
  is_demo_data: boolean;
  data_source_disclaimer: string;
  error: string | null;
  completed_at: string;
}

export interface VerificationRequest {
  id: string;
  request_type: string;
  provider_key: string;
  provider_label: string;
  provider_mode: string;
  is_demo_provider: boolean;
  status: string;
  trigger: string;
  requested_at: string;
  request_payload: Record<string, string>;
  result: VerificationResultBody | null;
  document_ref?: string | null;
  claim_number?: string | null;
}

export interface DocumentSummary {
  id: string;
  document_ref: string;
  claim_id: string | null;
  claim_number: string | null;
  original_filename: string;
  mime_type: string;
  file_extension: string;
  file_size: number;
  sha256: string;
  page_count: number;
  source: string;
  processing_status: string;
  processing_message: string | null;
  malware_status: string;
  classification_type: string | null;
  classification_label: string | null;
  classification_confidence: number | null;
  risk_score: number | null;
  risk_band: RiskBand | null;
  risk_band_label?: string | null;
  verification_state: string;
  uploaded_at: string;
  uploaded_by: UserRef | null;
  finding_counts: {
    total?: number;
    open?: number;
    confirmed?: number;
    dismissed?: number;
    by_severity?: Record<string, number>;
    by_kind?: Record<string, number>;
  };
}

export interface DocumentDetail extends DocumentSummary {
  artifact_prefix: string;
  malware_detail: Record<string, any>;
  classification_detail: Record<string, any>;
  pages: DocumentPage[];
  ocr: Array<{
    page_number: number;
    provider: string;
    provider_version: string;
    status: string;
    error: string | null;
    mean_confidence: number | null;
    word_count: number;
    duration_ms: number;
    raw_text: string;
    words: Array<{ text: string; confidence: number; bbox: Region; line: number }>;
  }>;
  extracted_fields: ExtractedField[];
  line_items: Array<{ field_key: string; label: string; raw: string | null; value: string | null; page: number | null; bbox: Region | null }>;
  metadata_entries: Array<{ group: string; key: string; value: string | null; is_anomalous: boolean; note: string | null }>;
  findings: Finding[];
  risk_assessment: RiskAssessment | null;
  latest_run: AnalysisRun | null;
  verification: VerificationRequest[];
  review_actions: Array<{
    id: string;
    action: string;
    reason: string | null;
    finding_id: string | null;
    finding_kind: string | null;
    previous_status: string | null;
    new_status: string | null;
    actor: UserRef | null;
    actor_role: string | null;
    created_at: string;
    context: Record<string, unknown>;
  }>;
  schema_fields: Array<{ key: string; label: string; type: string; required: boolean; group: string; sensitive: boolean }>;
  schema_label?: string;
  verified_by: UserRef | null;
  verification_note: string | null;
  retention_expires_at: string | null;
}

export interface ClaimSummary {
  id: string;
  claim_number: string;
  customer_name: string;
  policy_number: string;
  insurer: string;
  claim_type: string;
  status: string;
  currency: string;
  claimed_amount: string | null;
  risk_score: number | null;
  risk_band: RiskBand | null;
  risk_band_label?: string | null;
  incident_date: string | null;
  document_count: number;
  open_findings: number;
  assigned_investigator: UserRef | null;
  created_at: string;
  updated_at: string;
}

export interface ClaimDetail extends ClaimSummary {
  customer_dob: string | null;
  customer_email: string | null;
  customer_phone: string | null;
  summary: string | null;
  decision: string | null;
  decision_reason: string | null;
  decided_at: string | null;
  created_by: UserRef | null;
  documents: DocumentSummary[];
  verification: VerificationRequest[];
  findings_summary: {
    total: number;
    by_severity: Record<string, number>;
    by_kind: Record<string, number>;
    open: number;
    confirmed: number;
    dismissed: number;
    top: Finding[];
  };
  investigations: Investigation[];
  cross_document: {
    documents_compared?: number;
    fields_compared?: number;
    agreements?: number;
    mismatches?: number;
    comparisons?: Array<{
      field: string;
      label: string;
      document_a: string;
      document_b: string;
      value_a: string;
      value_b: string;
      agrees: boolean;
      similarity: number | null;
      detail: string;
      mode: string;
      skipped?: boolean;
      against_claim_record?: boolean;
    }>;
  };
  timeline: Array<{ at: string; type: string; summary: string; actor: UserRef | null }>;
}

export interface Investigation {
  id: string;
  case_number: string;
  claim_id: string | null;
  document_id: string | null;
  title: string;
  status: string;
  priority: string;
  assigned_to: UserRef | null;
  opened_by: UserRef | null;
  opened_at: string | null;
  closed_at: string | null;
  resolution: string | null;
  resolution_reason: string | null;
  summary: string | null;
  risk_score_at_open: number | null;
  context: Record<string, unknown>;
  note_count: number;
  created_at: string;
  updated_at: string;
  claim_number?: string | null;
  customer_name?: string | null;
  document_ref?: string | null;
  document_type?: string | null;
  risk_score?: number | null;
  risk_band?: RiskBand | null;
  notes?: Array<{ id: string; body: string; note_type: string; is_internal: boolean; author: UserRef | null; created_at: string }>;
  claim?: Record<string, any>;
  documents?: Array<Record<string, any>>;
  findings?: Finding[];
}

export interface Paged<T> {
  items: T[];
  meta: {
    total: number;
    page: number;
    page_size: number;
    pages: number;
    has_next: boolean;
    has_previous: boolean;
  };
}

export interface DashboardData {
  generated_at: string;
  cards: Record<string, number>;
  documents_by_status: Array<{ status: string; count: number }>;
  risk_distribution: Array<{ band: string; label: string; count: number }>;
  document_types: Array<{ type: string; label: string; count: number }>;
  findings_by_kind: Record<string, { total: number; open: number; by_severity: Record<string, number> }>;
  top_consistency_findings: Array<{ code: string; count: number }>;
  top_forensic_findings: Array<{ code: string; count: number }>;
  daily_volume: Array<{ date: string; documents: number; high_concern: number; review_recommended: number; low_concern: number }>;
  claims_by_status: Array<{ status: string; count: number }>;
  verification_outcomes: Array<{ outcome: string; count: number }>;
  verification_note: string;
  verification_states: Array<{ state: string; count: number }>;
  recent_investigations: Investigation[];
  pipeline_runs: Record<string, { count: number; avg_duration_ms: number }>;
}

export interface AuditEntry {
  id: string;
  seq: number;
  action: string;
  resource_type: string;
  resource_id: string | null;
  summary: string | null;
  actor_email: string | null;
  actor_role: string | null;
  ip_address: string | null;
  request_id: string | null;
  before_state: Record<string, unknown> | null;
  after_state: Record<string, unknown> | null;
  metadata_json: Record<string, unknown>;
  prev_hash: string | null;
  entry_hash: string;
  created_at: string;
}

export interface DetectionRule {
  id: string;
  code: string;
  name: string;
  category: string;
  description: string;
  default_severity: Severity;
  weight: number;
  enabled: boolean;
  applies_to: string[];
  params: Record<string, unknown>;
  version: string;
  is_system: boolean;
  updated_at: string;
}

export interface ProviderConfig {
  id: string;
  kind: string;
  key: string;
  label: string;
  description: string;
  is_active: boolean;
  is_demo: boolean;
  credential_env_keys: string[];
  settings_json: Record<string, unknown>;
  model_name: string | null;
  model_version: string | null;
  health_status: string;
  health_detail: string | null;
  updated_at: string;
}

export interface ReportSummary {
  id: string;
  report_ref: string;
  report_type: string;
  title: string;
  format: string;
  file_size: number;
  sha256: string | null;
  document_sha256: string | null;
  document_id: string | null;
  claim_id: string | null;
  pipeline_version: string | null;
  rules_version: string | null;
  generated_by: UserRef | null;
  created_at: string;
  notes: string | null;
}
