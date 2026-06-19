import AuthGate, { useAuth } from './AuthGate';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { apiRequest } from './api';
import Select from './components/Select';
import { fmtMs, fmtNum, fmtPct, unique } from './utils';

const CAPABILITY_LABELS = {
  'chat': '对话',
  'vision.image': '视觉·图片',
  'vision.video': '视觉·视频',
  'audio.asr': '语音识别',
  'audio.tts': '语音合成',
  'audio.speech_to_speech': '语音·语音',
  'image.generation': '图像生成',
  'image.edit': '图像编辑',
  'video.text_to_video': '视频·文生',
  'video.image_to_video': '视频·图生',
  'video.video_to_video': '视频·视频',
  'embedding': '嵌入',
  'rerank': '重排',
};

const CAPABILITY_EMOJI = {
  'chat': '',
  'vision': ' 📷',
  'audio': ' 🎧',
  'image': ' 📷',
  'video': ' 🎬',
  'embedding': '',
  'rerank': '',
};

const NAV_ITEMS = [
  ['overview', '仪表盘'],
  ['providers', 'Provider'],
  ['models', '模型'],
  ['keys', 'API 密钥'],
  ['logs', '调用日志'],
  ['usage', '用量统计'],
  ['settings', '配置'],
];

const DASHBOARD_PERIOD_OPTIONS = [
  { value: 'today', label: '今日' },
  { value: '7d', label: '7 天' },
];

const USAGE_PERIOD_OPTIONS = [
  { value: 'today', label: '今日' },
  { value: '7d', label: '7 天' },
  { value: '30d', label: '30 天' },
];

const LOG_STATUS_OPTIONS = [
  { value: 'all', label: '全部' },
  { value: 'ok', label: '成功', tone: 'ok' },
  { value: 'error', label: '错误', tone: 'bad' },
];

const MODEL_LINE_COLORS = ['#6d5dfc', '#10a9c7', '#df5f83'];

function getInitialSection() {
  const section = window.location.hash.slice(1);
  return NAV_ITEMS.some(([id]) => id === section) ? section : 'overview';
}

function Delta({ value, children, downWhenNegative = true }) {
  if (children) {
    return <span className="delta">{children}</span>;
  }
  if (value == null || Number.isNaN(Number(value))) {
    return <span className="delta">--</span>;
  }
  const n = Number(value);
  const down = downWhenNegative ? n <= 0 : n > 0;
  const sign = n > 0 ? '+' : '';
  return <span className={`delta${down ? ' down' : ''}`}>{sign}{n.toFixed(1)}%</span>;
}

function Badge({ tone = '', children }) {
  return <span className={`badge${tone ? ` ${tone}` : ''}`}>{children}</span>;
}

function TestPill({ test }) {
  if (!test) return null;
  if (test.status === 'pending') {
    return <span className="test-pill pending">测试中...</span>;
  }
  if (test.status === 'success') {
    const label = [`正常 ${fmtMs(test.latencyMs)}`, test.testedAt ? ` · ${test.testedAt}` : ''].filter(Boolean).join('');
    return <span className="test-pill success" title={test.content || ''}>{label}</span>;
  }
  if (test.status === 'error') {
    return <span className="test-pill error" title={test.message || ''}>失败</span>;
  }
  return null;
}

function EmptyRow({ colSpan, children = '暂无数据' }) {
  return (
    <tr>
      <td colSpan={colSpan} style={{ color: 'var(--muted)' }}>{children}</td>
    </tr>
  );
}

function MetricCard({ tone = '', label, delta, value, foot }) {
  return (
    <article className={`metric-card card-hover${tone ? ` ${tone}` : ''}`}>
      <div className="metric-label">{label} {delta}</div>
      <b className="metric-value">{value}</b>
      <p className="metric-foot">{foot}</p>
    </article>
  );
}

function makeSmoothPath(points) {
  if (!points.length) return '';
  if (points.length === 1) return `M${points[0].x.toFixed(1)} ${points[0].y.toFixed(1)}`;
  let path = `M${points[0].x.toFixed(1)} ${points[0].y.toFixed(1)}`;
  for (let i = 0; i < points.length - 1; i += 1) {
    const p0 = points[i - 1] || points[i];
    const p1 = points[i];
    const p2 = points[i + 1];
    const p3 = points[i + 2] || p2;
    const cp1x = p1.x + (p2.x - p0.x) / 6;
    const cp1y = p1.y + (p2.y - p0.y) / 6;
    const cp2x = p2.x - (p3.x - p1.x) / 6;
    const cp2y = p2.y - (p3.y - p1.y) / 6;
    path += ` C${cp1x.toFixed(1)} ${cp1y.toFixed(1)} ${cp2x.toFixed(1)} ${cp2y.toFixed(1)} ${p2.x.toFixed(1)} ${p2.y.toFixed(1)}`;
  }
  return path;
}

function trendDateLabel(date) {
  return (date || '').slice(5) || '--';
}

function buildTopModelSeries(trend, entries) {
  const dates = (trend || []).map((item) => item.date).filter(Boolean);
  if (!dates.length || !entries?.length) return [];
  const dateIndex = new Map(dates.map((date, index) => [date, index]));
  const byModel = {};

  for (const entry of entries) {
    const model = entry.model || 'unknown';
    const date = entry._trendDate || String(entry.timestamp || '').slice(0, 10);
    const index = dateIndex.get(date);
    if (index == null) continue;
    if (!byModel[model]) {
      byModel[model] = {
        model,
        values: Array(dates.length).fill(0),
        total: 0,
      };
    }
    byModel[model].values[index] += 1;
    byModel[model].total += 1;
  }

  const all = Object.values(byModel).sort((a, b) => b.total - a.total).slice(0, 3);
  const grandTotal = all.reduce((sum, item) => sum + item.total, 0) || 1;
  return all.map((item, index) => ({
    ...item,
    color: MODEL_LINE_COLORS[index],
    pct: item.total / grandTotal * 100,
  }));
}

