import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertTriangle,
  Box,
  Camera,
  CheckCircle2,
  Code,
  Cpu,
  Database,
  Download,
  FileText,
  Fingerprint,
  Layers,
  Loader2,
  RefreshCw,
  ShieldCheck,
  Upload,
  X,
} from 'lucide-react';
import ModelViewer from './components/ModelViewer';
import {
  confirmConnectorParams,
  createCadRegistryItem,
  createFileConnectorJob,
  createJobFromManualImageUrl,
  createJobFromSelectedImage,
  createTextConnectorJob,
  checkRegistryCache,
  checkRegistryItemCache,
  deprecateCadRegistryItem,
  downloadRegistryAuditReport,
  exportCadRegistry,
  fileUrl,
  getAiApiStatus,
  getCadRegistryCache,
  getCadRegistryItemHistory,
  getCadRegistryStats,
  getRegistryAuditReport,
  importCadRegistry,
  listCadRegistryItems,
  pollConnectorJob,
  postAiTest,
  repairRegistryCache,
  repairRegistryItemCache,
  refreshCadRegistryCache,
  reviewCadRegistryItem,
  searchConnectorImages,
  verifyRegistryAudit,
} from './api/connectorCad';

const WORKFLOW_STATUS = {
  idle: { label: '待输入', tone: 'neutral' },
  uploading: { label: '上传中', tone: 'active' },
  generating: { label: '生成中', tone: 'active' },
  needs_confirmation: { label: '预览版 / 待确认', tone: 'warning' },
  completed: { label: '确认版已生成', tone: 'success' },
  failed: { label: '失败', tone: 'danger' },
};

const tabs = [
  { id: 'text', label: '文本描述', icon: FileText },
  { id: 'drawing', label: '二维图纸', icon: Layers },
  { id: 'photo', label: '3D 扫描', icon: Camera },
];

const CONFIRM_FIELDS = [
  ['body_length_mm', '总长', 'overall_length'],
  ['body_width_mm', '总宽', 'overall_width'],
  ['body_height_mm', '总高', 'overall_height'],
  ['pitch_mm', '针距', 'pin_pitch'],
  ['positions', '针位数', 'pin_count'],
  ['cavity_diameter_mm', '孔腔直径', 'pin_diameter'],
  ['mounting_hole_spacing_mm', '安装孔距', 'mount_hole_spacing'],
  ['mounting_hole_diameter_mm', '安装孔直径', 'mount_hole_diameter'],
];

