import React, { useEffect, useRef, useState } from 'react';
import { ArrowUpDown, Database, ExternalLink, FileSpreadsheet, MapPin, Search, ShieldAlert, SlidersHorizontal, Upload } from 'lucide-react';
import { importProcurementQuotes, listProcurementSources, procurementCsvUrl, searchProcurement } from './api/connectorCad';

const PLATFORM_OPTIONS = ['全部', '淘宝', '京东', '1688', '其他'];
const PLATFORM_VALUES = ['淘宝', '京东', '1688', '其他'];
const SOURCE_FILTERS = [
  { label: '全部来源', value: 'all' },
  { label: '仅报价表', value: 'imports' },
  { label: '仅 mock', value: 'mock' },
  { label: '授权接口', value: 'generic_json' },
];

function mapSort(sortMode) {
  if (sortMode === '按发货地排序') return 'location';
  if (sortMode === '按匹配度排序') return 'match';
  return 'price';
}

function sourceTypesForFilter(filter) {
  if (filter === 'imports') return ['csv_upload', 'excel_upload'];
  if (filter === 'mock') return ['mock'];
  if (filter === 'generic_json') return ['generic_json'];
  return ['mock', 'csv_upload', 'excel_upload', 'generic_json'];
}

function platformClass(platform) {
  if (platform === '淘宝') return '平台-淘宝';
  if (platform === '京东') return '平台-京东';
  if (platform === '1688') return '平台-1688';
  return '平台-其他';
}

function formatPrice(price, currency) {
  const prefix = currency === 'CNY' ? '¥' : `${currency || ''} `;
  return `${prefix}${Number(price || 0).toFixed(2)}`;
}