function buildTrendVisual(data, modelSeries = []) {
  if (!data?.length) {
    return {
      width: 720,
      height: 260,
      bars: [],
      area: '',
      totalLine: '',
      ticks: [],
      modelLines: [],
      avg: 0,
      maxRequests: 0,
      latestRequests: 0,
      peak: null,
      baselineY: 0,
      peakLabel: null,
    };
  }
  const width = 720;
  const height = 260;
  const padLeft = 54;
  const padRight = 28;
  const top = 28;
  const bottom = 206;
  const plotWidth = width - padLeft - padRight;
  const x = (i) => padLeft + (i / Math.max(data.length - 1, 1)) * (width - padLeft - padRight);
  const maxRequests = Math.max(...data.map((item) => item.requests || 0), 1);
  const avg = data.reduce((sum, item) => sum + (item.requests || 0), 0) / data.length;
  const scaleMax = Math.max(maxRequests, avg, ...modelSeries.flatMap((item) => item.values), 1);
  const niceMax = Math.max(1, Math.ceil(scaleMax * 1.18));
  const y = (value) => bottom - (value / niceMax) * (bottom - top);
  const points = data.map((item, index) => ({ x: x(index), y: y(item.requests || 0), value: item.requests || 0, date: item.date }));
  const totalLine = makeSmoothPath(points);
  const area = `${totalLine} L${points[points.length - 1].x.toFixed(1)} ${bottom} L${points[0].x.toFixed(1)} ${bottom} Z`;
  const barWidth = Math.min(34, Math.max(12, plotWidth / Math.max(data.length, 1) * 0.42));
  const bars = data.map((item, index) => {
    const value = item.requests || 0;
    const barY = y(value);
    return {
      date: item.date,
      label: trendDateLabel(item.date),
      value,
      x: x(index) - barWidth / 2,
      y: barY,
      width: barWidth,
      height: Math.max(2, bottom - barY),
      cx: x(index),
      labelY: Math.max(top + 12, barY - 10),
    };
  });
  const peak = points.reduce((best, item) => (item.value > best.value ? item : best), points[0]);
  const peakLabelOffset = peak.y < top + 42 ? 40 : -34;
  const peakLabel = {
    x: Math.max(padLeft + 28, Math.min(width - padRight - 34, peak.x)),
    y: Math.max(top + 18, Math.min(bottom - 20, peak.y + peakLabelOffset)),
  };
  const tickValues = [niceMax, Math.round(niceMax * 2 / 3), Math.round(niceMax / 3), 0]
    .filter((value, index, arr) => arr.indexOf(value) === index);
  const ticks = tickValues.map((value) => ({ value, y: y(value) }));
  const modelLines = modelSeries.map((item) => {
    const linePoints = item.values.map((value, index) => ({ x: x(index), y: y(value), value }));
    return {
      ...item,
      path: makeSmoothPath(linePoints),
      latest: item.values[item.values.length - 1] || 0,
    };
  });
  return {
    width,
    height,
    bars,
    area,
    totalLine,
    ticks,
    modelLines,
    avg,
    maxRequests,
    latestRequests: data[data.length - 1]?.requests || 0,
    peak,
    baselineY: y(avg),
    peakLabel,
  };
}

function AppBar({ activeSection, baseUrl, onNavigate, onLogout }) {
  return (
    <div className="appbar">
      <div className="identity">
        <img className="logo" src="/logo.png" alt="Kemo" />
        <h1>Kemo Adapter</h1>
      </div>
      <nav className="nav">
        {NAV_ITEMS.map(([id, label]) => (
          <button
            type="button"
            className={`nav-btn${activeSection === id ? ' active' : ''}`}
            data-section={id}
            key={id}
            onClick={() => onNavigate(id)}
          >
            <span className="nav-dot" />
            {label}
          </button>
        ))}
      </nav>
      <div className="base-url-pill" title={baseUrl ? `${baseUrl}\n来自 provider.env，仅用于展示` : 'provider.env 中未配置 BASE_URL'}>
        <span>base_url</span>
        <b className="base-url-text">{baseUrl || '未配置'}</b>
      </div>
      <button type="button" className="logout-btn" onClick={onLogout} title="退出登录">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.3" strokeLinecap="round" strokeLinejoin="round" width="15" height="15">
          <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
          <polyline points="16 17 21 12 16 7"/>
          <line x1="21" y1="12" x2="9" y2="12"/>
        </svg>
      </button>
    </div>
  );
}