export default function App() {
  const [activeTab, setActiveTab] = useState('text');
  const [inputText, setInputText] = useState('');
  const [file, setFile] = useState(null);
  const [job, setJob] = useState(null);
  const [status, setStatus] = useState('idle');
  const [error, setError] = useState('');
  const [confirmValues, setConfirmValues] = useState({});
  const [unknownNotes, setUnknownNotes] = useState({});
  const [confirmNotes, setConfirmNotes] = useState('用户已确认关键尺寸');
  const [showRegistry, setShowRegistry] = useState(false);
  const fileInputRef = useRef(null);

  const [aiApiStatus, setAiApiStatus] = useState(null);
  const [aiTestFailed, setAiTestFailed] = useState(false);
  const [aiTestBusy, setAiTestBusy] = useState(false);
  const [aiTestMessage, setAiTestMessage] = useState('');
  const [imageSearch, setImageSearch] = useState(null);
  const [imageSearchBusy, setImageSearchBusy] = useState(false);
  const [selectedCandidateId, setSelectedCandidateId] = useState('');
  const [manualImageUrl, setManualImageUrl] = useState('');
  const [manualSourceUrl, setManualSourceUrl] = useState('');

  const canGenerate = activeTab === 'text' ? inputText.trim().length > 0 : Boolean(file);
  const isBusy = status === 'uploading' || status === 'generating';

  useEffect(() => {
    let cancelled = false;
    getAiApiStatus()
      .then((data) => {
        if (!cancelled) {
          setAiApiStatus(data);
          setAiTestFailed(false);
        }
      })
      .catch(() => {
        if (!cancelled) setAiApiStatus({ configured: false, model: '', key_preview: '' });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const handleAiTest = async () => {
    const sample = inputText.trim() || 'TE 282104-1 2 pin automotive connector pitch 6.0mm';
    setAiTestBusy(true);
    setAiTestMessage('');
    try {
      const res = await postAiTest(sample);
      setAiTestFailed(!res.ok);
      setAiTestMessage(res.ok ? 'AI 測試解析成功' : 'AI 測試解析失敗（仍可使用本地預設參數生成）');
    } catch (err) {
      setAiTestFailed(true);
      setAiTestMessage(err.message || 'AI 測試請求失敗');
    } finally {
      setAiTestBusy(false);
    }
  };

  useEffect(() => {
    if (!job?.params?.dimensions) return;
    const next = {};
    for (const [fieldKey, , dimensionKey] of CONFIRM_FIELDS) {
      const value = job.params.dimensions[dimensionKey]?.value;
      if (value !== undefined) next[fieldKey] = value;
    }
    setConfirmValues(next);
    setUnknownNotes({});
  }, [job?.job_id]);

  const handleGenerate = async () => {
    if (!canGenerate || isBusy) return;
    setError('');
    setJob(null);
    setStatus(activeTab === 'text' ? 'generating' : 'uploading');
    try {
      const created = activeTab === 'text'
        ? await createTextConnectorJob(inputText.trim())
        : await createFileConnectorJob(activeTab, file);
      setJob(created);
      setStatus('generating');
      const finalJob = await pollConnectorJob(created.job_id);
      setJob(finalJob);
      setStatus(finalJob.status === 'failed' ? 'failed' : finalJob.status);
      if (finalJob.status === 'failed') setError(finalJob.error || '生成失败');
    } catch (err) {
      setStatus('failed');
      setError(err.message || '生成失败');
    }
  };

  const finishCreatedJob = async (created) => {
    setJob(created);
    setStatus('generating');
    const finalJob = await pollConnectorJob(created.job_id);
    setJob(finalJob);
    setStatus(finalJob.status === 'failed' ? 'failed' : finalJob.status);
    if (finalJob.status === 'failed') setError(finalJob.error || '鐢熸垚澶辫触');
  };

  const handleImageSearch = async () => {
    const query = inputText.trim();
    if (!query || imageSearchBusy || isBusy) return;
    setError('');
    setImageSearch(null);
    setImageSearchBusy(true);
    try {
      const result = await searchConnectorImages(query, 8);
      setImageSearch(result);
    } catch (err) {
      setError(err.message || '图片搜索失败');
    } finally {
      setImageSearchBusy(false);
    }
  };

  const handleCreateFromCandidate = async (candidate) => {
    if (!imageSearch?.search_id || !candidate?.id || isBusy) return;
    const generationRisk = candidate.generation_risk || {};
    const requiresConfirmation = Boolean(generationRisk.requires_confirmation);
    const acceptedRiskCode = generationRisk.confirmation_code || '';
    const acceptPartMismatchRisk = acceptedRiskCode === 'near_miss_part_number';
    if (requiresConfirmation) {
      const confirmed = window.confirm(`${riskPromptText(acceptedRiskCode)}\n\n${generationRisk.recommended_action || '请人工核对后再生成。'}\n\n确认继续？`);
      if (!confirmed) return;
    }
    setError('');
    setSelectedCandidateId(candidate.id);
    setStatus('generating');
    try {
      const created = await createJobFromSelectedImage(
        imageSearch.search_id,
        candidate.id,
        inputText.trim(),
        acceptPartMismatchRisk,
        requiresConfirmation,
        acceptedRiskCode,
      );
      await finishCreatedJob(created);
    } catch (err) {
      setStatus('failed');
      setError(err.message || '选择图片生成失败');
    } finally {
      setSelectedCandidateId('');
    }
  };

  const handleManualImageGenerate = async () => {
    const query = inputText.trim();
    const imageUrl = manualImageUrl.trim();
    if (!query || !imageUrl || isBusy) return;
    setError('');
    setSelectedCandidateId('manual_image');
    setStatus('generating');
    try {
      const created = await createJobFromManualImageUrl(query, imageUrl, manualSourceUrl.trim(), '手动图片 URL');
      await finishCreatedJob(created);
    } catch (err) {
      setStatus('failed');
      setError(err.message || '手动图片 URL 生成失败');
    } finally {
      setSelectedCandidateId('');
    }
  };

  const handleConfirm = async () => {
    if (!job || isBusy) return;
    setError('');
    setStatus('generating');
    try {
      const acceptedUnknowns = (job.params?.unknown_fields || []).filter((field) => (unknownNotes[field] || '').trim());
      const confirmed = {};
      for (const [key] of CONFIRM_FIELDS) {
        const value = Number(confirmValues[key]);
        if (Number.isFinite(value)) confirmed[key] = value;
      }
      const updated = await confirmConnectorParams(job.job_id, {
        confirmed_params: confirmed,
        accepted_unknowns: acceptedUnknowns,
        notes: confirmNotes,
      });
      const finalJob = await pollConnectorJob(updated.job_id);
      setJob(finalJob);
      setStatus(finalJob.status);
      if (finalJob.status === 'failed') setError(finalJob.error || '重新生成失败');
    } catch (err) {
      setStatus('failed');
      setError(err.message || '重新生成失败');
    }
  };

  const reset = () => {
    setJob(null);
    setFile(null);
    setInputText('');
    setError('');
    setImageSearch(null);
    setManualImageUrl('');
    setManualSourceUrl('');
    setStatus('idle');
  };

  return (
    <div className="app-shell">
      <aside className="rail" aria-label="主工具栏">
        <button className="rail-primary" title="SmartCAD"><Box size={18} /></button>
        <div className="rail-line" />
        <button className="rail-tool active" title="生成"><FileText size={18} /></button>
        <button className="rail-tool" title="模型"><Layers size={18} /></button>
        <button className="rail-tool" title="导出"><Download size={18} /></button>
      </aside>

      <header className="topbar">
        <div className="brand">
          <span>SmartCAD 连接器生成</span>
          <span className="version">MVP</span>
          <StatusBadge status={status} />
        </div>
        <div className="top-actions">
          <div className="ai-toolbar" title={aiApiStatus?.key_preview ? `Key 預覽：${aiApiStatus.key_preview}` : ''}>
            <Cpu size={14} aria-hidden />
            <span>
              AI API：
              {!aiApiStatus ? '讀取中…' : aiTestFailed ? '測試失敗' : aiApiStatus.configured ? '已配置' : '未配置'}
            </span>
            {aiApiStatus?.configured && aiApiStatus.model ? (
              <span className="ai-model" title={aiApiStatus.model}>{aiApiStatus.model}</span>
            ) : null}
            <button type="button" className="small-action" disabled={aiTestBusy} onClick={handleAiTest}>
              {aiTestBusy ? <Loader2 className="spin" size={12} /> : null}
              測試 AI 解析
            </button>
          </div>
          {aiTestMessage ? <span className="ai-test-msg">{aiTestMessage}</span> : null}
          <button className="docs-link button-link" onClick={() => setShowRegistry(true)}>
            <Database size={14} />
            CAD 来源库
          </button>
          <a className="docs-link" href="/docs" target="_blank" rel="noreferrer">API 文档</a>
        </div>
      </header>

      {showRegistry && <RegistryPanel onClose={() => setShowRegistry(false)} />}

      {!job ? (
        <main className="center-stage">
          <section className="input-panel">
            <div className="tabs">
              {tabs.map((tab) => (
                <button
                  key={tab.id}
                  className={activeTab === tab.id ? 'tab active' : 'tab'}
                  onClick={() => {
                    setActiveTab(tab.id);
                    setError('');
                    if (!isBusy) setStatus('idle');
                  }}
                >
                  <tab.icon size={15} />
                  <span>{tab.label}</span>
                </button>
              ))}
            </div>
            {activeTab === 'text' ? (
              <>
                <input
                  className="hero-input"
                  value={inputText}
                  onChange={(event) => {
                    setInputText(event.target.value);
                    setImageSearch(null);
                    if (!isBusy) setStatus('idle');
                  }}
                  placeholder="输入连接器型号或描述"
                  autoFocus
                />
                <div className="examples">
                  <span>示例</span>
                  {['1-968970-1', 'TE 282104-1', 'LOCAL SAMPLE STEP', 'CACHE SAMPLE STEP'].map((item) => (
                    <button key={item} onClick={() => { setInputText(item); setImageSearch(null); }}>{item}</button>
                  ))}
                </div>
              </>
            ) : (
              <FileDropZone file={file} fileInputRef={fileInputRef} setFile={setFile} setStatus={setStatus} />
            )}
            <button className="generate-button" disabled={!canGenerate || isBusy} onClick={handleGenerate}>
              {isBusy ? <Loader2 className="spin" size={17} /> : <Box size={17} />}
              <span>{isBusy ? WORKFLOW_STATUS[status].label : '生成 CAD 文件'}</span>
            </button>
            {activeTab === 'text' ? (
              <>
                <button
                  className="image-search-button"
                  disabled={!inputText.trim() || imageSearchBusy || isBusy}
                  onClick={handleImageSearch}
                >
                  {imageSearchBusy ? <Loader2 className="spin" size={16} /> : <Camera size={16} />}
                  <span>{imageSearchBusy ? '搜索图片中...' : '搜索图片生成相似 CAD'}</span>
                </button>
                <ImageSearchPanel
                  search={imageSearch}
                  busy={imageSearchBusy}
                  selectedCandidateId={selectedCandidateId}
                  manualImageUrl={manualImageUrl}
                  manualSourceUrl={manualSourceUrl}
                  setManualImageUrl={setManualImageUrl}
                  setManualSourceUrl={setManualSourceUrl}
                  onSelect={handleCreateFromCandidate}
                  onManualGenerate={handleManualImageGenerate}
                  canManualGenerate={Boolean(inputText.trim() && manualImageUrl.trim() && !isBusy)}
                />
              </>
            ) : null}
            {isBusy && activeTab === 'text' && (
              <p className="generating-hint">
                正在搜尋相關產品圖 → 排序可信圖片 → 提取外觀特徵 → 生成視覺近似 CAD（若未設定圖片搜尋 API，將自動回退既有流程）。
              </p>
            )}
            {error && <ErrorMessage error={error} />}
          </section>
        </main>
      ) : (
        <main className="workspace">
          <section className="viewer-card">
            <div className="viewer-heading">
              <div>
                <h1>{job.params?.title || job.params?.part_number || '通用矩形连接器'}</h1>
                <div className="viewer-origin-row">
                  <OriginPill job={job} />
                  <p className="viewer-sub">{modelSourceSubtitle(job)}</p>
                </div>
              </div>
              <button className="icon-button" onClick={reset} title="关闭工作区"><X size={16} /></button>
            </div>
            <ModelViewer
              jobId={job.job_id}
              stlUrl={job.files?.model_stl}
              previewBaseColor={job.params?.preview_style?.base_color}
            />
            <FlatCadPanel job={job} />
          </section>

          <aside className="inspector">
            <div className="inspector-title">
              <span>属性面板</span>
              <button className="icon-button" onClick={handleGenerate} disabled={isBusy} title="重新生成">
                <RefreshCw size={15} className={isBusy ? 'spin' : ''} />
              </button>
            </div>
            {(job.params?.model_origin === 'image_search_approximated'
              || job.params?.model_origin === 'image_upload_approximated') && (
              <div className="image-search-banner" role="alert">
                <AlertTriangle size={17} />
                <span>
                  {job.params?.model_origin === 'image_upload_approximated'
                    ? '图片驱动外观近似 CAD。依据上传图片生成，仅用于外观预览，不代表原厂 CAD，不可直接作为制造尺寸依据。'
                    : '圖片搜尋驅動外觀近似 CAD。依網路圖片生成，僅供外觀預覽，不代表原廠 CAD，不可直接作為製造尺寸依據。'}
                </span>
              </div>
            )}
            <SourcePanel job={job} />
            <ImageSearchSourcePanel job={job} />
            <AppearanceDetailPanel job={job} />
            <AiExtractionPanel job={job} />
            <AuditPanel job={job} />
            <StatusPanel status={status} warning={job.warning || job.params?.warning} />
            {status === 'completed' && <SuccessMessage job={job} />}
            {status === 'failed' && error && <ErrorMessage error={error} />}
            {job.params?.model_origin !== 'official_cad' && (
              <>
                <div className="section-label">参数表</div>
                <ParamGrid dimensions={job.params?.dimensions || {}} />
                {status === 'needs_confirmation' && (
                  <ConfirmPanel
                    job={job}
                    confirmValues={confirmValues}
                    setConfirmValues={setConfirmValues}
                    unknownNotes={unknownNotes}
                    setUnknownNotes={setUnknownNotes}
                    confirmNotes={confirmNotes}
                    setConfirmNotes={setConfirmNotes}
                    isBusy={isBusy}
                    onConfirm={handleConfirm}
                  />
                )}
              </>
            )}
            <DownloadPanel job={job} />
          </aside>
        </main>
      )}
    </div>
  );
}

function FileDropZone({ file, fileInputRef, setFile, setStatus }) {
  const updateFile = (nextFile) => {
    setFile(nextFile);
    setStatus('idle');
  };
  return (
    <div
      className="drop-zone"
      onClick={() => fileInputRef.current?.click()}
      onDragOver={(event) => event.preventDefault()}
      onDrop={(event) => {
        event.preventDefault();
        updateFile(event.dataTransfer.files?.[0] || null);
      }}
    >
      <Upload size={22} />
      <strong>{file ? file.name : '上传图纸、PDF、DXF、图片或扫描图'}</strong>
      <span>{file ? `${Math.ceil(file.size / 1024)} KB` : '上传入口使用 FormData 发送到后端'}</span>
      <input
        ref={fileInputRef}
        type="file"
        hidden
        accept=".pdf,.dxf,.png,.jpg,.jpeg,.webp,.bmp,.tif,.tiff"
        onChange={(event) => updateFile(event.target.files?.[0] || null)}
      />
    </div>
  );
}

function ImageSearchPanel({
  search,
  busy,
  selectedCandidateId,
  manualImageUrl,
  manualSourceUrl,
  setManualImageUrl,
  setManualSourceUrl,
  onSelect,
  onManualGenerate,
  canManualGenerate,
}) {
  const [failedImages, setFailedImages] = useState({});
  if (busy) {
    return (
      <div className="image-search-panel loading">
        <Loader2 className="spin" size={18} />
        <span>正在搜索候选图片...</span>
      </div>
    );
  }
  if (!search) return null;
  const results = search.results || [];
  const matchSummary = search.match_summary || {};
  const nearMissResults = results.filter((candidate) => candidate.part_match?.match_level === 'near_miss');
  const primaryResults = results.filter((candidate) => candidate.part_match?.match_level !== 'near_miss');
  const notConfigured = search.status === 'not_configured';
  const failed = search.status === 'failed';
  const showManualFallback = notConfigured || failed;
  const renderCandidate = (candidate) => {
    const partMatch = candidate.part_match || {};
    const evidence = candidate.match_evidence || {};
    const generationRisk = candidate.generation_risk || {};
    const matchLevel = partMatch.match_level || 'none';
    const evidenceLevel = evidence.evidence_level || 'unknown';
    const requiresConfirmation = Boolean(generationRisk.requires_confirmation);
    const isNearMiss = matchLevel === 'near_miss';
    const exactLowEvidence = matchLevel === 'exact' && evidenceLevel === 'low';
    return (
      <article key={candidate.id} className={`candidate-card match-${matchLevel} evidence-${evidenceLevel}`}>
        <div className="candidate-thumb">
          {failedImages[candidate.id] ? (
            <div className="thumb-fallback">缩略图加载失败，但仍可尝试使用原图 URL</div>
          ) : (
            <img
              src={candidate.thumbnail_url || candidate.image_url}
              alt={candidate.title || 'candidate connector'}
              onError={() => setFailedImages((current) => ({ ...current, [candidate.id]: true }))}
            />
          )}
        </div>
        <div className="candidate-body">
          <div className="candidate-title-row">
            <strong>{candidate.title || 'Untitled candidate'}</strong>
            <PartMatchBadge level={matchLevel} />
            <EvidenceBadge level={evidenceLevel} />
          </div>
          <span>{candidate.domain || domainFromUrl(candidate.source_url) || 'unknown source'}</span>
          <span>provider: {candidate.provider || search.provider || 'unknown'}</span>
          <span>search_round: {candidate.search_round || 'initial'}</span>
          <span>score: {candidate.score ?? 'n/a'}</span>
          <span>evidence_score: {evidence.evidence_score ?? 'n/a'}</span>
          {partMatch.matched_part_number ? <span>matched_part_number: {partMatch.matched_part_number}</span> : null}
          {partMatch.reason ? <p className={`part-match-reason ${isNearMiss ? 'danger' : ''}`}>{partMatch.reason}</p> : null}
          <div className="evidence-flags">
            <span>title exact: {formatBool(evidence.title_has_exact)}</span>
            <span>source exact: {formatBool(evidence.source_url_has_exact)}</span>
            <span>image exact: {formatBool(evidence.image_url_has_exact)}</span>
            <span>thumb exact: {formatBool(evidence.thumbnail_url_has_exact)}</span>
            <span>trusted domain: {formatBool(evidence.domain_trusted)}</span>
            <span>probe ok: {formatBool(evidence.download_probe_ok)}</span>
          </div>
          {Array.isArray(evidence.warnings) && evidence.warnings.length ? (
            <div className={`evidence-warning ${evidenceLevel === 'low' ? 'danger' : ''}`}>{evidence.warnings.join('；')}</div>
          ) : null}
          <div className={`generation-risk ${requiresConfirmation ? 'confirm' : generationRisk.risk_level === 'notice' ? 'notice' : ''}`}>
            <span>risk_level: {generationRisk.risk_level || 'none'}</span>
            <span>confirmation_code: {generationRisk.confirmation_code || 'none'}</span>
            {Array.isArray(generationRisk.risk_reasons) && generationRisk.risk_reasons.length ? (
              <p>{generationRisk.risk_reasons.join('；')}</p>
            ) : null}
            {generationRisk.recommended_action ? <p>{generationRisk.recommended_action}</p> : null}
          </div>
          <p>{candidate.rank_reason || 'Connector-like visual candidate'}</p>
          {candidate.source_url ? (
            <a href={candidate.source_url} target="_blank" rel="noreferrer">source_url</a>
          ) : null}
        </div>
        {isNearMiss ? (
          <div className="candidate-near-alert">
            该候选图可能属于相近料号，不一定是当前输入型号，生成结果仅供外观参考。
          </div>
        ) : null}
        {exactLowEvidence ? (
          <div className="candidate-near-alert">
            完整料号命中，但图片证据较弱，请人工核对。
          </div>
        ) : null}
        {generationRisk.confirmation_code === 'no_part_number_match' ? (
          <div className="candidate-near-alert">图片未匹配当前料号，请谨慎使用。</div>
        ) : null}
        <button
          className={`candidate-select ${requiresConfirmation ? 'danger' : ''}`}
          onClick={() => onSelect(candidate)}
          disabled={Boolean(selectedCandidateId)}
        >
          {selectedCandidateId === candidate.id ? <Loader2 className="spin" size={14} /> : <Camera size={14} />}
          <span>{requiresConfirmation ? '确认风险并生成 CAD' : '选择此图生成 CAD'}</span>
        </button>
      </article>
    );
  };
  return (
    <div className="image-search-panel">
      <div className="image-search-head">
        <div>
          <strong>{notConfigured ? '图片搜索未配置' : '候选图片'}</strong>
          <span>{search.provider || 'unknown'} / {search.status || 'unknown'} / {results.length} results</span>
          {search.expanded_query ? <span>expanded_query: {search.expanded_query}</span> : null}
        </div>
        {search.search_id ? <code>{search.search_id}</code> : null}
      </div>
      <div className="image-source-alert">
        该模型由搜索图片生成，仅为外观近似 CAD，不代表原厂 CAD，不可作为制造尺寸依据。
      </div>
      <div className="match-summary-row">
        <span className="summary-chip exact">完整匹配 {matchSummary.exact ?? 0}</span>
        <span className="summary-chip weak">弱匹配 {matchSummary.weak ?? 0}</span>
        <span className="summary-chip near">相近料号 {matchSummary.near_miss ?? 0}</span>
        <span className="summary-chip none">未匹配 {matchSummary.none ?? 0}</span>
      </div>
      {matchSummary.has_exact === false ? (
        <div className="candidate-near-alert">
          未找到完整料号匹配图片，当前结果可能是相近料号，请谨慎选择。
        </div>
      ) : null}
      {Array.isArray(search.refined_searches) && search.refined_searches.length ? (
        <div className="refined-searches">
          <strong>精确料号二次搜索</strong>
          {search.refined_searches.map((item) => (
            <span key={`${item.query}-${item.status}`}>{item.query} / {item.status} / {item.results_count} results</span>
          ))}
        </div>
      ) : null}
      {Array.isArray(search.warnings) && search.warnings.length ? (
        <div className="image-search-warnings">{search.warnings.join('；')}</div>
      ) : null}
      {showManualFallback ? (
        <ManualImageUrlForm
          imageUrl={manualImageUrl}
          sourceUrl={manualSourceUrl}
          setImageUrl={setManualImageUrl}
          setSourceUrl={setManualSourceUrl}
          onGenerate={onManualGenerate}
          canGenerate={canManualGenerate}
          busy={selectedCandidateId === 'manual_image'}
        />
      ) : null}
      {results.length ? (
        <>
          {primaryResults.length ? <div className="candidate-grid">{primaryResults.map(renderCandidate)}</div> : null}
          {nearMissResults.length ? (
            <details className="near-miss-section">
              <summary>相近料号风险候选（{nearMissResults.length}）</summary>
              <div className="candidate-grid">{nearMissResults.map(renderCandidate)}</div>
            </details>
          ) : null}
        </>
      ) : !notConfigured ? (
        <div className="empty-panel">没有返回候选图片，可稍后重试或检查图片搜索配置。</div>
      ) : null}
    </div>
  );
}

function ManualImageUrlForm({
  imageUrl,
  sourceUrl,
  setImageUrl,
  setSourceUrl,
  onGenerate,
  canGenerate,
  busy,
}) {
  return (
    <div className="manual-image-form">
      <label>
        <span>手动图片 URL</span>
        <input
          value={imageUrl}
          onChange={(event) => setImageUrl(event.target.value)}
          placeholder="https://example.com/connector-photo.png"
        />
      </label>
      <label>
        <span>来源链接（可选）</span>
        <input
          value={sourceUrl}
          onChange={(event) => setSourceUrl(event.target.value)}
          placeholder="https://example.com/product-page"
        />
      </label>
      <button className="candidate-select manual" disabled={!canGenerate || busy} onClick={onGenerate}>
        {busy ? <Loader2 className="spin" size={14} /> : <Camera size={14} />}
        <span>使用手动图片 URL 生成 CAD</span>
      </button>
    </div>
  );
}

function PartMatchBadge({ level }) {
  const labels = {
    exact: '完整料号匹配',
    weak: '弱匹配',
    near_miss: '相近料号风险',
    none: '未匹配料号',
  };
  const normalized = labels[level] ? level : 'none';
  return <span className={`part-match-badge ${normalized}`}>{labels[normalized]}</span>;
}

function EvidenceBadge({ level }) {
  const labels = {
    high: '高可信',
    medium: '中等可信',
    low: '低可信，需核对',
    unknown: '未知可信度',
  };
  const normalized = labels[level] ? level : 'unknown';
  return <span className={`evidence-badge ${normalized}`}>{labels[normalized]}</span>;
}

function formatBool(value) {
  if (value === true) return 'yes';
  if (value === false) return 'no';
  return 'unknown';
}

function riskPromptText(code) {
  const prompts = {
    low_evidence_exact: '完整料号命中，但图片证据较弱，需人工核对。',
    unknown_evidence_exact: '完整料号命中，但图片证据未知，需人工核对。',
    low_evidence_weak: '弱料号匹配且证据较弱，可能不是当前型号。',
    near_miss_part_number: '相近料号风险，可能不是当前型号。',
    no_part_number_match: '图片未匹配当前料号，请谨慎使用。',
  };
  return prompts[code] || '该候选图需要确认风险后才能生成。';
}

function StatusBadge({ status }) {
  const config = WORKFLOW_STATUS[status] || WORKFLOW_STATUS.idle;
  return <span className={`status-badge ${config.tone}`}>{config.label}</span>;
}

function OriginPill({ job }) {
  const o = job?.params?.model_origin;
  const label = appearanceOriginLabel(o);
  const tone =
    o === 'official_cad' ? 'origin-official'
      : o === 'series_template' ? 'origin-series'
        : o === 'image_approximated' ? 'origin-image'
          : o === 'image_search_approximated' || o === 'image_upload_approximated' ? 'origin-image'
            : o === 'third_party_cad' ? 'origin-third'
              : 'origin-generic';
  return <span className={`origin-pill ${tone}`}>{label}</span>;
}

function appearanceOriginLabel(origin) {
  if (origin === 'official_cad') return '官方 CAD';
  if (origin === 'series_template') return '系列模板近似模型';
  if (origin === 'image_approximated') return '图片驱动外观近似模型';
  if (origin === 'image_search_approximated') return '搜索图片驱动外观近似 CAD';
  if (origin === 'image_upload_approximated') return '上傳圖片驅動外觀近似';
  if (origin === 'generic_mvp') return '通用参数化白模';
  if (origin === 'third_party_cad') return '第三方 CAD';
  if (origin === 'parametric_mvp') return '通用参数化近似（旧）';
  return '工程近似模型';
}

function AppearanceDetailPanel({ job }) {
  const p = job?.params || {};
  const ap = p.appearance_pipeline;
  if (!ap?.used && !p.template_name) return null;
  const vm = p.visual_match || {};
  const imgSum = p.image_feature_summary;
  const iff = imgSum?.feature_flags || {};
  const uploadFeat = p.model_origin === 'image_upload_approximated';
  return (
    <>
      <div className="section-label">外形与模板</div>
      <div className="audit-card appearance-detail-card">
        {uploadFeat && imgSum && (
          <>
            <div className="section-label subtle">上傳圖片特徵</div>
            <AuditRow label="檔名" value={p.uploaded_file_name || '—'} mono />
            <AuditRow label="主色（dominant_color）" value={String(imgSum.dominant_color ?? '—')} />
            <AuditRow label="正面佈局（front_face_layout）" value={JSON.stringify(imgSum.front_face_layout || {})} />
            <AuditRow label="特徵旗標（feature_flags）" value={JSON.stringify(iff)} />
            {Array.isArray(imgSum.warnings) && imgSum.warnings.length > 0 ? (
              <AuditRow label="影像警告" value={imgSum.warnings.join('；')} />
            ) : null}
            {Array.isArray(p.visual_recipe?.warnings) && p.visual_recipe.warnings.length > 0 ? (
              <AuditRow label="配方警告" value={p.visual_recipe.warnings.join('；')} />
            ) : null}
          </>
        )}
        <AuditRow label="模板名称" value={p.template_name || ap?.template_name || '—'} />
        <AuditRow label="外观置信度" value={p.appearance_confidence || '—'} />
        <AuditRow label="匹配来源" value={vm.selection_reason || ap?.selection_reason || '—'} />
        <AuditRow label="预览色（示意）" value={p.preview_style?.base_color || ap?.preview_color || '—'} />
        <AuditRow label="几何基础" value={p.geometry_basis || '—'} />
        <AuditRow label="制造精度等级" value={p.manufacturing_accuracy || '—'} />
        {p.image_search_context?.search && (
          <>
            <div className="section-label subtle">圖片搜尋</div>
            <pre className="ai-json-preview">{JSON.stringify(p.image_search_context.search, null, 2).slice(0, 900)}</pre>
          </>
        )}
        {p.visual_recipe && (
          <>
            <div className="section-label subtle">視覺配方（visual_recipe）</div>
            <pre className="ai-json-preview">{JSON.stringify(p.visual_recipe, null, 2).slice(0, 1400)}{JSON.stringify(p.visual_recipe, null, 2).length > 1400 ? '…' : ''}</pre>
          </>
        )}
        {p.model_origin === 'series_template' && (
          <div className="appearance-warn">该模型依据连接器系列模板生成，外形近似，非原厂精确 CAD。</div>
        )}
        {p.model_origin === 'image_approximated' && (
          <div className="appearance-warn appearance-warn-strong">该模型依据图片外观近似生成，仅用于形态预览，不代表制造级精确 CAD。</div>
        )}
        {(p.model_origin === 'image_search_approximated' || p.model_origin === 'image_upload_approximated') && (
          <div className="appearance-warn appearance-warn-strong">
            視覺形狀語法（非逐型號模板庫）生成的外觀代理模型；尺寸為工程假設，須人工確認。
          </div>
        )}
        {p.image_fallback_warning && (
          <div className="appearance-warn">{p.image_fallback_warning}</div>
        )}
        {imgSum && !uploadFeat && (
          <>
            <div className="section-label subtle">图像特征摘要</div>
            <pre className="ai-json-preview">{JSON.stringify(imgSum, null, 2).slice(0, 1200)}{JSON.stringify(imgSum, null, 2).length > 1200 ? '…' : ''}</pre>
          </>
        )}
        {p.vision_report_summary && (
          <>
            <div className="section-label subtle">视觉理解（AI）</div>
            <pre className="ai-json-preview">{JSON.stringify(p.vision_report_summary, null, 2).slice(0, 800)}</pre>
          </>
        )}
      </div>
    </>
  );
}

function AiExtractionPanel({ job }) {
  const ai = job?.params?.ai_extraction;
  const dimensions = job?.params?.dimensions || {};
  if (!ai) return null;
  const fromAi = Object.entries(dimensions)
    .filter(([, v]) => v?.source === 'ai_extracted')
    .map(([k]) => k);
  const extracted = ai.extracted || {};
  const pending = (job.params?.unknown_fields || []).filter(Boolean);
  return (
    <>
      <div className="section-label">AI 解析</div>
      <div className="audit-card ai-card">
        <div className="audit-head">
          <Cpu size={15} />
          <strong>狀態：{ai.status || '—'}{ai.enabled === false ? '（未啟用）' : ''}</strong>
        </div>
        <AuditRow label="模型" value={ai.model || '—'} />
        <AuditRow label="服務商" value={ai.provider || '—'} />
        {ai.error ? <AuditRow label="錯誤" value={ai.error} /> : null}
        <div className="section-label subtle">AI 結構化提取</div>
        <pre className="ai-json-preview">{JSON.stringify(extracted, null, 2)}</pre>
        <div className="section-label subtle">標記為 ai_extracted 的參數</div>
        <div className="mono-list">{fromAi.length ? fromAi.join(', ') : '（無）'}</div>
        <div className="section-label subtle">仍需確認 / 未知欄位</div>
        <div className="mono-list">{pending.length ? pending.join(', ') : '（無）'}</div>
      </div>
    </>
  );
}

function SourcePanel({ job }) {
  const params = job.params || {};
  const uploadVisual = params.model_origin === 'image_upload_approximated';
  return (
    <div className={`source-card ${dangerSource(job) ? 'danger-source' : ''}`}>
      <strong>{modelSourceTitle(job)}</strong>
      <span>{modelSourceSubtitle(job)}</span>
      {uploadVisual && (
        <>
          <em>圖片驅動外觀近似 CAD</em>
          <span className="source-upload-note">
            依據上傳圖片生成，僅用於外觀預覽，不代表原廠 CAD，不可直接作為製造尺寸依據。
          </span>
          {params.uploaded_file_name ? (
            <small className="upload-filename">已選／上傳檔名（伺服端）：{params.uploaded_file_name}</small>
          ) : null}
        </>
      )}
      {params.source_type === 'official_candidate' && <em>检测到待审核 CAD 来源，但当前未用于生成。</em>}
      {(params.model_origin === 'parametric_mvp' || params.model_origin === 'generic_mvp') && (
        <em>参数化工程近似模型，不是原厂 CAD。</em>
      )}
      {params.model_origin === 'series_template' && <em>系列模板外形近似，不等同原厂精确几何。</em>}
      {params.model_origin === 'image_approximated' && <em>依据图像的外观近似，非制造级精确模型。</em>}
      {params.selection_reason && <small>选择策略：{params.selection_reason}</small>}
    </div>
  );
}

function ImageSearchSourcePanel({ job }) {
  const params = job.params || {};
  if (params.model_origin !== 'image_search_approximated') return null;
  const imageSearch = params.image_search || {};
  const context = params.image_search_context || {};
  const selected = imageSearch.selected || context.rank?.selected || {};
  const search = context.search || {};
  const recipe = params.visual_recipe || {};
  const imageUrl = selected.image_url || selected.thumbnail_url || '';
  const sourceUrl = selected.source_url || params.source_url || '';
  const recipeSummary = {
    color: recipe.color,
    confidence: recipe.confidence,
    cavity_array: recipe.cavity_array,
    front_shroud: recipe.front_shroud,
    top_features: recipe.top_features,
    side_features: recipe.side_features,
  };
  return (
    <>
      <div className="section-label">搜索图片来源</div>
      <div className="audit-card image-source-card">
        <div className="image-source-alert">
          该模型由搜索图片生成，仅为外观近似 CAD，不代表原厂 CAD，不可作为制造尺寸依据。
        </div>
        {imageUrl ? (
          <img className="selected-image-preview" src={imageUrl} alt={selected.title || 'selected connector reference'} />
        ) : null}
        <AuditRow label="image_url" value={imageUrl || '未记录'} mono />
        <AuditRow label="source_url" value={sourceUrl || '未记录'} mono />
        <AuditRow label="search_id" value={search.search_id || imageSearch.search_id || '未记录'} mono />
        <AuditRow label="selected_candidate_id" value={selected.id || imageSearch.selected_candidate_id || '未记录'} mono />
        <AuditRow label="selection_mode" value={search.provider === 'manual_url' ? 'manual_url' : 'selected_candidate'} />
        <AuditRow label="provider" value={imageSearch.provider || search.provider || '未记录'} />
        <AuditRow label="status" value={imageSearch.status || search.status || '未记录'} />
        <AuditRow label="generation_risk_accepted" value={String(Boolean(imageSearch.generation_risk_accepted))} />
        <AuditRow label="accepted_risk_code" value={imageSearch.accepted_risk_code || '未记录'} />
        <AuditRow label="selected_evidence_level" value={imageSearch.selected_evidence_level || '未记录'} />
        {imageSearch.generation_risk_accepted ? (
          <div className="candidate-near-alert">该模型基于带风险的候选图生成，已由用户确认风险。</div>
        ) : null}
        {imageSearch.selected_evidence_level === 'low' ? (
          <div className="candidate-near-alert">候选图证据较弱，请人工核对图片是否对应目标料号。</div>
        ) : null}
        <div className="section-label subtle">selected_part_match</div>
        <pre className="ai-json-preview">{JSON.stringify(imageSearch.selected_part_match || {}, null, 2)}</pre>
        <div className="section-label subtle">selected_match_evidence</div>
        <pre className="ai-json-preview">{JSON.stringify(imageSearch.selected_match_evidence || {}, null, 2)}</pre>
        <div className="section-label subtle">generation_risk</div>
        <pre className="ai-json-preview">{JSON.stringify(imageSearch.generation_risk || {}, null, 2)}</pre>
        <div className="section-label subtle">visual_recipe 摘要</div>
        <pre className="ai-json-preview">{JSON.stringify(recipeSummary, null, 2)}</pre>
      </div>
    </>
  );
}

function AuditPanel({ job }) {
  const domain = job.source_domain || {};
  const summary = job.source_audit_summary || {};
  const params = job.params || {};
  const category = summary.source_category || domain.category || params.source_domain_category || 'unknown';
  const approved = Boolean(summary.is_approved_source ?? domain.is_approved ?? params.source_domain_approved);
  const versions = params.available_versions || [];
  return (
    <>
      <div className="section-label">来源审计</div>
      <div className={`audit-card ${category === 'unknown' || category === 'third_party_repository' ? 'audit-warning' : ''}`}>
        <div className="audit-head">
          <Fingerprint size={15} />
          <strong>{sourceCategoryText(category, params.model_origin)}</strong>
        </div>
        <AuditRow label="模型来源" value={originText(params.model_origin)} />
        <AuditRow label="来源域名" value={domain.domain || '未提供'} />
        <AuditRow label="来源分类" value={category} />
        <AuditRow label="白名单来源" value={approved ? '是' : '否，需人工核验'} />
        <AuditRow label="缓存使用" value={params.cached_file_used ? '已使用注册表缓存' : '未使用缓存'} />
        <AuditRow label="缓存状态" value={params.registry_cache_status || '未记录'} />
        <AuditRow label="选择策略" value={params.selection_reason || '未触发版本选择'} />
        {params.registry_item_id && <AuditRow label="注册表 ID" value={params.registry_item_id} mono />}
        {params.registry_candidate_id && <AuditRow label="候选 ID" value={params.registry_candidate_id} mono />}
        {params.revision && <AuditRow label="修订版本" value={params.revision} />}
        {params.version_label && <AuditRow label="版本标签" value={params.version_label} />}
        {params.cached_file_sha256 && <AuditRow label="缓存 SHA256" value={params.cached_file_sha256} mono />}
        {params.registry_sha256 && <AuditRow label="注册表 SHA256" value={params.registry_sha256} mono />}
        {versions.length > 0 && (
          <div className="version-list">
            {versions.map((item) => (
              <span key={item.registry_item_id}>{item.revision || 'unknown'} / {item.version_label || 'v?'} / {item.status}</span>
            ))}
          </div>
        )}
        {params.registry_item_id && <div className="audit-success-text">来源：已审核 CAD 来源库。</div>}
        {params.registry_candidate_id && !params.registry_item_id && (
          <div className="audit-warning-text">存在待审核 CAD 来源。管理员审核通过后，后续任务将优先使用官方 CAD。</div>
        )}
      </div>
    </>
  );
}

function RegistryPanel({ onClose }) {
  const [items, setItems] = useState([]);
  const [statusFilter, setStatusFilter] = useState('');
  const [query, setQuery] = useState('');
  const [sourceCategoryFilter, setSourceCategoryFilter] = useState('');
  const [cacheStatusFilter, setCacheStatusFilter] = useState('');
  const [page, setPage] = useState(1);
  const [pageData, setPageData] = useState({ page: 1, page_size: 20, total: 0, total_pages: 1 });
  const [stats, setStats] = useState(null);
  const [auditResult, setAuditResult] = useState(null);
  const [cacheCheck, setCacheCheck] = useState(null);
  const [itemCacheCheck, setItemCacheCheck] = useState(null);
  const [selected, setSelected] = useState(null);
  const [history, setHistory] = useState([]);
  const [cache, setCache] = useState(null);
  const [error, setError] = useState('');
  const [importText, setImportText] = useState('');
  const [form, setForm] = useState({
    manufacturer: 'Test',
    part_number: '',
    title: '',
    source_url: 'local-test',
    cad_url: 'file://backend/test_assets/sample_official.step',
    file_type: 'step',
    revision: 'unknown',
    version_label: 'v1',
    license_note: 'User should verify manufacturer CAD terms before production use.',
  });

  const refresh = async () => {
    setError('');
    try {
      const filters = {
        q: query,
        status: statusFilter,
        source_category: sourceCategoryFilter,
        cache_status: cacheStatusFilter,
        page: String(page),
        page_size: '10',
        sort_by: 'updated_at',
        sort_order: 'desc',
      };
      const [data, statData] = await Promise.all([
        listCadRegistryItems(filters),
        getCadRegistryStats(),
      ]);
      setItems(data.items || []);
      setPageData({
        page: data.page || 1,
        page_size: data.page_size || 10,
        total: data.total || 0,
        total_pages: data.total_pages || 1,
      });
      setStats(statData);
    } catch (err) {
      setError(err.message || '注册表加载失败');
    }
  };

  const loadDetails = async (item) => {
    setSelected(item);
    setHistory([]);
    setCache(null);
    try {
      const [historyData, cacheData] = await Promise.all([
        getCadRegistryItemHistory(item.id),
        getCadRegistryCache(item.id),
      ]);
      setHistory(historyData.events || []);
      setCache(cacheData);
    } catch (err) {
      setError(err.message || '详情加载失败');
    }
  };

  useEffect(() => {
    refresh();
  }, [statusFilter, sourceCategoryFilter, cacheStatusFilter, page]);

  const createItem = async () => {
    setError('');
    try {
      const created = await createCadRegistryItem(form);
      await refresh();
      await loadDetails(created);
    } catch (err) {
      setError(err.message || '新增失败');
    }
  };

  const reviewItem = async (item, status) => {
    setError('');
    try {
      const updated = await reviewCadRegistryItem(item.id, {
        status,
        reviewed_by: 'local_admin',
        review_note: status === 'approved' ? 'Verified CAD source and cached file.' : 'Rejected by local admin.',
      });
      await refresh();
      await loadDetails(updated);
    } catch (err) {
      setError(err.message || '审核失败');
    }
  };

  const refreshCache = async (item) => {
    setError('');
    try {
      const updated = await refreshCadRegistryCache(item.id);
      await refresh();
      await loadDetails(updated);
    } catch (err) {
      setError(err.message || '刷新缓存失败');
    }
  };

  const deprecateItem = async (item) => {
    setError('');
    try {
      const updated = await deprecateCadRegistryItem(item.id, { reason: 'Deprecated by local admin.' });
      await refresh();
      await loadDetails(updated);
    } catch (err) {
      setError(err.message || '废弃失败');
    }
  };

  const exportRegistry = async () => {
    const snapshot = await exportCadRegistry();
    setImportText(JSON.stringify(snapshot, null, 2));
  };

  const importRegistry = async () => {
    setError('');
    try {
      const result = await importCadRegistry(JSON.parse(importText));
      setError(`导入完成：${result.imported} imported, ${result.skipped} skipped, ${result.errors} errors`);
      await refresh();
    } catch (err) {
      setError(err.message || '导入失败');
    }
  };

  const runCacheCheck = async () => {
    setError('');
    try {
      const result = await checkRegistryCache();
      setCacheCheck(result);
    } catch (err) {
      setError(err.message || '缓存巡检失败');
    }
  };

  const repairCache = async () => {
    setError('');
    try {
      const result = await repairRegistryCache();
      setCacheCheck(result);
      await refresh();
    } catch (err) {
      setError(err.message || '缓存修复失败');
    }
  };

  const verifyAudit = async () => {
    setError('');
    try {
      setAuditResult(await verifyRegistryAudit());
    } catch (err) {
      setError(err.message || '审计签名校验失败');
    }
  };

  const loadAuditReport = async () => {
    setError('');
    try {
      const report = await getRegistryAuditReport();
      setImportText(JSON.stringify(report, null, 2));
    } catch (err) {
      setError(err.message || '审计报告生成失败');
    }
  };

  const checkSelectedCache = async (item) => {
    setError('');
    try {
      setItemCacheCheck(await checkRegistryItemCache(item.id));
    } catch (err) {
      setError(err.message || '单条缓存巡检失败');
    }
  };

  const repairSelectedCache = async (item) => {
    setError('');
    try {
      await repairRegistryItemCache(item.id);
      await refresh();
      await loadDetails(item);
    } catch (err) {
      setError(err.message || '单条缓存修复失败');
    }
  };

  return (
    <div className="registry-overlay">
      <section className="registry-panel">
        <div className="registry-header">
          <div>
            <h2>CAD 来源库</h2>
            <p>维护已审核来源、文件缓存、审核历史和多版本记录。</p>
          </div>
          <button className="icon-button" onClick={onClose} title="关闭"><X size={16} /></button>
        </div>
        {error && <ErrorMessage error={error} />}
        {stats && (
          <div className="registry-stats">
            <div><strong>{stats.total_items}</strong><span>总条目</span></div>
            <div><strong>{stats.approved_count}</strong><span>approved</span></div>
            <div><strong>{stats.pending_review_count}</strong><span>pending</span></div>
            <div><strong>{stats.deprecated_count}</strong><span>deprecated</span></div>
            <div><strong>{stats.by_cache_status?.cached || 0}</strong><span>缓存正常</span></div>
            <div><strong>{(stats.by_cache_status?.missing || 0) + (stats.by_cache_status?.invalid || 0)}</strong><span>缓存异常</span></div>
          </div>
        )}
        <div className="registry-audit-actions">
          <button onClick={runCacheCheck}>全量缓存巡检</button>
          <button onClick={repairCache}>修复异常缓存</button>
          <button onClick={verifyAudit}>审核签名校验</button>
          <button onClick={loadAuditReport}>生成审计报告</button>
          <a href={downloadRegistryAuditReport()} download>下载审计报告</a>
        </div>
        {cacheCheck && <div className="audit-warning-text">缓存巡检：checked {cacheCheck.summary?.checked}, ok {cacheCheck.summary?.ok}, missing {cacheCheck.summary?.missing}, hash mismatch {cacheCheck.summary?.hash_mismatch}</div>}
        {auditResult && (
          <div className={auditResult.summary?.invalid ? 'audit-warning-text' : 'audit-success-text'}>
            审计签名：valid {auditResult.summary?.valid}, invalid {auditResult.summary?.invalid}, legacy {auditResult.summary?.unsigned_legacy}
          </div>
        )}
        <div className="registry-layout">
          <div className="registry-form">
            <div className="section-label">新增来源</div>
            {[
              ['manufacturer', '厂家'],
              ['part_number', '连接器型号'],
              ['title', '标题'],
              ['source_url', '来源页面'],
              ['cad_url', 'CAD URL / file://'],
              ['file_type', '文件类型'],
              ['revision', '修订号'],
              ['version_label', '版本标签'],
              ['license_note', '许可证备注'],
            ].map(([key, label]) => (
              <label key={key}>
                <span>{label}</span>
                <input value={form[key]} onChange={(event) => setForm({ ...form, [key]: event.target.value })} />
              </label>
            ))}
            <button className="confirm-button" onClick={createItem}>新增为待审核来源</button>
            <div className="section-label">导入 / 导出</div>
            <div className="registry-actions two">
              <button onClick={exportRegistry}>导出快照</button>
              <button onClick={importRegistry}>导入快照</button>
            </div>
            <textarea
              className="notes-input registry-import"
              value={importText}
              onChange={(event) => setImportText(event.target.value)}
              placeholder="导出的 registry/history JSON 快照"
            />
          </div>
          <div className="registry-list">
            <div className="registry-search">
              <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索 manufacturer / part number / title" />
              <button className="small-action" onClick={() => { setPage(1); refresh(); }}>搜索</button>
            </div>
            <div className="registry-toolbar">
              <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
                <option value="">全部状态</option>
                {['draft', 'pending_review', 'approved', 'rejected', 'deprecated', 'failed_review'].map((item) => (
                  <option key={item} value={item}>{item}</option>
                ))}
              </select>
              <select value={sourceCategoryFilter} onChange={(event) => setSourceCategoryFilter(event.target.value)}>
                <option value="">全部来源</option>
                {['official_manufacturer', 'authorized_distributor', 'third_party_repository', 'local_test', 'unknown'].map((item) => (
                  <option key={item} value={item}>{item}</option>
                ))}
              </select>
              <select value={cacheStatusFilter} onChange={(event) => setCacheStatusFilter(event.target.value)}>
                <option value="">全部缓存</option>
                {['cached', 'missing', 'invalid', 'not_cached'].map((item) => (
                  <option key={item} value={item}>{item}</option>
                ))}
              </select>
              <button className="small-action" onClick={refresh}>刷新列表</button>
            </div>
            <div className="registry-items">
              {items.map((item) => (
                <button key={item.id} className="registry-item" onClick={() => loadDetails(item)}>
                  <strong>{item.manufacturer || 'Unknown'} / {item.part_number}</strong>
                  <span>{item.source_category} / {item.status} / {item.revision || 'unknown'} / {item.version_label}</span>
                  <small>{item.cache_status || 'not_cached'} / {item.updated_at}</small>
                </button>
              ))}
              {!items.length && <div className="empty-panel">暂无注册表条目</div>}
            </div>
            <div className="pagination">
              <button disabled={pageData.page <= 1} onClick={() => setPage(pageData.page - 1)}>上一页</button>
              <span>{pageData.page} / {pageData.total_pages} · {pageData.total}</span>
              <button disabled={pageData.page >= pageData.total_pages} onClick={() => setPage(pageData.page + 1)}>下一页</button>
            </div>
          </div>
          <div className="registry-detail">
            <div className="section-label">详情与审核</div>
            {selected ? (
              <>
                <AuditRow label="ID" value={selected.id} mono />
                <AuditRow label="型号" value={selected.part_number} />
                <AuditRow label="状态" value={selected.status} />
                <AuditRow label="修订号" value={selected.revision} />
                <AuditRow label="版本标签" value={selected.version_label} />
                <AuditRow label="缓存状态" value={selected.cache_status || cache?.cache_status || 'not_cached'} />
                <AuditRow label="cached_at" value={selected.cached_at || '未缓存'} />
                <AuditRow label="文件大小" value={selected.file_size_bytes ? `${selected.file_size_bytes} bytes` : '待计算'} />
                <AuditRow label="SHA256" value={selected.sha256 || '待计算'} mono />
                <AuditRow label="缓存文件" value={selected.cached_file_path || cache?.cached_file_path || '无'} mono />
                <div className="registry-actions">
                  <button onClick={() => reviewItem(selected, 'approved')}>审核通过</button>
                  <button onClick={() => reviewItem(selected, 'rejected')}>驳回</button>
                  <button onClick={() => refreshCache(selected)}>刷新缓存</button>
                  <button onClick={() => checkSelectedCache(selected)}>巡检</button>
                  <button onClick={() => repairSelectedCache(selected)}>修复</button>
                  <button onClick={() => deprecateItem(selected)}>废弃</button>
                </div>
                {itemCacheCheck && (
                  <div className="audit-warning-text">
                    单条巡检：{itemCacheCheck.results?.[0]?.status} / {itemCacheCheck.results?.[0]?.message}
                  </div>
                )}
                <div className="section-label">审核历史</div>
                <div className="history-list">
                  {history.map((event) => (
                    <div key={event.id} className={event.signature && event.payload_hash ? '' : 'invalid-history'}>
                      <strong>{event.event_type}</strong>
                      <span>{event.actor} / {event.created_at}</span>
                      <small>{event.note}</small>
                      <small>{event.signature ? 'signature: recorded' : 'unsigned legacy event'}</small>
                    </div>
                  ))}
                  {!history.length && <div className="empty-panel">暂无历史事件</div>}
                </div>
              </>
            ) : (
              <div className="empty-panel">选择一条来源记录查看详情</div>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}

function AuditRow({ label, value, mono = false }) {
  return (
    <div className="audit-row">
      <span>{label}</span>
      <strong className={mono ? 'mono-value' : ''}>{value || '未记录'}</strong>
    </div>
  );
}

function StatusPanel({ status, warning }) {
  return (
    <div className={`status-card ${status === 'needs_confirmation' ? 'warning-card' : ''}`}>
      <StatusBadge status={status} />
      <span>
        {status === 'needs_confirmation'
          ? warning || '当前为参数化近似预览版，以下尺寸需要确认后才能生成确认版 CAD。'
          : '后端已返回生成结果。'}
      </span>
    </div>
  );
}

function SuccessMessage({ job }) {
  return (
    <div className="success-card">
      <CheckCircle2 size={15} />
      <span>{job.params?.model_origin === 'official_cad' ? '官方 CAD 模型已就绪。' : '确认版 CAD 已生成。'}</span>
    </div>
  );
}

function ErrorMessage({ error }) {
  return (
    <div className="error">
      <AlertTriangle size={15} />
      <span>{error}</span>
    </div>
  );
}

function ParamGrid({ dimensions }) {
  const entries = useMemo(() => Object.entries(dimensions), [dimensions]);
  if (!entries.length) return <div className="empty-panel">暂无参数</div>;
  return (
    <div className="param-grid">
      {entries.map(([key, data]) => (
        <div key={key}>
          <span>{key}</span>
          <strong>{data?.value ?? '待确认'} {data?.unit || ''}</strong>
          <em>{sourceLabel(data?.source)} / {data?.confidence || 'unknown'}</em>
        </div>
      ))}
    </div>
  );
}

function ConfirmPanel({
  job,
  confirmValues,
  setConfirmValues,
  unknownNotes,
  setUnknownNotes,
  confirmNotes,
  setConfirmNotes,
  isBusy,
  onConfirm,
}) {
  const dimensions = job.params?.dimensions || {};
  return (
    <>
      <div className="confirm-alert">当前为参数化近似预览版，以下尺寸需要确认后才能生成确认版 CAD。</div>
      <div className="section-label">确认尺寸</div>
      <div className="confirm-grid">
        {CONFIRM_FIELDS.map(([key, label, dimensionKey]) => {
          const source = dimensions[dimensionKey]?.source;
          return (
            <label key={key}>
              <span>
                {label}
                <small className={`source-tag ${source === 'user_confirmed' ? 'confirmed' : ''}`}>
                  {sourceLabel(source)}
                </small>
              </span>
              <input
                type="number"
                step="0.01"
                value={confirmValues[key] ?? ''}
                onChange={(event) => setConfirmValues({ ...confirmValues, [key]: event.target.value })}
              />
            </label>
          );
        })}
      </div>
      <div className="section-label">待确认参数</div>
      <div className="unknown-inputs">
        {(job.params?.unknown_fields || []).map((field) => (
          <label key={field}>
            <span>{field}</span>
            <input
              value={unknownNotes[field] || ''}
              placeholder="填写说明，或输入 accepted 接受 MVP 近似"
              onChange={(event) => setUnknownNotes({ ...unknownNotes, [field]: event.target.value })}
            />
          </label>
        ))}
      </div>
      <textarea className="notes-input" value={confirmNotes} onChange={(event) => setConfirmNotes(event.target.value)} />
      <button className="confirm-button" disabled={isBusy} onClick={onConfirm}>
        {isBusy ? <Loader2 className="spin" size={16} /> : <RefreshCw size={16} />}
        <span>确认参数并重新生成 CAD</span>
      </button>
    </>
  );
}

function FlatCadPanel({ job }) {
  const params = job.params || {};
  const fc = params.flat_cad;
  const svgUrl = job.files?.flat_views_svg;
  if (!fc?.enabled) return null;
  const sc = fc.structure_completeness || {};
  const mis = fc.missing_items || [];
  const tis = fc.terminal_insertion_summary || {};
  const vcs = fc.view_classification_summary || {};
  const needManual = tis.requires_manual_confirmation !== false;
  return (
    <div className="flat-cad-panel">
      <div className="flat-cad-head">
        <h2>平面 CAD 工程視圖</h2>
        <p className="flat-cad-sub">
          核心交付物為 2D 示意圖（DXF / SVG / JSON），適用於 SOP / WI / QC；3D 僅為輔助預覽。
        </p>
      </div>
      <div className="flat-cad-meta">
        <span>狀態：<strong>{fc.status || '—'}</strong></span>
        <span>結構完整性：<strong>{sc.status || '—'}</strong></span>
        <span>分數：<strong>{sc.score != null ? sc.score : '—'}</strong></span>
      </div>
      <div className="flat-cad-views">
        <div>
          <span className="flat-label">正面／對插面</span>
          <span className="flat-val">{vcs.mating_face_visible ? '影像側推定可見（需確認）' : '示意合成'}</span>
        </div>
        <div>
          <span className="flat-label">反面／入線面</span>
          <span className="flat-val">{vcs.wire_entry_face_visible ? '後側線束出口線索' : '示意合成'}</span>
        </div>
        <div>
          <span className="flat-label">端子插入面（推定）</span>
          <span className="flat-val">{vcs.terminal_insertion_face_likely || '—'}</span>
        </div>
        <div>
          <span className="flat-label">插入方向（推定）</span>
          <span className="flat-val">{tis.insertion_direction || '—'}</span>
        </div>
      </div>
      <div className="flat-cad-terminal">
        <span className="flat-label">建議插入面</span>
        <span>{tis.recommended_insertion_face || '—'}</span>
        <span className="flat-label">信心度</span>
        <span>{tis.confidence || '—'}</span>
        <span className="flat-label">需人工確認</span>
        <span>{needManual ? '是' : '否'}</span>
      </div>
      <div className="flat-cad-warn" role="alert">
        <AlertTriangle size={16} />
        <span>端子插入方向為推斷結果，須依實物或廠家資料確認。非原廠尺寸圖。</span>
      </div>
      {sc.status && sc.status !== 'complete' && mis.length ? (
        <div className="flat-cad-missing">
          <strong>缺漏項目</strong>
          <ul>{mis.map((m) => <li key={m}>{m}</li>)}</ul>
        </div>
      ) : null}
      {fc.warnings && fc.warnings.length ? (
        <ul className="flat-cad-warn-list">
          {fc.warnings.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      ) : null}
      {svgUrl ? (
        <div className="flat-cad-svg-wrap">
          <img className="flat-cad-svg" src={svgUrl} alt="平面視圖總覽 SVG" />
        </div>
      ) : null}
      {fc.status === 'failed' && fc.error ? (
        <p className="flat-cad-error">平面視圖生成失敗：{fc.error}</p>
      ) : null}
    </div>
  );
}

function DownloadPanel({ job }) {
  const params = job.params || {};
  const official = params.model_origin === 'official_cad';
  const completed = job.status === 'completed';
  const ap = params.appearance_pipeline || {};
  const uploadVisual = params.model_origin === 'image_upload_approximated';
  const showImg =
    job.files?.image_features && (ap.image_features_file || uploadVisual);
  const showVision =
    job.files?.vision_report && (ap.vision_report_file || uploadVisual);
  const showSearch = job.files?.image_search_results;
  const showSel = job.files?.selected_image;
  const showRecipe = job.files?.visual_recipe || params.visual_recipe;
  return (
    <>
      <div className="section-label">导出文件</div>
      <div className="downloads">
        <a href={fileUrl(job, 'model_step')} download><span>{official ? '下载官方 STEP' : completed ? '下载确认版 STEP' : '下载预览 STEP'}</span><Download size={14} /></a>
        <a href={fileUrl(job, 'drawing_dxf')} download><span>{official ? '下载来源 DXF' : completed ? '下载确认版 DXF' : '下载预览 DXF'}</span><Code size={14} /></a>
        <a href={fileUrl(job, 'model_stl')} download><span>{official ? '下载官方模型预览 STL' : completed ? '下载确认版 STL' : '下载预览 STL'}</span><Download size={14} /></a>
        <a href={fileUrl(job, 'params_json')} download><span>{official ? '下载来源记录' : completed ? '下载确认版参数记录' : '下载参数记录'}</span><Download size={14} /></a>
        <a href={fileUrl(job, 'source_manifest')} download><span>下载来源审计 JSON</span><ShieldCheck size={14} /></a>
        {showImg ? (
          <a href={fileUrl(job, 'image_features')} download><span>下载图像特征 JSON</span><Code size={14} /></a>
        ) : null}
        {showVision ? (
          <a href={fileUrl(job, 'vision_report')} download><span>下载视觉理解 JSON</span><Code size={14} /></a>
        ) : null}
        {showSearch ? (
          <a href={fileUrl(job, 'image_search_results')} download><span>下载图片搜索结果 JSON</span><Code size={14} /></a>
        ) : null}
        {showSel ? (
          <a href={fileUrl(job, 'selected_image')} download><span>下载选中参考图元数据 JSON</span><Code size={14} /></a>
        ) : null}
        {showRecipe && job.files?.visual_recipe ? (
          <a href={fileUrl(job, 'visual_recipe')} download><span>下载视觉配方 JSON</span><Code size={14} /></a>
        ) : null}
        {job.files?.flat_front_dxf ? (
          <a href={fileUrl(job, 'flat_front_dxf')} download><span>下載平面正面 DXF</span><Download size={14} /></a>
        ) : null}
        {job.files?.flat_rear_dxf ? (
          <a href={fileUrl(job, 'flat_rear_dxf')} download><span>下載平面反面／入線面 DXF</span><Download size={14} /></a>
        ) : null}
        {job.files?.flat_top_dxf ? (
          <a href={fileUrl(job, 'flat_top_dxf')} download><span>下載平面俯視 DXF</span><Download size={14} /></a>
        ) : null}
        {job.files?.flat_side_dxf ? (
          <a href={fileUrl(job, 'flat_side_dxf')} download><span>下載平面側視 DXF</span><Download size={14} /></a>
        ) : null}
        {job.files?.flat_insertion_dxf ? (
          <a href={fileUrl(job, 'flat_insertion_dxf')} download><span>下載端子插入方向 DXF</span><Download size={14} /></a>
        ) : null}
        {job.files?.flat_views_svg ? (
          <a href={fileUrl(job, 'flat_views_svg')} download><span>下載平面總覽 SVG</span><Download size={14} /></a>
        ) : null}
        {job.files?.flat_recipe_json ? (
          <a href={fileUrl(job, 'flat_recipe_json')} download><span>下載 2D recipe JSON</span><Code size={14} /></a>
        ) : null}
        {job.files?.flat_view_classification_json ? (
          <a href={fileUrl(job, 'flat_view_classification_json')} download><span>下載視圖分類 JSON</span><Code size={14} /></a>
        ) : null}
        {job.files?.flat_terminal_insertion_json ? (
          <a href={fileUrl(job, 'flat_terminal_insertion_json')} download><span>下載端子插入判斷 JSON</span><Code size={14} /></a>
        ) : null}
        {job.files?.flat_structure_report_json ? (
          <a href={fileUrl(job, 'flat_structure_report_json')} download><span>下載結構完整性報告 JSON</span><Code size={14} /></a>
        ) : null}
      </div>
    </>
  );
}

function modelSourceTitle(job) {
  const params = job.params || {};
  if (params.model_origin === 'official_cad') return '官方 CAD 模型';
  if (params.model_origin === 'third_party_cad' || params.source_type === 'third_party') return '第三方 CAD 模型';
  if (params.model_origin === 'series_template') return '系列模板近似模型';
  if (params.model_origin === 'image_approximated') return '图片驱动外观近似';
  if (params.model_origin === 'image_search_approximated') return '搜索图片驱动外观近似 CAD';
  if (params.model_origin === 'image_upload_approximated') return '上傳圖片驅動外觀近似模型';
  if (params.model_origin === 'generic_mvp') return '通用参数化白模';
  return '参数化工程近似模型';
}

function modelSourceSubtitle(job) {
  const params = job.params || {};
  if (params.model_origin === 'official_cad') return params.cached_file_used ? '来源：已审核 CAD 来源库缓存' : '来源：厂家官网 / 授权来源，状态：确认版';
  if (params.model_origin === 'third_party_cad' || params.source_type === 'third_party') return '第三方模型，需核验';
  if (params.model_origin === 'series_template') return '系列模板外形近似，非原厂 CAD；关键尺寸需确认';
  if (params.model_origin === 'image_approximated') return '依据上传图像的外观近似模型，非计量级精确 CAD';
  if (params.model_origin === 'image_search_approximated') return '该模型由搜索图片生成，仅为外观近似 CAD，不代表原厂 CAD，不可作为制造尺寸依据。';
  if (params.model_origin === 'image_upload_approximated') return '依上傳圖片之外觀近似；須人工確認尺寸';
  if (params.model_origin === 'generic_mvp') return '升级版通用参数化白模；仅工程近似预览';
  return '需人工确认关键尺寸，不是原厂精确 CAD';
}

function originText(origin) {
  if (origin === 'official_cad') return '官方 CAD';
  if (origin === 'third_party_cad') return '第三方 CAD';
  if (origin === 'series_template') return '系列模板近似';
  if (origin === 'image_approximated') return '图片近似';
  if (origin === 'image_search_approximated') return '搜索图片近似';
  if (origin === 'image_upload_approximated') return '上傳圖片近似';
  if (origin === 'generic_mvp') return '通用白模';
  return '参数化 MVP';
}

function domainFromUrl(url) {
  if (!url) return '';
  try {
    return new URL(url, window.location.origin).hostname;
  } catch {
    return '';
  }
}

function sourceCategoryText(category, origin) {
  if (origin === 'generic_mvp' || origin === 'series_template' || origin === 'image_approximated'
    || origin === 'image_search_approximated' || origin === 'image_upload_approximated') {
    return '參數化 / 視覺近似，不是原廠 CAD';
  }
  if (origin === 'parametric_mvp') return '参数化工程近似模型，不是原厂 CAD';
  if (category === 'official_manufacturer') return '厂家官方来源';
  if (category === 'authorized_distributor') return '授权经销商来源';
  if (category === 'third_party_repository') return '第三方模型来源，必须人工核验后使用';
  if (category === 'local_test') return '本地测试 CAD 来源';
  return '未知来源 CAD，需人工核验';
}

function sourceLabel(source) {
  if (source === 'user_confirmed') return '已确认';
  if (source === 'default_mvp') return '默认值';
  if (source === 'text_hint') return '文本线索';
  if (source === 'ai_extracted') return 'AI 提取';
  if (source === 'registry_template') return '外形注册表';
  return '未知来源';
}

function dangerSource(job) {
  const params = job.params || {};
  const category = job.source_audit_summary?.source_category || job.source_domain?.category;
  return params.source_type === 'third_party' || category === 'third_party_repository' || category === 'unknown';
}
