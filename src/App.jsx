import React, { useMemo, useRef, useState } from 'react';
import { ArrowUpDown, Camera, ExternalLink, MapPin, Search, ShieldAlert, SlidersHorizontal, Upload } from 'lucide-react';

const 平台选项 = ['全部', '淘宝', '京东', '1688', '其他'];

function 连接器图片(颜色, 形状 = 'rect') {
  const svg = 形状 === 'round'
    ? `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 360 240"><rect width="360" height="240" fill="#f7f7f4"/><ellipse cx="176" cy="122" rx="82" ry="70" fill="${颜色}" stroke="#222" stroke-width="10"/><ellipse cx="176" cy="122" rx="34" ry="29" fill="#f1f1ef" stroke="#333" stroke-width="7"/><rect x="50" y="101" width="74" height="42" rx="14" fill="${颜色}" stroke="#222" stroke-width="8"/><rect x="229" y="84" width="42" height="76" rx="10" fill="#444"/><text x="24" y="220" font-family="Arial" font-size="18" fill="#555">圆形连接器示意图</text></svg>`
    : `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 360 240"><rect width="360" height="240" fill="#f7f7f4"/><rect x="62" y="72" width="236" height="104" rx="18" fill="${颜色}" stroke="#222" stroke-width="8"/><rect x="96" y="99" width="168" height="52" rx="12" fill="#f5f5ef" stroke="#333" stroke-width="5"/><g fill="#222">${[0,1,2,3].map((i)=>`<circle cx="${126+i*36}" cy="125" r="10"/>`).join('')}</g><rect x="132" y="48" width="96" height="25" rx="7" fill="${颜色}" stroke="#222" stroke-width="6"/><text x="24" y="220" font-family="Arial" font-size="18" fill="#555">矩形连接器示意图</text></svg>`;
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
}

const mock商品 = [
  {
    id: 'taobao-001',
    平台: '淘宝',
    店铺: '华南接插件现货店',
    标题: 'TE 同款 1-968970-1 汽车连接器护套 4孔 蓝色',
    价格: 3.8,
    发货地: '广东 深圳',
    库存: '现货 1200 件',
    起订量: '10 件起订',
    参数: ['4孔', '蓝色护套', '汽车线束', 'PA66'],
    匹配度: 96,
    风险: ['需核对原厂料号授权'],
    链接: 'https://example.com/taobao/1-968970-1',
    图片: 连接器图片('#2f73d8'),
    异常价格: false,
  },
  {
    id: 'jd-001',
    平台: '京东',
    店铺: '工控电子自营专区',
    标题: '1-968970-1 连接器外壳 端子配套 汽车插件',
    价格: 6.5,
    发货地: '江苏 苏州',
    库存: '现货 380 件',
    起订量: '1 件起订',
    参数: ['4位', '线束外壳', '耐温 -40~105℃'],
    匹配度: 92,
    风险: ['价格含平台服务费'],
    链接: 'https://example.com/jd/1-968970-1',
    图片: 连接器图片('#2f73d8'),
    异常价格: false,
  },
  {
    id: '1688-001',
    平台: '1688',
    店铺: '东莞精密连接器厂',
    标题: '汽车连接器 1-968970-1 蓝色胶壳 可配端子',
    价格: 1.26,
    发货地: '广东 东莞',
    库存: '库存 9800 件',
    起订量: '500 件起订',
    参数: ['工厂批发', '可配端子', '蓝色', '批量价'],
    匹配度: 89,
    风险: ['起订量较高', '需确认是否原厂兼容'],
    链接: 'https://example.com/1688/1-968970-1',
    图片: 连接器图片('#2f73d8'),
    异常价格: false,
  },
  {
    id: 'taobao-002',
    平台: '淘宝',
    店铺: '线束端子配件仓',
    标题: '8-968970-1 相近型号蓝色汽车接插件',
    价格: 2.9,
    发货地: '浙江 宁波',
    库存: '现货 600 件',
    起订量: '20 件起订',
    参数: ['相近料号', '蓝色', '汽车插件'],
    匹配度: 71,
    风险: ['相近型号风险', '不能直接替代需确认'],
    链接: 'https://example.com/taobao/8-968970-1',
    图片: 连接器图片('#3777d4'),
    异常价格: false,
  },
  {
    id: 'other-001',
    平台: '其他',
    店铺: 'Mouser 代购报价',
    标题: 'TE Connectivity 1-968970-1 连接器采购代订',
    价格: 12.4,
    发货地: '海外仓',
    库存: '预计 2-3 周',
    起订量: '1 件起订',
    参数: ['品牌渠道', '代订', '交期较长'],
    匹配度: 94,
    风险: ['交期不确定', '需核对含税运费'],
    链接: 'https://example.com/distributor/1-968970-1',
    图片: 连接器图片('#2f73d8'),
    异常价格: false,
  },
  {
    id: '1688-002',
    平台: '1688',
    店铺: '温州端子连接器批发',
    标题: '6-968970-1 相近规格连接器胶壳 批发',
    价格: 0.18,
    发货地: '浙江 温州',
    库存: '库存 20000 件',
    起订量: '1000 件起订',
    参数: ['相近料号', '批发低价', '需样品确认'],
    匹配度: 63,
    风险: ['相近型号风险', '价格异常', '参数不完整'],
    链接: 'https://example.com/1688/6-968970-1',
    图片: 连接器图片('#2f73d8'),
    异常价格: true,
  },
  {
    id: 'jd-002',
    平台: '京东',
    店铺: '汽车线束配件旗舰店',
    标题: '1-968970-1 蓝色连接器套装 含端子密封塞',
    价格: 9.9,
    发货地: '上海',
    库存: '现货 88 套',
    起订量: '1 套起订',
    参数: ['套装', '含端子', '含密封塞'],
    匹配度: 88,
    风险: ['套装价格不可直接对比单壳'],
    链接: 'https://example.com/jd/kit-1-968970-1',
    图片: 连接器图片('#2f73d8'),
    异常价格: false,
  },
  {
    id: 'taobao-003',
    平台: '淘宝',
    店铺: '工业圆形航空插头店',
    标题: '圆形防水连接器 4芯 黑色 航空插头',
    价格: 18.5,
    发货地: '浙江 宁波',
    库存: '现货 260 件',
    起订量: '2 件起订',
    参数: ['圆形', '防水', '4芯', '黑色'],
    匹配度: 42,
    风险: ['图片相似但型号不匹配', '非目标料号'],
    链接: 'https://example.com/taobao/round-connector',
    图片: 连接器图片('#18191b', 'round'),
    异常价格: false,
  },
];