function Overview({ health, stats, statsPeriod, onStatsPeriodChange, trendEntries }) {
  const recentCalls = stats?.recent_calls || [];
  const trend = stats?.trend || [];
  const topModelSeries = useMemo(() => buildTopModelSeries(trend, trendEntries || []), [trend, trendEntries]);
  const trendVisual = useMemo(() => buildTrendVisual(trend, topModelSeries), [trend, topModelSeries]);
  const latencyDelta = stats?.latency_delta_ms == null
    ? '--'
    : `${stats.latency_delta_ms > 0 ? '+' : ''}${stats.latency_delta_ms}ms`;
  const errorOpen = stats?.error_open_count == null ? '--' : `${stats.error_open_count} open`;

  return (
    <section className="section active" id="overview">
      <div className="hero-grid">
        <article className="hero-card card-hover">
          <span className="chip blue">OpenAI-compatible gateway</span>
          <h2 className="hero-title">LLM routing console.</h2>
          <p className="hero-desc">统一接入 Provider、模型别名、API Key 鉴权、Token 统计与调用日志。</p>
          <div className="hero-meta">
            <span className={`chip${(health?.providers_online || 0) > 0 ? '' : ' warn'}`}>registry: {health?.providers_online ?? 0} providers</span>
            <span className={`chip${health?.server_version ? '' : ' warn'}`}>{health?.server_version ? `server: ${health.server_version}` : 'server.py pending'}</span>
            <span className={`chip${health?.quota_enabled ? '' : ' warn'}`}>{health?.quota_enabled ? 'quota: live' : 'quota: pending'}</span>
          </div>
        </article>
        <aside className="summary-card">
          <div className="summary-top">
            <div><span>Gateway health</span><strong>Runtime Snapshot</strong></div>
            <Badge tone="ok">Live</Badge>
          </div>
          <div className="ring-row">
            <div className="ring">
              <div className="ring-inner">{health?.health_score ?? '--'}<small>score</small></div>
            </div>
            <div className="summary-list">
              <div className="summary-item"><span>Provider online</span><b>{health ? `${health.providers_online || 0} / ${health.providers_total || 0}` : '--'}</b></div>
              <div className="summary-item"><span>Exposed models</span><b>{health ? `${health.models_visible || health.models_exposed || 0} visible` : '--'}</b></div>
              <div className="summary-item"><span>Error rate</span><b>{fmtPct(health?.error_rate_pct)}</b></div>
            </div>
          </div>
        </aside>
      </div>

      <div className="metric-grid">
        <MetricCard label="请求数" delta={<Delta value={stats?.request_delta_pct} />} value={fmtNum(stats?.request_count)} foot="OpenAI 兼容请求进入网关的有效调用。" />
        <MetricCard tone="orange" label="Token 消耗" delta={<Delta value={stats?.token_delta_pct} />} value={fmtNum(stats?.token_total)} foot="prompt + completion + cache + reasoning。" />
        <MetricCard tone="green" label="平均延迟" delta={<Delta>{latencyDelta}</Delta>} value={fmtMs(stats?.avg_latency_ms)} foot="provider API 调用与响应归一化均值。" />
        <MetricCard tone="pink" label="错误率" delta={<Delta>{errorOpen}</Delta>} value={fmtPct(stats?.error_rate_pct)} foot="超时 · 鉴权 · 限流错误汇总。" />
      </div>

      <div className="grid">
        <article className="panel span-12 accent trend-panel">
          <div className="panel-head">
            <div><h3 className="panel-title">请求趋势</h3><p className="panel-sub">请求柱状、总量曲线、前三模型与平均基准线。</p></div>
            <Select value={statsPeriod} options={DASHBOARD_PERIOD_OPTIONS} onChange={onStatsPeriodChange} />
          </div>
          <div className="trend-stat-row">
            <div><span>最新请求</span><b>{fmtNum(trendVisual.latestRequests)}</b></div>
            <div><span>峰值</span><b>{fmtNum(trendVisual.maxRequests)}</b></div>
            <div><span>平均基准</span><b>{fmtNum(Math.round(trendVisual.avg))}</b></div>
          </div>
          <div className="trend-chart-shell">
            <svg className="line-chart trend-chart" viewBox={`0 0 ${trendVisual.width} ${trendVisual.height}`} aria-label="请求趋势图">
              <defs>
                <linearGradient id="areaBlue" x1="0" x2="0" y1="0" y2="1">
                  <stop offset="0%" stopColor="#3468ff" stopOpacity=".30" />
                  <stop offset="100%" stopColor="#3468ff" stopOpacity="0" />
                </linearGradient>
                <linearGradient id="barBlue" x1="0" x2="0" y1="0" y2="1">
                  <stop offset="0%" stopColor="#3468ff" stopOpacity=".88" />
                  <stop offset="100%" stopColor="#9eb6ff" stopOpacity=".28" />
                </linearGradient>
                <filter id="lineGlow" x="-20%" y="-20%" width="140%" height="140%">
                  <feDropShadow dx="0" dy="8" stdDeviation="8" floodColor="#3468ff" floodOpacity=".20" />
                </filter>
              </defs>
              {trendVisual.ticks.map((tick) => (
                <g key={tick.value}>
                  <line className="axis-line" x1="54" x2="692" y1={tick.y} y2={tick.y} />
                  <text className="axis-number" x="16" y={tick.y + 4}>{fmtNum(tick.value)}</text>
                </g>
              ))}
              <line className="trend-baseline" x1="54" x2="692" y1={trendVisual.baselineY} y2={trendVisual.baselineY} />
              <text className="baseline-label" x="610" y={trendVisual.baselineY - 8}>avg {fmtNum(Math.round(trendVisual.avg))}</text>
              {trendVisual.bars.map((bar, index) => (
                <g key={bar.date || index} className="trend-bar-group">
                  <rect className="trend-bar" x={bar.x} y={bar.y} width={bar.width} height={bar.height} rx="7" />
                  {trend.length <= 14 && bar.value > 0 ? <text className="bar-value" x={bar.cx} y={bar.labelY}>{fmtNum(bar.value)}</text> : null}
                </g>
              ))}
              <path className="chart-area" d={trendVisual.area} />
              {trendVisual.modelLines.map((line) => (
                <path key={line.model} className="chart-line-model" d={line.path} stroke={line.color} />
              ))}
              <path className="chart-line-a" d={trendVisual.totalLine} filter="url(#lineGlow)" />
              {trendVisual.bars.map((bar, index) => (
                <circle key={`${bar.date || index}-dot`} className="trend-dot" cx={bar.cx} cy={bar.y} r={bar.value > 0 ? 3.8 : 2.4} />
              ))}
              {trendVisual.bars.map((bar, index) => (
                <text key={`${bar.date || index}-axis`} className="x-axis-label" x={bar.cx} y="238">{bar.label}</text>
              ))}
              {trendVisual.peak && trendVisual.peakLabel ? (
                <g className="trend-peak-svg" transform={`translate(${trendVisual.peakLabel.x} ${trendVisual.peakLabel.y})`}>
                  <rect x="-25" y="-17" width="50" height="34" rx="17" />
                  <text className="trend-peak-value" y="-2">{fmtNum(trendVisual.peak.value)}</text>
                  <text className="trend-peak-date" y="11">{trendDateLabel(trendVisual.peak.date)}</text>
                </g>
              ) : null}
            </svg>
          </div>
          <div className="trend-legend">
            <span className="legend-item total"><i />总请求曲线</span>
            <span className="legend-item bars"><i />请求柱</span>
            {trendVisual.modelLines.length ? trendVisual.modelLines.map((item) => (
              <span className="legend-item model" key={item.model}>
                <i style={{ background: item.color }} />
                <b>{item.model}</b>
                <em>{fmtNum(item.total)} req</em>
              </span>
            )) : <span className="legend-empty">暂无模型曲线</span>}
          </div>
        </article>

        <article className="panel span-12">
          <div className="panel-head">
            <div><h3 className="panel-title">最近调用</h3><p className="panel-sub">最新 5 条请求记录 · 实时。</p></div>
            <Badge tone="ok">live</Badge>
          </div>
          <div className="table-wrap" style={{ border: 'none', borderRadius: 14, background: 'transparent', marginTop: 2 }}>
            <table className="calls-table">
              <thead><tr><th>ID</th><th>Model</th><th>Latency</th><th>Tokens</th><th>Status</th></tr></thead>
              <tbody>
                {recentCalls.length ? recentCalls.slice(0, 5).map((call) => {
                  const hasError = Boolean(call.error);
                  return (
                    <tr className={hasError ? 'call-err' : ''} key={call.request_id || `${call.model}-${call.latency_ms}`}>
                      <td className="mono" style={{ fontSize: 11, color: hasError ? 'var(--pink)' : 'var(--blue)' }}>{(call.request_id || '--').slice(0, 14)}</td>
                      <td><b>{call.model || '--'}</b></td>
                      <td>{fmtMs(call.latency_ms)}</td>
                      <td>{call.total_tokens != null ? fmtNum(call.total_tokens) : '—'}</td>
                      <td><Badge tone={hasError ? 'bad' : 'ok'}>{hasError ? 'error' : 'ok'}</Badge></td>
                    </tr>
                  );
                }) : <EmptyRow colSpan={5} children="暂无调用记录" />}
              </tbody>
            </table>
          </div>
        </article>
      </div>
    </section>
  );
}

