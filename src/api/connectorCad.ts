const API_BASE = import.meta.env.VITE_API_BASE_URL || '';

export type ConnectorInputType = 'text' | 'drawing' | 'photo';

export type AiApiStatus = {
  configured: boolean;
  provider: string;
  base_url_set: boolean;
  api_key_set: boolean;
  model: string;
  key_preview: string;
  missing?: string[];
  error?: string;
  error_type?: string;
};

export type AiTestResponse = {
  ok: boolean;
  extracted: Record<string, unknown>;
  meta?: {
    status?: string;
    provider?: string;
    model?: string;
    configured?: boolean;
    base_url_set?: boolean;
    api_key_set?: boolean;
    error?: string;
    error_type?: string;
  };
};

export type ConnectorJob = {
  job_id: string;
  status: 'idle' | 'uploading' | 'generating' | 'needs_confirmation' | 'completed' | 'failed';
  params?: Record<string, any>;
  files?: {
    model_step: string;
    model_stl: string;
    drawing_dxf: string;
    params_json: string;
    source_manifest: string;
    image_features?: string;
    vision_report?: string;
    image_search_results?: string;
    selected_image?: string;
    visual_recipe?: string;
    flat_front_dxf?: string;
    flat_rear_dxf?: string;
    flat_top_dxf?: string;
    flat_side_dxf?: string;
    flat_insertion_dxf?: string;
    flat_views_svg?: string;
    flat_recipe_json?: string;
    flat_view_classification_json?: string;
    flat_terminal_insertion_json?: string;
    flat_structure_report_json?: string;
    sop_wi_draft_json?: string;
    sop_wi_draft_html?: string;
    sop_wi_summary_md?: string;
    sop_wi_confirmation_checklist?: string;
    sop_wi_assets_manifest?: string;
    sop_wi_draft_pdf?: string;
    confirmation_status?: string;
    sop_wi_signed_html?: string;
    sop_wi_signed_json?: string;
    sop_wi_signed_summary_md?: string;
    sop_wi_signed_pdf?: string;
  };
  source_manifest_url?: string;
  source_domain?: Record<string, any>;
  source_audit_summary?: Record<string, any>;
  error?: string;
  warning?: string;
};

export type ConnectorImageSearchCandidate = {
  id: string;
  rank: number;
  title: string;
  image_url: string;
  thumbnail_url: string;
  source_url: string;
  domain: string;
  rank_reason?: string;
  score?: number;
  provider?: string;
  width?: number;
  height?: number;
  search_round?: string;
  part_match?: {
    match_level?: 'exact' | 'weak' | 'near_miss' | 'none' | string;
    query_part_number?: string;
    matched_part_number?: string;
    normalized_query?: string;
    normalized_matched?: string;
    reason?: string;
  };
  match_evidence?: {
    evidence_level?: 'high' | 'medium' | 'low' | 'unknown' | string;
    evidence_score?: number;
    title_has_exact?: boolean;
    source_url_has_exact?: boolean;
    image_url_has_exact?: boolean;
    thumbnail_url_has_exact?: boolean;
    domain_trusted?: boolean;
    download_probe_ok?: boolean;
    reasons?: string[];
    warnings?: string[];
  };
  generation_risk?: {
    requires_confirmation?: boolean;
    risk_level?: 'none' | 'notice' | 'confirm' | 'required_block' | string;
    risk_reasons?: string[];
    confirmation_code?: string;
    recommended_action?: string;
  };
};

export type ConnectorImageSearch = {
  search_id: string;
  query: string;
  expanded_query?: string;
  provider: string;
  status: 'success' | 'not_configured' | 'failed' | 'manual' | string;
  results: ConnectorImageSearchCandidate[];
  warnings: string[];
  refined_searches?: Array<{ query: string; status: string; results_count: number }>;
  exact_match_found?: boolean;
  match_summary?: {
    exact: number;
    weak: number;
    near_miss: number;
    none: number;
    has_exact: boolean;
    requires_part_mismatch_confirmation: boolean;
  };
  created_at?: string;
};

export async function getAiApiStatus(): Promise<AiApiStatus> {
  const response = await fetch(`${API_BASE}/api/ai/status`);
  return parseResponse(response);
}

export async function postAiTest(text: string): Promise<AiTestResponse> {
  const response = await fetch(`${API_BASE}/api/ai/test`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  });
  return parseResponse(response);
}

