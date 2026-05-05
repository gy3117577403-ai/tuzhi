const API_BASE = import.meta.env.VITE_API_BASE_URL || '';

export type ConnectorInputType = 'text' | 'drawing' | 'photo';

export type AiApiStatus = {
  configured: boolean;
  provider: string;
  base_url_set: boolean;
  api_key_set: boolean;
  model: string;
  key_preview: string;
};

export type AiTestResponse = {
  ok: boolean;
  extracted: Record<string, unknown>;
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
  part_match?: {
    match_level?: 'exact' | 'weak' | 'near_miss' | 'none' | string;
    query_part_number?: string;
    matched_part_number?: string;
    normalized_query?: string;
    normalized_matched?: string;
    reason?: string;
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
    return Promise.reject(new Error(parsed.detail || text || `HTTP ${response.status}`));
  } catch {
    throw new Error(text || `HTTP ${response.status}`);
  }
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
): Promise<ConnectorJob> {
  const response = await fetch(`${API_BASE}/api/connector-cad/jobs/from-selected-image`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ search_id: searchId, candidate_id: candidateId, query }),
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