function Providers({ providers, onToggleProvider }) {
  return (
    <section className="section active" id="providers">
      <div className="grid">
        <article className="panel span-12 provider-registry">
          <div className="panel-head"><div><h3 className="panel-title">Provider Registry</h3><p className="panel-sub">统一注册 · 独立适配 · 按 capability 暴露实例。</p></div></div>
          <div className="table-wrap">
            <table>
              <thead><tr><th>厂商</th><th>模块</th><th>Base URL</th><th>能力</th><th>状态</th><th>总开关</th></tr></thead>
              <tbody>
                {providers.length ? providers.map((provider) => (
                  <tr key={provider.name}>
                    <td><b>{provider.name}</b></td>
                    <td className="mono">provider/{provider.name}</td>
                    <td className="mono">{provider.base_url || '—'}</td>
                    <td>
                      {(provider.capabilities || []).length
                        ? provider.capabilities.map((capability) => <Badge tone="blue" key={capability}>{capability}</Badge>)
                        : <span className="badge" style={{ opacity: 0.4 }}>—</span>}
                    </td>
                    <td><Badge tone={provider.enabled ? 'ok' : 'warn'}>{provider.enabled ? '启用' : '已禁用'}</Badge></td>
                    <td>
                      <button type="button" className={`pill-tag${provider.enabled ? ' on' : ''}`} onClick={() => onToggleProvider(provider.name, !provider.enabled)}>
                        {provider.enabled ? '开' : '关'}
                      </button>
                    </td>
                  </tr>
                )) : <EmptyRow colSpan={6} children="暂无 provider" />}
              </tbody>
            </table>
          </div>
        </article>
      </div>
    </section>
  );
}

function Models({ models, modelTests, onToggleModel, onTestModel }) {
  return (
    <section className="section active" id="models">
      <article className="panel span-12">
        <div className="panel-head"><div><h3 className="panel-title">模型路由表</h3><p className="panel-sub">暴露名与 vendor model 分离 · 重命名 · 冲突检测 · 连通测试。</p></div></div>
        <div className="table-wrap">
          <table>
            <thead><tr><th>暴露模型名</th><th>Provider</th><th>厂商模型</th><th>能力</th><th>启用</th><th>测试</th></tr></thead>
            <tbody>
              {models.length ? models.map((model) => (
                <tr key={model.id}>
                  <td><span className="mono" style={{ fontSize: 12 }}>{model.id}</span></td>
                  <td>{model.provider}</td>
                  <td className="mono" style={{ fontSize: 12 }}>{model.model}</td>
                  <td>
                    {(() => {
                      const caps = model.capabilities || (model.capability ? [model.capability] : null);
                      if (!caps || !caps.length) return <span className="badge" style={{ opacity: 0.4 }}>—</span>;
                      return caps.map((cap) => (
                        <Badge tone="blue" key={cap}>{CAPABILITY_LABELS[cap] || cap}</Badge>
                      ));
                    })()}
                  </td>
                  <td>
                    <button type="button" className={`pill-tag${model.enabled ? ' on' : ''}`} onClick={() => onToggleModel(model.id, !model.enabled)}>
                      {model.enabled ? '开' : '关'}
                    </button>
                  </td>
                  <td style={{ whiteSpace: 'nowrap' }}>
                    <button
                      type="button"
                      className="btn"
                      style={{ minHeight: 30, padding: '0 12px', fontSize: 11.5 }}
                      onClick={() => onTestModel(model.id)}
                      disabled={modelTests[model.id]?.status === 'pending'}
                    >
                      {modelTests[model.id]?.status === 'pending' ? '...' : '测试'}
                    </button>{' '}
                    <TestPill test={modelTests[model.id]} />
                  </td>
                </tr>
              )) : <EmptyRow colSpan={6} children="暂无模型" />}
            </tbody>
          </table>
        </div>
      </article>
    </section>
  );
}