async function parseResponse(response: Response) {
  if (response.ok) return response.json();
  const text = await response.text();
  try {
    const parsed = JSON.parse(text);
    const detail = parsed.detail;
    const message = typeof detail === 'string' ? detail : detail?.message || detail?.error || text || `HTTP ${response.status}`;
    const error = new Error(message) as Error & { detail?: unknown; status?: number };
    error.detail = detail;
    error.status = response.status;
    return Promise.reject(error);
  } catch {
    throw new Error(text || `HTTP ${response.status}`);
  }
}

export type ProcurementSortBy = 'price' | 'location' | 'match';

export type ProcurementSearchRequest = {
  query: string;
  target_location: string;
  platforms: string[];
  sort_by: ProcurementSortBy;
  image_search_enabled?: boolean;
  source_types?: string[];
};

export type ProcurementResult = {
  id: string;
  title: string;
  platform: string;
  shop_name: string;
  price: number;
  currency: string;
  price_type: string;
  shipping_location: string;
  stock_status: string;
  moq: number;
  image_url: string;
  product_url: string;
  key_parameters: Record<string, string | number>;
  match_score: number;
  risk_tags: string[];
  updated_at: string;
  source_type?: string;
  source_name?: string;
  import_id?: string;
  data_freshness?: string;
};

export type ProcurementSearchResponse = {
  search_id: string;
  query: string;
  target_location: string;
  status: string;
  provider: string;
  sort_by: ProcurementSortBy;
  results: ProcurementResult[];
  summary: {
    total: number;
    platform_counts: Record<string, number>;
    lowest_price: number | null;
    recommended_count: number;
  };
  warnings: string[];
};

export async function searchProcurement(payload: ProcurementSearchRequest): Promise<ProcurementSearchResponse> {
  const response = await fetch(`${API_BASE}/api/procurement/search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return parseResponse(response);
}

export type ProcurementImageKeywordsResponse = {
  status: string;
  keywords: string[];
  detected: {
    dominant_color?: string;
    shape?: string;
    positions_candidate?: string;
    ocr_text?: string;
    connector_type?: string;
  };
  confidence: 'low' | 'medium' | 'high' | string;
  warnings: string[];
  image_id?: string;
};

export async function extractProcurementImageKeywords(file: File): Promise<ProcurementImageKeywordsResponse> {
  const form = new FormData();
  form.append('file', file);
  const response = await fetch(`${API_BASE}/api/procurement/image-keywords`, {
    method: 'POST',
    body: form,
  });
  return parseResponse(response);
}

export async function getProcurementSearch(searchId: string): Promise<ProcurementSearchResponse> {
  const response = await fetch(`${API_BASE}/api/procurement/search/${searchId}`);
  return parseResponse(response);
}

export function procurementCsvUrl(searchId: string): string {
  return `${API_BASE}/api/procurement/search/${searchId}/export.csv`;
}

export type ProcurementSource = {
  source_id: string;
  source_name: string;
  source_type: string;
  enabled: boolean;
  priority: number;
  platform_label: string;
  notes?: string;
  created_at?: string;
  updated_at?: string;
  auth_mode?: string;
  safe_mode?: boolean;
};

export type ProcurementImportResponse = {
  import_id: string;
  source_name: string;
  source_type: string;
  rows_total: number;
  rows_imported: number;
  rows_skipped: number;
  warnings: string[];
  offers: ProcurementResult[];
};

export async function importProcurementQuotes(file: File, sourceName: string, platformLabel: string): Promise<ProcurementImportResponse> {
  const form = new FormData();
  form.append('file', file);
  form.append('source_name', sourceName);
  form.append('platform_label', platformLabel);
  const response = await fetch(`${API_BASE}/api/procurement/import`, {
    method: 'POST',
    body: form,
  });
  return parseResponse(response);
}

export async function listProcurementSources(): Promise<{ sources: ProcurementSource[] }> {
  const response = await fetch(`${API_BASE}/api/procurement/sources`);
  return parseResponse(response);
}

export async function createProcurementSource(payload: Partial<ProcurementSource>): Promise<ProcurementSource> {
  const response = await fetch(`${API_BASE}/api/procurement/sources`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return parseResponse(response);
}

export async function updateProcurementSource(sourceId: string, payload: Partial<ProcurementSource>): Promise<ProcurementSource> {
  const response = await fetch(`${API_BASE}/api/procurement/sources/${sourceId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return parseResponse(response);
}

export async function deleteProcurementSource(sourceId: string): Promise<{ deleted: boolean; source_id: string }> {
  const response = await fetch(`${API_BASE}/api/procurement/sources/${sourceId}`, { method: 'DELETE' });
  return parseResponse(response);
}

export async function createTextConnectorJob(
  text: string,
  params?: Record<string, number>,
  options: { preferred_revision?: string; preferred_version_label?: string } = {},
): Promise<ConnectorJob> {
  const response = await fetch(`${API_BASE}/api/connector-cad/jobs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ input_type: 'text', text, params, ...options }),
  });
  return parseResponse(response);
}

export async function searchConnectorImages(query: string, maxResults = 8): Promise<ConnectorImageSearch> {
  const response = await fetch(`${API_BASE}/api/connector-cad/image-search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, max_results: maxResults }),
  });
  return parseResponse(response);
}

