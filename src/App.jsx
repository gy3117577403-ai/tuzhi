import React, { useEffect, useMemo, useRef, useState } from 'react';
import { ArrowUpDown, ExternalLink, ImagePlus, MapPin, Search, ShieldAlert, SlidersHorizontal } from 'lucide-react';
import { procurementCsvUrl, searchProcurement } from './api/connectorCad';

const PLATFORM_OPTIONS = ['全部', '淘宝', '京东', '1688', '其他'];
const PLATFORM_VALUES = ['淘宝', '京东', '1688', '其他'];
const SORT_OPTIONS = [
  { label: '综合推荐', value: 'match' },
  { label: '价格从低到高', value: 'price' },
  { label: '发货地优先', value: 'location' },
  { label: '匹配度优先', value: 'match' },
];

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

function hasRisk(item) {
  return (item.risk_tags || []).some((tag) => tag.includes('相近') || tag.includes('异常') || tag.includes('不匹配'));
}

export default function App() {
  const [query, setQuery] = useState('1-968970-1');
  const [imageName, setImageName] = useState('');
  const [targetLocation, setTargetLocation] = useState('浙江 宁波');
  const [platform, setPlatform] = useState('全部');
  const [sortBy, setSortBy] = useState('match');
  const [hideAbnormal, setHideAbnormal] = useState(true);
  const [searchResult, setSearchResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const fileRef = useRef(null);

  const runSearch = async () => {
    const text = query.trim();
    if (!text || busy) return;
    setBusy(true);
    setError('');
    try {
      const data = await searchProcurement({
        query: text,
        target_location: targetLocation.trim(),
        platforms: platform === '全部' ? PLATFORM_VALUES : [platform],
        sort_by: sortBy,
        image_search_enabled: Boolean(imageName),
        source_types: ['mock'],
      });
      setSearchResult(data);
    } catch (err) {
      setError(err.message || '采购搜索失败，请稍后重试。');
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    runSearch();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const visibleResults = useMemo(() => {
    const results = searchResult?.results || [];
    if (!hideAbnormal) return results;
    return results.filter((item) => item.price_type !== 'abnormal' && !(item.risk_tags || []).includes('价格异常'));
  }, [hideAbnormal, searchResult]);

  const abnormalCount = (searchResult?.results || []).filter((item) => item.price_type === 'abnormal' || item.risk_tags?.includes('价格异常')).length;
  const riskCount = visibleResults.filter(hasRisk).length;

  return (
    <main className="采购页面">
      <section className="顶部区域">
        <div>
          <p className="小标题">单个连接器采购搜索工具</p>
          <h1>连接器采购搜索</h1>
          <p className="副标题">输入型号或上传图片，快速查找可采购连接器商品</p>
        </div>
        <div className="提示卡">
          <strong>采购风险提示</strong>
          <span>采购结果来自搜索或报价数据，型号、参数、价格、库存和发货地需采购人员与供应商二次确认。</span>
        </div>
      </section>

      <section className="搜索区">
        <div className="输入组 型号输入">
          <label>连接器型号</label>
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="1-968970-1、282104-1、DT04-2P" />
        </div>
        <div className="输入组">
          <label>目标收货地</label>
          <input value={targetLocation} onChange={(event) => setTargetLocation(event.target.value)} placeholder="例如：浙江 宁波" />
        </div>
        <div className="图片上传">
          <input
            ref={fileRef}
            type="file"
            accept="image/*"
            hidden
            onChange={(event) => setImageName(event.target.files?.[0]?.name || '')}
          />
          <button type="button" className="次要按钮" onClick={() => fileRef.current?.click()}>
            <ImagePlus size={18} />
            上传图片
          </button>
          <span>{imageName || '图片识别搜索待接入，当前仅记录图片名称作为辅助信息。'}</span>
        </div>
        <button type="button" className="搜索按钮" onClick={runSearch} disabled={busy || !query.trim()}>
          <Search size={19} />
          {busy ? '正在搜索...' : '搜索'}
        </button>
      </section>

      <section className="筛选区">
        <div className="筛选块 平台块">
          <SlidersHorizontal size={18} />
          <span>平台</span>
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
          <span>排序</span>
          <select value={sortBy} onChange={(event) => setSortBy(event.target.value)}>
            {SORT_OPTIONS.map((option) => (
              <option value={option.value} key={option.label}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
        <label className="异常开关">
          <input type="checkbox" checked={hideAbnormal} onChange={(event) => setHideAbnormal(event.target.checked)} />
          隐藏异常价格
        </label>
        <button type="button" className="次要按钮" onClick={runSearch} disabled={busy || !query.trim()}>
          应用筛选
        </button>
      </section>

      <section className="结果概览">
        <div>
          <strong>{busy ? '正在搜索采购结果...' : `${visibleResults.length} 条商品结果`}</strong>
          <span>已隐藏异常价格 {hideAbnormal ? abnormalCount : 0} 条，高风险提示 {riskCount} 条</span>
        </div>
        <div className="导出区">
          {searchResult?.search_id ? (
            <a className="导出按钮" href={procurementCsvUrl(searchResult.search_id)}>
              导出当前搜索 CSV
            </a>
          ) : null}
        </div>
      </section>

      {imageName ? <div className="图片提示">已选择图片：{imageName}。图片识别采购搜索将在后续阶段接入。</div> : null}
      {error ? <div className="错误提示">{error}</div> : null}

      <section className="结果网格">
        {visibleResults.map((item) => (
          <article className={`商品卡 ${item.price_type === 'abnormal' ? '价格异常' : ''}`} key={item.id}>
            <div className="图片框">
              {item.image_url ? <img src={item.image_url} alt={item.title} /> : <div className="无图">暂无图片</div>}
              <span className={`平台标签 ${platformClass(item.platform)}`}>{item.platform}</span>
            </div>
            <div className="商品内容">
              <h2>{item.title}</h2>
              <div className="信息行">
                <span>{item.shop_name}</span>
                <span><MapPin size={13} />{item.shipping_location}</span>
              </div>
              <div className="价格行">
                <strong>{formatPrice(item.price, item.currency)}</strong>
                <span>匹配度 {Math.round((item.match_score || 0) * 100)}%</span>
              </div>
              <div className="信息行">
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