function Keys({ keysList, models, onToggleKeyModel }) {
  const allModelIds = useMemo(() => unique(models.map((model) => model.id)), [models]);

  return (
    <section className="section active" id="keys">
      <div className="grid">
        <article className="panel span-12">
          <div className="panel-head"><div><h3 className="panel-title">API 密钥 & 配额</h3><p className="panel-sub">管理密钥 · 模型白名单 · Token 余额。</p></div></div>
          <div className="table-wrap">
            <table>
              <thead><tr><th>密钥</th><th>名称</th><th>模型白名单</th><th>Token 余额</th><th>状态</th></tr></thead>
              <tbody>
                {keysList.length ? keysList.map((keyInfo) => {
                  const keyModels = keyInfo.models || [];
                  const options = unique([...allModelIds, ...keyModels]);
                  const used = keyInfo.quota?.used_tokens || 0;
                  const total = keyInfo.quota?.total_tokens || 0;
                  return (
                    <tr key={keyInfo.id}>
                      <td><span className="mono" style={{ fontSize: 12, background: 'var(--blue-soft)', padding: '2px 8px', borderRadius: 6, color: 'var(--blue)' }}>{keyInfo.id}</span></td>
                      <td>{keyInfo.name || '—'}</td>
                      <td>
                        <div className="pill-group">
                          {options.length ? options.map((modelId) => {
                            const enabled = keyModels.includes(modelId);
                            return (
                              <button type="button" className={`pill-tag${enabled ? ' on' : ''}`} key={modelId} onClick={() => onToggleKeyModel(keyInfo.id, modelId)}>
                                {modelId}
                              </button>
                            );
                          }) : <span style={{ color: 'var(--muted)' }}>—</span>}
                        </div>
                      </td>
                      <td><b>{fmtNum(total)}</b> <span style={{ color: 'var(--muted)', fontSize: 11 }}>/ {fmtNum(used)} used</span></td>
                      <td><Badge tone={keyInfo.enabled ? 'ok' : 'warn'}>{keyInfo.enabled ? '启用' : '已禁用'}</Badge></td>
                    </tr>
                  );
                }) : <EmptyRow colSpan={5} children="暂无密钥" />}
              </tbody>
            </table>
          </div>
          <div className="keys-summary-row">
            <div className="notice">四层鉴权：密钥存在、已启用、模型白名单命中、Token 配额未超限。额度实时追踪并写回 config/api_keys.json。</div>
            <div className="mini-stats">
              {keysList.length ? keysList.map((keyInfo) => {
                const total = keyInfo.quota?.total_tokens || 0;
                const used = keyInfo.quota?.used_tokens || 0;
                const pct = total > 0 ? Math.min((used / total) * 100, 100) : 0;
                return (
                  <div className="mini-stat" key={keyInfo.id}>
                    <span>{keyInfo.name || keyInfo.id}</span>
                    <b>{fmtNum(used)} / {fmtNum(total)}</b>
                    <div className="progress" style={{ marginTop: 8 }}><i style={{ width: `${pct}%` }} /></div>
                  </div>
                );
              }) : <div className="mini-stat"><span>—</span><b>暂无数据</b></div>}
            </div>
          </div>
        </article>
      </div>
    </section>
  );
}

function Logs({ logs, logStatus, logSearch, onLogStatusChange, onLogSearchChange }) {
  const entries = logs?.entries || [];
  const byKey = {};
  const byModel = {};
  let totalTokens = 0;

  for (const entry of entries) {
    const key = entry.key_id || 'unknown';
    byKey[key] ??= { reqs: 0, errors: 0, tokens: 0 };
    byKey[key].reqs += 1;
    if (entry.error) byKey[key].errors += 1;
    const tokens = entry.usage?.total_tokens || 0;
    byKey[key].tokens += tokens;
    const model = entry.model || 'unknown';
    byModel[model] = (byModel[model] || 0) + tokens;
    totalTokens += tokens;
  }

  const totalReqs = entries.length;
  const modelTotal = Object.values(byModel).reduce((sum, tokens) => sum + tokens, 0) || 1;

  return (
    <section className="section active" id="logs">
      <div className="grid">
        <article className="panel span-12">
          <div className="panel-head">
            <div><h3 className="panel-title">调用日志</h3><p className="panel-sub">密钥 Token 使用 · 模型使用 · 调用详情。</p></div>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <Select value={logStatus} options={LOG_STATUS_OPTIONS} onChange={onLogStatusChange} id="log-filter-status" />
              <input className="mini-select" style={{ width: 130, padding: '0 10px' }} placeholder="搜索密钥/模型" value={logSearch} onChange={(event) => onLogSearchChange(event.target.value)} />
            </div>
          </div>
          <div className="table-wrap">
            <table>
              <thead><tr><th>时间</th><th>密钥</th><th>模型</th><th>延迟</th><th>Token</th><th>状态</th></tr></thead>
              <tbody>
                {entries.length ? entries.map((entry, index) => {
                  const hasError = Boolean(entry.error);
                  return (
                    <tr className={hasError ? 'call-err' : ''} key={`${entry.timestamp || index}-${entry.request_id || entry.model || index}`}>
                      <td>{entry.timestamp ? entry.timestamp.slice(11, 19) : '--'}</td>
                      <td className="mono" style={{ fontSize: 12 }}>{(entry.key_id || '--').slice(0, 16)}</td>
                      <td>{entry.model || '--'}</td>
                      <td>{fmtMs(entry.latency_ms)}</td>
                      <td>{entry.usage?.total_tokens != null ? fmtNum(entry.usage.total_tokens) : '—'}</td>
                      <td><Badge tone={hasError ? 'bad' : 'ok'}>{hasError ? entry.error : '成功'}</Badge></td>
                    </tr>
                  );
                }) : <EmptyRow colSpan={6} children="暂无日志" />}
              </tbody>
            </table>
          </div>
        </article>
        <article className="panel span-6">
          <div className="panel-head"><div><h3 className="panel-title">密钥汇总</h3></div></div>
          <div className="mini-stats" style={{ gridTemplateColumns: '1fr' }}>
            {Object.entries(byKey).slice(0, 3).map(([key, value]) => (
              <div className="mini-stat" key={key}>
                <span>{key.slice(0, 16)}</span>
                <b>{fmtNum(value.tokens)}</b>
                <span style={{ fontWeight: 400, color: 'var(--muted)', fontSize: 11, marginTop: 2 }}>{value.reqs} 请求 · {value.errors} 错误</span>
              </div>
            ))}
            <div className="mini-stat"><span>总计</span><b>{fmtNum(totalTokens)}</b><span style={{ fontWeight: 400, color: 'var(--muted)', fontSize: 11, marginTop: 2 }}>{totalReqs} 请求</span></div>
          </div>
        </article>
        <article className="panel span-6">
          <div className="panel-head"><div><h3 className="panel-title">模型使用占比</h3></div></div>
          <div className="provider-list">
            {Object.entries(byModel).length ? Object.entries(byModel).map(([model, tokens]) => (
              <div className="provider-card" key={model}>
                <div className="provider-main"><b>{model}</b><span>{fmtNum(tokens)} tokens</span></div>
                <b>{Math.round(tokens / modelTotal * 100)}%</b>
              </div>
            )) : <div className="provider-card"><div className="provider-main"><b>—</b></div></div>}
          </div>
        </article>
      </div>
    </section>
  );
}