export async function getConnectorImageSearch(searchId: string): Promise<ConnectorImageSearch> {
  const response = await fetch(`${API_BASE}/api/connector-cad/image-search/${searchId}`);
  return parseResponse(response);
}

export async function createJobFromSelectedImage(
  searchId: string,
  candidateId: string,
  query?: string,
  acceptPartMismatchRisk = false,
  acceptGenerationRisk = false,
  acceptedRiskCode = '',
): Promise<ConnectorJob> {
  const response = await fetch(`${API_BASE}/api/connector-cad/jobs/from-selected-image`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      search_id: searchId,
      candidate_id: candidateId,
      query,
      accept_part_mismatch_risk: acceptPartMismatchRisk,
      accept_generation_risk: acceptGenerationRisk,
      accepted_risk_code: acceptedRiskCode,
    }),
  });
  return parseResponse(response);
}

export async function createJobFromManualImageUrl(
  query: string,
  imageUrl: string,
  sourceUrl = '',
  title = 'manual image URL',
): Promise<ConnectorJob> {
  const response = await fetch(`${API_BASE}/api/connector-cad/jobs/from-manual-image-url`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, image_url: imageUrl, source_url: sourceUrl, title }),
  });
  return parseResponse(response);
}

export async function createFileConnectorJob(inputType: 'drawing' | 'photo', file: File): Promise<ConnectorJob> {
  const form = new FormData();
  form.append('input_type', inputType);
  form.append('file', file);
  const response = await fetch(`${API_BASE}/api/connector-cad/jobs`, {
    method: 'POST',
    body: form,
  });
  return parseResponse(response);
}

export async function getConnectorJob(jobId: string): Promise<ConnectorJob> {
  const response = await fetch(`${API_BASE}/api/connector-cad/jobs/${jobId}`);
  return parseResponse(response);
}

export async function generateSopWiDraft(jobId: string): Promise<{ job_id: string; status: string; files: Record<string, string> }> {
  const response = await fetch(`${API_BASE}/api/connector-cad/jobs/${jobId}/sop-wi/generate`, {
    method: 'POST',
  });
  return parseResponse(response);
}

export async function getConfirmationStatus(jobId: string): Promise<Record<string, any>> {
  const response = await fetch(`${API_BASE}/api/connector-cad/jobs/${jobId}/confirmation-status`);
  return parseResponse(response);
}

