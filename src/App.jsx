import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertTriangle,
  Box,
  Camera,
  CheckCircle2,
  Code,
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
  createTextConnectorJob,
  checkRegistryCache,
  checkRegistryItemCache,
  deprecateCadRegistryItem,
  downloadRegistryAuditReport,
  exportCadRegistry,
  fileUrl,
  getCadRegistryCache,
  getCadRegistryItemHistory,
  getCadRegistryStats,
  getRegistryAuditReport,
  importCadRegistry,
  listCadRegistryItems,
  pollConnectorJob,
  repairRegistryCache,
  repairRegistryItemCache,
  refreshCadRegistryCache,
  reviewCadRegistryItem,
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

  const canGenerate = activeTab === 'text' ? inputText.trim().length > 0 : Boolean(file);
  const isBusy = status === 'uploading' || status === 'generating';

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
                    if (!isBusy) setStatus('idle');
                  }}
                  placeholder="输入连接器型号或描述"
                  autoFocus
                />
                <div className="examples">
                  <span>示例</span>
                  {['TE 282104-1', 'LOCAL SAMPLE STEP', 'CACHE SAMPLE STEP'].map((item) => (
                    <button key={item} onClick={() => setInputText(item)}>{item}</button>
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
            {error && <ErrorMessage error={error} />}
          </section>
        </main>
      ) : (
        <main className="workspace">
          <section className="viewer-card">
            <div className="viewer-heading">
              <div>
                <h1>{job.params?.title || job.params?.part_number || '通用矩形连接器'}</h1>
                <p>{modelSourceSubtitle(job)}</p>
              </div>
              <button className="icon-button" onClick={reset} title="关闭工作区"><X size={16} /></button>
            </div>
            <ModelViewer jobId={job.job_id} stlUrl={job.files?.model_stl} />
          </section>

          <aside className="inspector">
            <div className="inspector-title">
              <span>属性面板</span>
              <button className="icon-button" onClick={handleGenerate} disabled={isBusy} title="重新生成">
                <RefreshCw size={15} className={isBusy ? 'spin' : ''} />
              </button>
            </div>
            <SourcePanel job={job} />
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

function StatusBadge({ status }) {
  const config = WORKFLOW_STATUS[status] || WORKFLOW_STATUS.idle;
  return <span className={`status-badge ${config.tone}`}>{config.label}</span>;
}

function SourcePanel({ job }) {
  const params = job.params || {};
  return (
    <div className={`source-card ${dangerSource(job) ? 'danger-source' : ''}`}>
      <strong>{modelSourceTitle(job)}</strong>
      <span>{modelSourceSubtitle(job)}</span>
      {params.source_type === 'official_candidate' && <em>检测到待审核 CAD 来源，但当前未用于生成。</em>}
      {params.model_origin === 'parametric_mvp' && <em>参数化工程近似模型，不是原厂 CAD。</em>}
      {params.selection_reason && <small>选择策略：{params.selection_reason}</small>}
    </div>
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

function DownloadPanel({ job }) {
  const params = job.params || {};
  const official = params.model_origin === 'official_cad';
  const completed = job.status === 'completed';
  return (
    <>
      <div className="section-label">导出文件</div>
      <div className="downloads">
        <a href={fileUrl(job, 'model_step')} download><span>{official ? '下载官方 STEP' : completed ? '下载确认版 STEP' : '下载预览 STEP'}</span><Download size={14} /></a>
        <a href={fileUrl(job, 'drawing_dxf')} download><span>{official ? '下载来源 DXF' : completed ? '下载确认版 DXF' : '下载预览 DXF'}</span><Code size={14} /></a>
        <a href={fileUrl(job, 'model_stl')} download><span>{official ? '下载官方模型预览 STL' : completed ? '下载确认版 STL' : '下载预览 STL'}</span><Download size={14} /></a>
        <a href={fileUrl(job, 'params_json')} download><span>{official ? '下载来源记录' : completed ? '下载确认版参数记录' : '下载参数记录'}</span><Download size={14} /></a>
        <a href={fileUrl(job, 'source_manifest')} download><span>下载来源审计 JSON</span><ShieldCheck size={14} /></a>
      </div>
    </>
  );
}

function modelSourceTitle(job) {
  const params = job.params || {};
  if (params.model_origin === 'official_cad') return '官方 CAD 模型';
  if (params.model_origin === 'third_party_cad' || params.source_type === 'third_party') return '第三方 CAD 模型';
  return '参数化工程近似模型';
}

function modelSourceSubtitle(job) {
  const params = job.params || {};
  if (params.model_origin === 'official_cad') return params.cached_file_used ? '来源：已审核 CAD 来源库缓存' : '来源：厂家官网 / 授权来源，状态：确认版';
  if (params.model_origin === 'third_party_cad' || params.source_type === 'third_party') return '第三方模型，需核验';
  return '需人工确认关键尺寸，不是原厂精确 CAD';
}

function originText(origin) {
  if (origin === 'official_cad') return '官方 CAD';
  if (origin === 'third_party_cad') return '第三方 CAD';
  return '参数化 MVP';
}

function sourceCategoryText(category, origin) {
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
  return '未知来源';
}

function dangerSource(job) {
  const params = job.params || {};
  const category = job.source_audit_summary?.source_category || job.source_domain?.category;
  return params.source_type === 'third_party' || category === 'third_party_repository' || category === 'unknown';
}