function Usage({ usage, usagePeriod, onUsagePeriodChange }) {
  const byProvider = usage?.by_provider || [];
  return (
    <section className="section active" id="usage">
      <div className="grid">
        <article className="panel span-4">
          <div className="panel-head"><div><h3 className="panel-title">API 总用量</h3><p className="panel-sub">周期汇总。</p></div><Badge tone="blue">统计</Badge></div>
          <div className="kpi-strip">
            <div className="kpi-tile"><span>总 Token</span><b>{fmtNum(usage?.total_tokens)}</b></div>
            <div className="kpi-tile"><span>请求数</span><b>{fmtNum(usage?.request_count)}</b></div>
            <div className="kpi-tile"><span>成功率</span><b>{fmtPct(usage?.success_rate_pct)}</b></div>
            <div className="kpi-tile"><span>活跃密钥</span><b>{usage?.active_keys ?? '--'}</b></div>
          </div>
        </article>
        <article className="panel span-4">
          <div className="panel-head"><div><h3 className="panel-title">延迟分布</h3></div></div>
          <div className="mini-stats">
            <div className="mini-stat"><span>P50</span><b>{fmtMs(usage?.latency?.p50_ms)}</b></div>
            <div className="mini-stat"><span>P95</span><b>{fmtMs(usage?.latency?.p95_ms)}</b></div>
            <div className="mini-stat"><span>P99</span><b>{fmtMs(usage?.latency?.p99_ms)}</b></div>
          </div>
        </article>
        <article className="panel span-4">
          <div className="panel-head"><div><h3 className="panel-title">缓存 & 推理</h3></div></div>
          <div className="mini-stats" style={{ gridTemplateColumns: '1fr' }}>
            <div className="mini-stat">
              <span>缓存命中</span>
              <b>{usage?.cache ? `${fmtNum(usage.cache.hit_tokens)} (${Math.round(usage.cache.hit_pct || 0)}%)` : '--'}</b>
              <div className="progress" style={{ marginTop: 8 }}><i style={{ width: `${Math.round(usage?.cache?.hit_pct || 0)}%` }} /></div>
            </div>
            <div className="mini-stat"><span>推理 Token</span><b>{fmtNum(usage?.reasoning_tokens)}</b><span style={{ fontWeight: 400, color: 'var(--muted)', fontSize: 11, marginTop: 2 }}>来自 thinking 模式</span></div>
          </div>
        </article>
        <article className="panel span-12 accent">
          <div className="panel-head">
            <div><h3 className="panel-title">Provider 精细化统计</h3><p className="panel-sub">请求数 · Token · 延迟 · 错误率。</p></div>
            <Select value={usagePeriod} options={USAGE_PERIOD_OPTIONS} onChange={onUsagePeriodChange} id="usage-period" />
          </div>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Provider</th><th>请求数</th><th>Token 总量</th><th>Prompt</th><th>Completion</th><th>缓存命中</th><th>推理 Token</th><th>延迟</th><th>错误率</th></tr></thead>
              <tbody>
                {byProvider.length ? byProvider.map((provider) => (
                  <tr key={provider.provider}>
                    <td><b>{provider.provider}</b></td>
                    <td>{fmtNum(provider.request_count)}</td>
                    <td>{fmtNum(provider.total_tokens)}</td>
                    <td>{fmtNum(provider.prompt_tokens)}</td>
                    <td>{fmtNum(provider.completion_tokens)}</td>
                    <td><Badge tone="ok">{Math.round(provider.cache_hit_pct || 0)}%</Badge></td>
                    <td>{fmtNum(provider.reasoning_tokens)}</td>
                    <td>{fmtMs(provider.avg_latency_ms)}</td>
                    <td>{fmtPct(provider.error_rate_pct)}</td>
                  </tr>
                )) : <EmptyRow colSpan={9} />}
              </tbody>
            </table>
          </div>
          <div style={{ marginTop: 14, display: 'flex', gap: 14, flexWrap: 'wrap' }}>
            {byProvider.map((provider) => (
              <div style={{ flex: 1, minWidth: 220 }} key={provider.provider}>
                <div className="provider-card" style={{ background: 'rgba(255,255,255,.06)', borderColor: 'rgba(255,255,255,.1)' }}>
                  <div className="provider-main"><b>{provider.provider} 用量明细</b></div>
                </div>
                <div className="provider-list" style={{ marginTop: 10 }}>
                  {(provider.models || []).length ? provider.models.map((model) => (
                    <div className="provider-card" style={{ background: 'rgba(255,255,255,.04)', borderColor: 'rgba(255,255,255,.08)' }} key={model.model}>
                      <div className="provider-main"><b>{model.model}</b><span>{fmtNum(model.total_tokens)} tok · {Math.round(model.pct || 0)}%</span></div>
                      <div style={{ width: 80 }}><div className="progress"><i style={{ width: `${Math.round(model.pct || 0)}%`, background: 'linear-gradient(90deg,var(--blue),var(--cyan))' }} /></div></div>
                    </div>
                  )) : <div className="provider-card"><div className="provider-main"><b>—</b></div></div>}
                </div>
              </div>
            ))}
          </div>
        </article>
      </div>
    </section>
  );
}

