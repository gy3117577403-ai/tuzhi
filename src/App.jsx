import React, { useEffect, useRef, useState } from 'react';
import { ArrowUpDown, ExternalLink, MapPin, Search, ShieldAlert, SlidersHorizontal, Upload } from 'lucide-react';
import { procurementCsvUrl, searchProcurement } from './api/connectorCad';

const PLATFORM_OPTIONS = ['??', '??', '??', '1688', '??'];
const PLATFORM_VALUES = ['??', '??', '1688', '??'];

function mapSort(sortMode) {
  if (sortMode === '???') return 'location';
  if (sortMode === '???') return 'match';
  return 'price';
}

function platformClass(platform) {
  if (platform === '??') return '??-??';
  if (platform === '??') return '??-??';
  if (platform === '1688') return '??-1688';
  return '??-??';
}

function formatPrice(price, currency) {
  const prefix = currency === 'CNY' ? '?' : `${currency || ''} `;
  return `${prefix}${Number(price || 0).toFixed(2)}`;
}

export default function App() {
  const [query, setQuery] = useState('1-968970-1');
  const [imageName, setImageName] = useState('');
  const [platform, setPlatform] = useState('??');
  const [sortMode, setSortMode] = useState('??');
  const [targetLocation, setTargetLocation] = useState('?? ??');
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
      const payload = {
        query: text,
        target_location: targetLocation.trim(),
        platforms: platform === '??' ? PLATFORM_VALUES : [platform],
        sort_by: mapSort(sortMode),
        image_search_enabled: false,
      };
      const data = await searchProcurement(payload);
      setSearchResult(data);
    } catch (err) {
      setError(err.message || '??????');
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    runSearch();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const results = searchResult?.results || [];
  const abnormalCount = results.filter((item) => item.price_type === 'abnormal' || item.risk_tags?.includes('????')).length;
  const highRiskCount = results.filter((item) => (item.risk_tags || []).some((tag) => tag.includes('??') || tag.includes('??') || tag.includes('???'))).length;

  return (
    <main className="????">
      <section className="????">
        <div>
          <p className="???">????????????</p>
          <h1>???????</h1>
          <p className="???">????????????????????</p>
        </div>
        <div className="???">
          <span>??????</span>
          <strong>?? mock provider????????????????</strong>
        </div>
      </section>

      <section className="????">
        <div className="??? ????">
          <label>????</label>
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="???1-968970-1" />
        </div>
        <div className="???">
          <input
            ref={fileRef}
            type="file"
            accept="image/*"
            hidden
            onChange={(event) => setImageName(event.target.files?.[0]?.name || '')}
          />
          <button type="button" className="????" onClick={() => fileRef.current?.click()}>
            <Upload size={18} />
            ????
          </button>
          <span>{imageName || '??????????????????????'}</span>
        </div>
        <button type="button" className="????" onClick={runSearch} disabled={busy || !query.trim()}>
          <Search size={19} />
          {busy ? '????????...' : '??'}
        </button>
      </section>

      <section className="????">
        <div className="???">
          <SlidersHorizontal size={18} />
          <span>????</span>
          <div className="????">
            {PLATFORM_OPTIONS.map((option) => (
              <button key={option} className={platform === option ? '??' : ''} onClick={() => setPlatform(option)}>
                {option}
              </button>
            ))}
          </div>
        </div>
        <div className="???">
          <ArrowUpDown size={18} />
          <span>????</span>
          <select value={sortMode} onChange={(event) => setSortMode(event.target.value)}>
            <option value="??">?????</option>
            <option value="???">??????</option>
            <option value="???">??????</option>
          </select>
        </div>
        <div className="??? ???">
          <MapPin size={18} />
          <span>?????</span>
          <input value={targetLocation} onChange={(event) => setTargetLocation(event.target.value)} placeholder="????? ??" />
        </div>
      </section>

      <section className="???">
        <button type="button" className="????" onClick={runSearch} disabled={busy || !query.trim()}>
          ???????
        </button>
        {searchResult?.search_id ? (
          <a className="????" href={procurementCsvUrl(searchResult.search_id)}>
            ?????? CSV
          </a>
        ) : null}
      </section>

      <section className="????">
        <div>
          <strong>{busy ? '????????...' : `${results.length} ?????`}</strong>
          <span>???? {abnormalCount} ?????????? {highRiskCount} ?</span>
        </div>
        <p>{searchResult?.warnings?.[0] || '???????????????????????????'}</p>
      </section>

      {error ? <div className="????">{error}</div> : null}

      <section className="????">
        {results.map((item) => (
          <article className={`??? ${item.price_type === 'abnormal' ? '????' : ''}`} key={item.id}>
            <div className="???">
              <img src={item.image_url} alt={item.title} />
              <span className={`???? ${platformClass(item.platform)}`}>{item.platform}</span>
            </div>
            <div className="????">
              <h2>{item.title}</h2>
              <div className="???">
                <span>{item.shop_name}</span>
                <span>{item.shipping_location}</span>
              </div>
              <div className="???">
                <strong>{formatPrice(item.price, item.currency)}</strong>
                <span>??? {Math.round((item.match_score || 0) * 100)}%</span>
              </div>
              <div className="???">
                <span>{item.stock_status}</span>
                <span>{item.moq} ???</span>
              </div>
              <div className="???">
                {Object.entries(item.key_parameters || {}).map(([key, value]) => (
                  <span key={key}>{key}?{String(value)}</span>
                ))}
              </div>
              <div className="???">
                {(item.risk_tags || []).map((tag) => (
                  <span className={tag.includes('??') || tag.includes('??') || tag.includes('???') ? '???' : ''} key={tag}>
                    <ShieldAlert size={13} />
                    {tag}
                  </span>
                ))}
              </div>
              <a className="????" href={item.product_url} target="_blank" rel="noreferrer">
                ??????
                <ExternalLink size={16} />
              </a>
            </div>
          </article>
        ))}
      </section>
    </main>
  );
}