export default function App() {
  const [query, setQuery] = useState('1-968970-1');
  const [imageName, setImageName] = useState('');
  const [platform, setPlatform] = useState('全部');
  const [sortMode, setSortMode] = useState('按价格排序');
  const [targetLocation, setTargetLocation] = useState('浙江 宁波');
  const [sourceFilter, setSourceFilter] = useState('all');
  const [searchResult, setSearchResult] = useState(null);
  const [sources, setSources] = useState([]);
  const [busy, setBusy] = useState(false);
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState('');
  const [importMessage, setImportMessage] = useState('');
  const [sourceName, setSourceName] = useState('供应商报价表');
  const [platformLabel, setPlatformLabel] = useState('其他');
  const fileRef = useRef(null);
  const quoteFileRef = useRef(null);

  const refreshSources = async () => {
    try {
      const data = await listProcurementSources();
      setSources(data.sources || []);
    } catch {
      setSources([]);
    }
  };

  const runSearch = async () => {
    const text = query.trim();
    if (!text || busy) return;
    setBusy(true);
    setError('');
    try {
      const payload = {
        query: text,
        target_location: targetLocation.trim(),
        platforms: platform === '全部' ? PLATFORM_VALUES : [platform],
        sort_by: mapSort(sortMode),
        image_search_enabled: false,
        source_types: sourceTypesForFilter(sourceFilter),
      };
      const data = await searchProcurement(payload);
      setSearchResult(data);
    } catch (err) {
      setError(err.message || '采购搜索失败');
    } finally {
      setBusy(false);
    }
  };

  const handleQuoteImport = async (event) => {
    const file = event.target.files?.[0];
    if (!file || importing) return;
    setImporting(true);
    setError('');
    setImportMessage('');
    try {
      const result = await importProcurementQuotes(file, sourceName, platformLabel);
      setImportMessage(`导入完成：共 ${result.rows_total} 行，成功 ${result.rows_imported} 行，跳过 ${result.rows_skipped} 行。`);
      await refreshSources();
      await runSearch();
    } catch (err) {
      setError(err.message || '报价表导入失败');
    } finally {
      setImporting(false);
      event.target.value = '';
    }
  };

  useEffect(() => {
    refreshSources();
    runSearch();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const results = searchResult?.results || [];
  const abnormalCount = results.filter((item) => item.price_type === 'abnormal' || item.risk_tags?.includes('价格异常')).length;
  const highRiskCount = results.filter((item) => (item.risk_tags || []).some((tag) => tag.includes('相近') || tag.includes('异常') || tag.includes('不匹配'))).length;

  return (
    <main className="采购页面">
      <section className="顶部区域">
        <div>
          <p className="小标题">连接器采购搜索与比价工具</p>
          <h1>连接器采购搜索</h1>
          <p className="副标题">输入型号或上传图片，搜索可采购连接器商品</p>
        </div>
        <div className="状态卡">
          <span>合规数据源</span>
          <strong>支持 mock、报价表导入、授权接口；不做违规爬虫</strong>
        </div>
      </section>

      <section className="搜索面板">
        <div className="输入组 型号输入">
          <label>型号</label>
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="例如：1-968970-1" />
        </div>
        <div className="上传区">
          <input
            ref={fileRef}
            type="file"
            accept="image/*"
            hidden
            onChange={(event) => setImageName(event.target.files?.[0]?.name || '')}
          />
          <button type="button" className="次要按钮" onClick={() => fileRef.current?.click()}>
            <Upload size={18} />
            上传图片
          </button>
          <span>{imageName || '图片搜索采购会在后续阶段接入'}</span>
        </div>
        <button type="button" className="搜索按钮" onClick={runSearch} disabled={busy || !query.trim()}>
          <Search size={19} />
          {busy ? '正在搜索采购渠道...' : '搜索'}
        </button>
      </section>

      <section className="数据源面板">
        <div className="数据源标题">
          <Database size={18} />
          <strong>采购数据源</strong>
          <span>{sources.length} 个来源</span>
        </div>
        <div className="导入控件">
          <input value={sourceName} onChange={(event) => setSourceName(event.target.value)} placeholder="数据源名称，例如：华东供应商报价表" />
          <select value={platformLabel} onChange={(event) => setPlatformLabel(event.target.value)}>
            <option value="其他">其他</option>
            <option value="淘宝">淘宝</option>
            <option value="京东">京东</option>
            <option value="1688">1688</option>
          </select>
          <input ref={quoteFileRef} type="file" accept=".csv,.xlsx,.xlsm" hidden onChange={handleQuoteImport} />
          <button type="button" className="次要按钮" onClick={() => quoteFileRef.current?.click()} disabled={importing}>
            <FileSpreadsheet size={18} />
            {importing ? '正在导入...' : '导入报价表'}
          </button>
        </div>
        <div className="来源列表">
          {sources.map((source) => (
            <span key={source.source_id}>
              {source.source_name} / {source.source_type} / {source.enabled ? '启用' : '停用'}
            </span>
          ))}
        </div>
        {importMessage ? <p className="导入提示">{importMessage}</p> : null}
      </section>

      <section className="筛选面板">
        <div className="筛选块">
          <SlidersHorizontal size={18} />
          <span>平台筛选</span>
          <div className="分段控件">
            {PLATFORM_OPTIONS.map((option) => (
              <button key={option} className={platform === option ? '已选' : ''} onClick={() => setPlatform(option)}>
                {option}
              </button>
            ))}
          </div>
        </div>
        <div className="筛选块">
          <ArrowUpDown size={18} />
          <span>排序方式</span>
          <select value={sortMode} onChange={(event) => setSortMode(event.target.value)}>
            <option value="按价格排序">按价格排序</option>
            <option value="按发货地排序">按发货地排序</option>
            <option value="按匹配度排序">按匹配度排序</option>
          </select>
        </div>
        <div className="筛选块 目标地">
          <MapPin size={18} />
          <span>目标收货地</span>
          <input value={targetLocation} onChange={(event) => setTargetLocation(event.target.value)} placeholder="例如：浙江 宁波" />
        </div>
        <div className="筛选块">
          <Database size={18} />
          <span>来源筛选</span>
          <select value={sourceFilter} onChange={(event) => setSourceFilter(event.target.value)}>
            {SOURCE_FILTERS.map((option) => (
              <option value={option.value} key={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
      </section>

      <section className="操作栏">
        <button type="button" className="次要按钮" onClick={runSearch} disabled={busy || !query.trim()}>
          应用筛选与排序
        </button>
        {searchResult?.search_id ? (
          <a className="导出按钮" href={procurementCsvUrl(searchResult.search_id)}>
            导出采购清单 CSV
          </a>
        ) : null}
      </section>

      <section className="结果概览">
        <div>
          <strong>{busy ? '正在搜索采购渠道...' : `${results.length} 条商品结果`}</strong>
          <span>价格异常 {abnormalCount} 条，高风险提示 {highRiskCount} 条</span>
        </div>
        <p>{searchResult?.warnings?.[0] || '采购结果需人工确认型号、供应商资质、库存和交期。'}</p>
      </section>

      {error ? <div className="错误提示">{error}</div> : null}

      <section className="结果网格">
        {results.map((item) => (
          <article className={`商品卡 ${item.price_type === 'abnormal' ? '价格异常' : ''}`} key={item.id}>
            <div className="图片框">
              {item.image_url ? <img src={item.image_url} alt={item.title} /> : <div className="无图">暂无图片</div>}
              <span className={`平台标签 ${platformClass(item.platform)}`}>{item.platform}</span>
            </div>
            <div className="商品内容">
              <h2>{item.title}</h2>
              <div className="店铺行">
                <span>{item.shop_name}</span>
                <span>{item.shipping_location}</span>
              </div>
              <div className="来源行">
                <span>{item.source_name || '未知来源'}</span>
                <span>{item.source_type || 'mock'}</span>
              </div>
              <div className="价格行">
                <strong>{formatPrice(item.price, item.currency)}</strong>
                <span>匹配度 {Math.round((item.match_score || 0) * 100)}%</span>
              </div>
              <div className="库存行">
                <span>{item.stock_status}</span>
                <span>{item.moq} 起订</span>
              </div>
              <div className="参数行">
                {Object.entries(item.key_parameters || {}).map(([key, value]) => (
                  <span key={key}>{key}：{String(value)}</span>
                ))}
              </div>
              <div className="风险行">
                {(item.risk_tags || []).map((tag) => (
                  <span className={tag.includes('相近') || tag.includes('异常') || tag.includes('不匹配') ? '高风险' : ''} key={tag}>
                    <ShieldAlert size={13} />
                    {tag}
                  </span>
                ))}
              </div>
              <a className="商品链接" href={item.product_url} target="_blank" rel="noreferrer">
                打开商品链接
                <ExternalLink size={16} />
              </a>
            </div>
          </article>
        ))}
      </section>
    </main>
  );
}