export async function updateConfirmationItem(
  jobId: string,
  itemId: string,
  payload: { status: string; note?: string; confirmed_by?: string; role?: string },
): Promise<Record<string, any>> {
  const response = await fetch(`${API_BASE}/api/connector-cad/jobs/${jobId}/confirmation-status/items/${itemId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return parseResponse(response);
}

export async function resetConfirmationStatus(jobId: string): Promise<Record<string, any>> {
  const response = await fetch(`${API_BASE}/api/connector-cad/jobs/${jobId}/confirmation-status/reset`, {
    method: 'POST',
  });
  return parseResponse(response);
}

export async function exportSignedSopWi(jobId: string): Promise<{ job_id: string; status: string; files: Record<string, string> }> {
  const response = await fetch(`${API_BASE}/api/connector-cad/jobs/${jobId}/sop-wi/export-signed`, {
    method: 'POST',
  });
  return parseResponse(response);
}

export async function confirmConnectorParams(
  jobId: string,
  payload: {
    confirmed_params: Record<string, number>;
    accepted_unknowns: string[];
    notes?: string;
  },
): Promise<ConnectorJob> {
  const response = await fetch(`${API_BASE}/api/connector-cad/jobs/${jobId}/confirm-params`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return parseResponse(response);
}

export async function pollConnectorJob(jobId: string, maxAttempts = 20): Promise<ConnectorJob> {
  let lastJob: ConnectorJob | null = null;
  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    lastJob = await getConnectorJob(jobId);
    if (['completed', 'needs_confirmation', 'failed'].includes(lastJob.status)) return lastJob;
    await new Promise((resolve) => setTimeout(resolve, 700));
  }
  return lastJob || getConnectorJob(jobId);
}

export function fileUrl(job: ConnectorJob, key: keyof NonNullable<ConnectorJob['files']>): string {
  return job.files?.[key] || '#';
}

export async function listCadRegistryItems(filters: Record<string, string> = {}) {
  const query = new URLSearchParams(Object.entries(filters).filter(([, value]) => value));
  const response = await fetch(`${API_BASE}/api/cad-registry/items${query.toString() ? `?${query}` : ''}`);
  return parseResponse(response);
}

export const searchCadRegistryItems = listCadRegistryItems;

export async function getCadRegistryStats() {
  const response = await fetch(`${API_BASE}/api/cad-registry/stats`);
  return parseResponse(response);
}

export async function createCadRegistryItem(payload: Record<string, any>) {
  const response = await fetch(`${API_BASE}/api/cad-registry/items`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return parseResponse(response);
}

export async function updateCadRegistryItem(itemId: string, payload: Record<string, any>) {
  const response = await fetch(`${API_BASE}/api/cad-registry/items/${itemId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return parseResponse(response);
}

export async function reviewCadRegistryItem(itemId: string, payload: { status: string; reviewed_by?: string; review_note?: string }) {
  const response = await fetch(`${API_BASE}/api/cad-registry/items/${itemId}/review`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return parseResponse(response);
}

export async function deprecateCadRegistryItem(itemId: string, payload: { replacement_id?: string; reason?: string }) {
  const response = await fetch(`${API_BASE}/api/cad-registry/items/${itemId}/deprecate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return parseResponse(response);
}

export async function getCadRegistryItemHistory(itemId: string) {
  const response = await fetch(`${API_BASE}/api/cad-registry/items/${itemId}/history`);
  return parseResponse(response);
}

export async function refreshCadRegistryCache(itemId: string) {
  const response = await fetch(`${API_BASE}/api/cad-registry/items/${itemId}/refresh-cache`, { method: 'POST' });
  return parseResponse(response);
}

export async function getCadRegistryCache(itemId: string) {
  const response = await fetch(`${API_BASE}/api/cad-registry/items/${itemId}/cache`);
  return parseResponse(response);
}

export async function checkRegistryCache() {
  const response = await fetch(`${API_BASE}/api/cad-registry/cache/check`, { method: 'POST' });
  return parseResponse(response);
}

export async function checkRegistryItemCache(itemId: string) {
  const response = await fetch(`${API_BASE}/api/cad-registry/items/${itemId}/cache/check`, { method: 'POST' });
  return parseResponse(response);
}

export async function repairRegistryCache() {
  const response = await fetch(`${API_BASE}/api/cad-registry/cache/repair`, { method: 'POST' });
  return parseResponse(response);
}

export async function repairRegistryItemCache(itemId: string) {
  const response = await fetch(`${API_BASE}/api/cad-registry/items/${itemId}/cache/repair`, { method: 'POST' });
  return parseResponse(response);
}

export async function verifyRegistryAudit() {
  const response = await fetch(`${API_BASE}/api/cad-registry/audit/verify`);
  return parseResponse(response);
}

export async function getRegistryAuditReport() {
  const response = await fetch(`${API_BASE}/api/cad-registry/audit/report`);
  return parseResponse(response);
}

export function downloadRegistryAuditReport() {
  return `${API_BASE}/api/cad-registry/audit/report/download`;
}

export async function exportCadRegistry() {
  const response = await fetch(`${API_BASE}/api/cad-registry/export`);
  return parseResponse(response);
}

export async function importCadRegistry(payload: Record<string, any>) {
  const response = await fetch(`${API_BASE}/api/cad-registry/import`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return parseResponse(response);
}