function Settings({ promptText, onPromptTextChange, onRefreshPrompt, onSavePrompt }) {
  return (
    <section className="section active" id="settings">
      <div className="grid">
        <article className="panel span-12">
          <div className="panel-head">
            <div><h3 className="panel-title">全局 Prompt</h3><p className="panel-sub">提示词基座 · system prompt 模板。</p></div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button type="button" className="btn" onClick={onRefreshPrompt}>刷新</button>
              <button type="button" className="btn primary" onClick={onSavePrompt}>保存</button>
            </div>
          </div>
          <textarea className="textarea-card settings-prompt" style={{ fontSize: 12 }} value={promptText} onChange={(event) => onPromptTextChange(event.target.value)} />
          <div style={{ marginTop: 10, display: 'flex', gap: 16, fontSize: 11.5, color: 'var(--muted)' }}>
            <span><span className="mono" style={{ fontSize: 11, background: 'rgba(0,0,0,.04)', padding: '1px 6px', borderRadius: 4 }}>config/global_prompt.md</span></span>
          </div>
        </article>
      </div>
    </section>
  );
}

export default function App() {
  const auth = useAuth();
  const [activeSection, setActiveSection] = useState(getInitialSection);
  const [toast, setToast] = useState({ message: '已完成', visible: false });
  const [health, setHealth] = useState(null);
  const [stats, setStats] = useState(null);
  const [providers, setProviders] = useState([]);
  const [models, setModels] = useState([]);
  const [keysList, setKeysList] = useState([]);
  const [logs, setLogs] = useState(null);
  const [trendEntries, setTrendEntries] = useState([]);
  const [usage, setUsage] = useState(null);
  const [promptText, setPromptText] = useState('loading...');
  const [statsPeriod, setStatsPeriod] = useState('today');
  const [usagePeriod, setUsagePeriod] = useState('today');
  const [logStatus, setLogStatus] = useState('all');
  const [logSearch, setLogSearch] = useState('');
  const [modelTests, setModelTests] = useState({});  // { [modelId]: { status, latencyMs, message, content, testedAt, requestId } }
  const toastTimer = useRef(null);

  const notify = useCallback((message) => {
    setToast({ message, visible: true });
    window.clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(() => {
      setToast((current) => ({ ...current, visible: false }));
    }, 1700);
  }, []);

  const loadHealth = useCallback(async () => {
    try {
      setHealth(await apiRequest('/health'));
    } catch (error) {
      console.error('health:', error);
      setHealth(null);
    }
  }, []);

  const loadStats = useCallback(async (period) => {
    try {
      setStats(await apiRequest(`/stats?period=${period}`));
    } catch (error) {
      console.error('stats:', error);
    }
  }, []);

  const loadProviders = useCallback(async () => {
    try {
      const data = await apiRequest('/providers');
      setProviders(data.providers || []);
    } catch (error) {
      console.error('providers:', error);
    }
  }, []);

  const loadModels = useCallback(async () => {
    try {
      const data = await apiRequest('/models');
      setModels(data.models || []);
    } catch (error) {
      console.error('models:', error);
    }
  }, []);

  const loadKeys = useCallback(async () => {
    try {
      const data = await apiRequest('/keys');
      setKeysList(data.keys || []);
    } catch (error) {
      console.error('keys:', error);
    }
  }, []);

  const loadLogs = useCallback(async (status, search) => {
    try {
      const params = new URLSearchParams();
      if (status && status !== 'all') params.set('status', status);
      if (search) params.set('q', search);
      params.set('limit', '50');
      setLogs(await apiRequest(`/logs?${params}`));
    } catch (error) {
      console.error('logs:', error);
    }
  }, []);

  const loadTrendEntries = useCallback(async (dates) => {
    const cleanDates = dates.filter(Boolean);
    if (!cleanDates.length) {
      setTrendEntries([]);
      return;
    }
    try {
      const results = await Promise.all(cleanDates.map(async (date) => {
        const data = await apiRequest(`/logs?date=${encodeURIComponent(date)}&limit=1000`);
        return (data.entries || []).map((entry) => ({ ...entry, _trendDate: date }));
      }));
      setTrendEntries(results.flat());
    } catch (error) {
      console.error('trend logs:', error);
      setTrendEntries([]);
    }
  }, []);

  const loadUsage = useCallback(async (period) => {
    try {
      setUsage(await apiRequest(`/usage?period=${period}`));
    } catch (error) {
      console.error('usage:', error);
    }
  }, []);

  const loadConfig = useCallback(async () => {
    try {
      const data = await apiRequest('/config');
      setPromptText(data.global_prompt || '');
    } catch (error) {
      console.error('config:', error);
    }
  }, []);

  useEffect(() => {
    const onHashChange = () => {
      const next = getInitialSection();
      setActiveSection(next);
    };
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, []);

  useEffect(() => {
    if (!auth.isAuthenticated) return;
    loadConfig();
  }, [auth.isAuthenticated, loadConfig]);

  useEffect(() => {
    if (!auth.isAuthenticated) return;
    loadStats(statsPeriod);
  }, [auth.isAuthenticated, statsPeriod, loadStats]);

  const trendDatesKey = useMemo(() => (stats?.trend || []).map((item) => item.date).filter(Boolean).join(','), [stats]);

  useEffect(() => {
    if (!auth.isAuthenticated || !trendDatesKey) {
      setTrendEntries([]);
      return;
    }
    loadTrendEntries(trendDatesKey.split(','));
  }, [auth.isAuthenticated, trendDatesKey, loadTrendEntries]);

  useEffect(() => {
    if (!auth.isAuthenticated) return;
    loadUsage(usagePeriod);
  }, [auth.isAuthenticated, usagePeriod, loadUsage]);

  useEffect(() => {
    if (!auth.isAuthenticated) return;
    const timer = window.setTimeout(() => loadLogs(logStatus, logSearch.trim()), 150);
    return () => window.clearTimeout(timer);
  }, [auth.isAuthenticated, logStatus, logSearch, loadLogs]);

  // 高频轮询：仪表盘数据 + 日志（每 10 秒自动刷新）
  useEffect(() => {
    if (!auth.isAuthenticated) return;
    const poll = () => {
      loadHealth();
      loadStats(statsPeriod);
      loadLogs(logStatus, logSearch.trim());
    };
    poll();
    const id = setInterval(poll, 10_000);
    return () => clearInterval(id);
  }, [auth.isAuthenticated, statsPeriod, logStatus, logSearch, loadHealth, loadStats, loadLogs]);

  // 低频轮询：Provider 注册表 + 模型路由表（每 30 秒）
  useEffect(() => {
    if (!auth.isAuthenticated) return;
    loadProviders();
    loadModels();
    const id = setInterval(() => {
      loadProviders();
      loadModels();
    }, 30_000);
    return () => clearInterval(id);
  }, [auth.isAuthenticated, loadProviders, loadModels]);

  // 独立低频：API 密钥（每 60 秒）
  useEffect(() => {
    if (!auth.isAuthenticated) return;
    loadKeys();
    const id = setInterval(() => loadKeys(), 60_000);
    return () => clearInterval(id);
  }, [auth.isAuthenticated, loadKeys]);

  function navigate(sectionId) {
    setActiveSection(sectionId);
    if (window.location.hash !== `#${sectionId}`) {
      window.history.replaceState(null, '', `#${sectionId}`);
    }
  }

  async function toggleProvider(name, enabled) {
    try {
      await apiRequest(`/providers/${name}/toggle`, { method: 'POST', body: JSON.stringify({ enabled }) });
      notify(`${name} ${enabled ? '已启用' : '已禁用'}`);
      await Promise.allSettled([loadProviders(), loadHealth()]);
    } catch (error) {
      notify(`操作失败: ${error.message}`);
    }
  }

  async function toggleModel(id, enabled) {
    try {
      await apiRequest(`/models/${id}/toggle`, { method: 'POST', body: JSON.stringify({ enabled }) });
      notify(`${id} ${enabled ? '已启用' : '已禁用'}`);
      await Promise.allSettled([loadModels(), loadHealth()]);
    } catch (error) {
      notify(`操作失败: ${error.message}`);
    }
  }

  async function testModel(id) {
    const requestId = Date.now();
    setModelTests((current) => ({
      ...current,
      [id]: { status: 'pending', requestId },
    }));
    try {
      const result = await apiRequest(`/models/${id}/test`, { method: 'POST' });
      setModelTests((current) => {
        if (current[id]?.requestId !== requestId) return current;
        const testedAt = new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        return {
          ...current,
          [id]: result.ok
            ? { status: 'success', latencyMs: result.latency_ms, content: result.content || '', testedAt }
            : { status: 'error', message: result.error || 'fail', testedAt },
        };
      });
    } catch (error) {
      setModelTests((current) => {
        if (current[id]?.requestId !== requestId) return current;
        const testedAt = new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        return {
          ...current,
          [id]: { status: 'error', message: error.message, testedAt },
        };
      });
    }
  }

  async function toggleKeyModel(keyId, modelId) {
    try {
      const keyInfo = keysList.find((item) => item.id === keyId);
      if (!keyInfo) return;
      const currentModels = keyInfo.models || [];
      const nextModels = currentModels.includes(modelId)
        ? currentModels.filter((item) => item !== modelId)
        : [...currentModels, modelId];
      await apiRequest(`/keys/${keyId}/models`, { method: 'POST', body: JSON.stringify({ models: nextModels }) });
      notify('模型白名单已更新');
      await loadKeys();
    } catch (error) {
      notify(`操作失败: ${error.message}`);
    }
  }

  async function saveGlobalPrompt() {
    try {
      await apiRequest('/config/global_prompt', { method: 'POST', body: JSON.stringify({ content: promptText }) });
      notify('已保存');
    } catch (error) {
      notify(`保存失败: ${error.message}`);
    }
  }

  async function refreshPrompt() {
    await loadConfig();
    notify('已刷新');
  }

  const activeView = {
    overview: <Overview health={health} stats={stats} statsPeriod={statsPeriod} onStatsPeriodChange={setStatsPeriod} trendEntries={trendEntries} />,
    providers: <Providers providers={providers} onToggleProvider={toggleProvider} />,
    models: <Models models={models} modelTests={modelTests} onToggleModel={toggleModel} onTestModel={testModel} />,
    keys: <Keys keysList={keysList} models={models} onToggleKeyModel={toggleKeyModel} />,
    logs: <Logs logs={logs} logStatus={logStatus} logSearch={logSearch} onLogStatusChange={setLogStatus} onLogSearchChange={setLogSearch} />,
    usage: <Usage usage={usage} usagePeriod={usagePeriod} onUsagePeriodChange={setUsagePeriod} />,
    settings: <Settings promptText={promptText} onPromptTextChange={setPromptText} onRefreshPrompt={refreshPrompt} onSavePrompt={saveGlobalPrompt} />,
  }[activeSection];

  return (
    <AuthGate auth={auth}>
      <div className="page">
        <div className="shell glass">
          <AppBar
            activeSection={activeSection}
            baseUrl={health?.base_url || ''}
            onNavigate={navigate}
            onLogout={auth.logout}
          />
          <main className="content">{activeView}</main>
        </div>
      </div>
      <div className={`toast${toast.visible ? ' show' : ''}`}>{toast.message}</div>
    </AuthGate>
  );
}