function 地区命中分(发货地, 目标地) {
  const 发货 = 发货地.replace(/\s+/g, '');
  const 目标 = 目标地.replace(/\s+/g, '');
  if (!目标) return 0;
  if (发货.includes(目标) || 目标.includes(发货)) return 3;
  const 目标片段 = 目标地.split(/\s+/).filter(Boolean);
  return 目标片段.reduce((分, 片段) => 分 + (发货.includes(片段) ? 1 : 0), 0);
}

function 价格排序值(商品) {
  return 商品.异常价格 ? 商品.价格 + 100000 : 商品.价格;
}

export default function App() {
  const [型号, 设置型号] = useState('1-968970-1 connector');
  const [图片名, 设置图片名] = useState('');
  const [平台, 设置平台] = useState('全部');
  const [排序, 设置排序] = useState('价格');
  const [目标地, 设置目标地] = useState('浙江 宁波');
  const [已搜索, 设置已搜索] = useState(true);
  const fileRef = useRef(null);

  const 结果 = useMemo(() => {
    const 关键词 = 型号.trim().toLowerCase();
    const 过滤后 = mock商品.filter((商品) => {
      const 平台匹配 = 平台 === '全部' || 商品.平台 === 平台;
      const 文本 = `${商品.标题} ${商品.参数.join(' ')}`.toLowerCase();
      const 关键词匹配 = !关键词 || 文本.includes(关键词.split(/\s+/)[0]) || 商品.匹配度 >= 60;
      return 平台匹配 && 关键词匹配;
    });
    return [...过滤后].sort((a, b) => {
      if (排序 === '发货地') {
        const 地区差 = 地区命中分(b.发货地, 目标地) - 地区命中分(a.发货地, 目标地);
        if (地区差 !== 0) return 地区差;
        if (a.异常价格 !== b.异常价格) return a.异常价格 ? 1 : -1;
        return a.价格 - b.价格;
      }
      const 价差 = 价格排序值(a) - 价格排序值(b);
      if (价差 !== 0) return 价差;
      return b.匹配度 - a.匹配度;
    });
  }, [型号, 平台, 排序, 目标地]);

  const 异常数量 = 结果.filter((商品) => 商品.异常价格).length;
  const 高风险数量 = 结果.filter((商品) => 商品.风险.some((项) => 项.includes('相近') || 项.includes('异常'))).length;

  return (
    <main className="采购页面">
      <section className="顶部区域">
        <div>
          <p className="小标题">连接器采购搜索与比价工具</p>
          <h1>连接器采购搜索</h1>
          <p className="副标题">输入型号或上传图片，搜索可采购连接器商品</p>
        </div>
        <div className="状态卡">
          <span>当前为模拟数据演示</span>
          <strong>不接真实平台接口，不做爬虫</strong>
        </div>
      </section>

      <section className="搜索面板">
        <div className="输入组 型号输入">
          <label>型号输入</label>
          <input value={型号} onChange={(event) => 设置型号(event.target.value)} placeholder="例如：1-968970-1 connector" />
        </div>
        <div className="上传区">
          <input
            ref={fileRef}
            type="file"
            accept="image/*"
            hidden
            onChange={(event) => 设置图片名(event.target.files?.[0]?.name || '')}
          />
          <button type="button" className="次要按钮" onClick={() => fileRef.current?.click()}>
            <Upload size={18} />
            上传图片
          </button>
          <span>{图片名 || '可上传商品图或连接器照片用于后续识别'}</span>
        </div>
        <button type="button" className="搜索按钮" onClick={() => 设置已搜索(true)}>
          <Search size={19} />
          搜索
        </button>
      </section>

      <section className="筛选面板">
        <div className="筛选块">
          <SlidersHorizontal size={18} />
          <span>平台筛选</span>
          <div className="分段控件">
            {平台选项.map((选项) => (
              <button key={选项} className={平台 === 选项 ? '已选' : ''} onClick={() => 设置平台(选项)}>
                {选项}
              </button>
            ))}
          </div>
        </div>
        <div className="筛选块">
          <ArrowUpDown size={18} />
          <span>排序方式</span>
          <select value={排序} onChange={(event) => 设置排序(event.target.value)}>
            <option value="价格">按价格排序</option>
            <option value="发货地">按发货地排序</option>
          </select>
        </div>
        <div className="筛选块 目标地">
          <MapPin size={18} />
          <span>目标收货地</span>
          <input value={目标地} onChange={(event) => 设置目标地(event.target.value)} placeholder="例如：浙江 宁波" />
        </div>
      </section>

      <section className="结果概览">
        <div>
          <strong>{已搜索 ? `${结果.length} 条商品结果` : '等待搜索'}</strong>
          <span>价格异常 {异常数量} 条，相近型号或高风险 {高风险数量} 条</span>
        </div>
        <p>价格异常项不会排在第一位；采购前请核对型号、规格、库存、税费、交期和供应商资质。</p>
      </section>

      <section className="结果网格">
        {结果.map((商品) => (
          <article className={`商品卡 ${商品.异常价格 ? '价格异常' : ''}`} key={商品.id}>
            <div className="图片框">
              <img src={商品.图片} alt={商品.标题} />
              <span className={`平台标签 平台-${商品.平台}`}>{商品.平台}</span>
            </div>
            <div className="商品内容">
              <h2>{商品.标题}</h2>
              <div className="店铺行">
                <span>{商品.店铺}</span>
                <span>{商品.发货地}</span>
              </div>
              <div className="价格行">
                <strong>￥{商品.价格.toFixed(2)}</strong>
                <span>匹配度 {商品.匹配度}%</span>
              </div>
              <div className="库存行">
                <span>{商品.库存}</span>
                <span>{商品.起订量}</span>
              </div>
              <div className="参数行">
                {商品.参数.map((参数) => <span key={参数}>{参数}</span>)}
              </div>
              <div className="风险行">
                {商品.风险.map((风险) => (
                  <span className={风险.includes('异常') || 风险.includes('相近') || 风险.includes('非目标') ? '高风险' : ''} key={风险}>
                    <ShieldAlert size={13} />
                    {风险}
                  </span>
                ))}
              </div>
              <a className="商品链接" href={商品.链接} target="_blank" rel="noreferrer">
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
