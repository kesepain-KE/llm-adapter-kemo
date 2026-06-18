import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { apiRequest } from './api';
import Select from './components/Select';
import { fmtMs, fmtNum, fmtPct, unique } from './utils';

const NAV_ITEMS = [
  ['overview', '仪表盘'],
  ['providers', 'Provider'],
  ['models', '模型'],
  ['keys', 'API 密钥'],
  ['logs', '调用日志'],
  ['usage', '用量统计'],
  ['settings', '配置'],
];

const PERIOD_OPTIONS = [
  { value: 'today', label: '今日' },
  { value: '7d', label: '7 天' },
  { value: '30d', label: '30 天' },
];

const LOG_STATUS_OPTIONS = [
  { value: 'all', label: '全部' },
  { value: 'ok', label: '成功', tone: 'ok' },
  { value: 'error', label: '错误', tone: 'bad' },
];

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

function buildTrendPaths(data) {
  if (!data?.length) {
    return { area: '', lineA: '', lineB: '', maxRequests: '--' };
  }
  const width = 620;
  const padLeft = 22;
  const padRight = 20;
  const top = 30;
  const bottom = 175;
  const x = (i) => padLeft + (i / Math.max(data.length - 1, 1)) * (width - padLeft - padRight);
  const maxRequests = Math.max(...data.map((item) => item.requests || 0), 1);
  const y = (value) => bottom - (value / maxRequests) * (bottom - top);
  const lineA = data.map((item, index) => `${index === 0 ? 'M' : 'L'}${x(index).toFixed(0)} ${y(item.requests || 0).toFixed(0)}`).join(' ');
  const area = `${lineA} L${x(data.length - 1).toFixed(0)} ${bottom} L${padLeft.toFixed(0)} ${bottom} Z`;
  const hasCache = data.some((item) => item.cache_hit != null);
  const maxCache = Math.max(...data.map((item) => item.cache_hit || 0), 1);
  const lineB = hasCache
    ? data.map((item, index) => `${index === 0 ? 'M' : 'L'}${x(index).toFixed(0)} ${y((item.cache_hit || 0) * maxRequests / maxCache).toFixed(0)}`).join(' ')
    : '';
  return { area, lineA, lineB, maxRequests: fmtNum(maxRequests) };
}

function AppBar({ activeSection, baseUrl, globalSearch, onGlobalSearch, onNavigate }) {
  return (
    <div className="appbar">
      <div className="identity">
        <div className="logo">K</div>
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
      <label className="search">
        <input value={globalSearch} onChange={onGlobalSearch} placeholder="搜索..." autoComplete="off" />
      </label>
      <div className="base-url-pill" title={baseUrl ? `${baseUrl}\n来自 provider.env，仅用于展示` : 'provider.env 中未配置 BASE_URL'}>
        <span>base_url</span>
        <b className="base-url-text">{baseUrl || '未配置'}</b>
      </div>
    </div>
  );
}

function Overview({ health, stats, statsPeriod, onStatsPeriodChange }) {
  const trendPaths = useMemo(() => buildTrendPaths(stats?.trend || []), [stats]);
  const providerBreakdown = stats?.by_provider || [];
  const providerTotal = providerBreakdown.reduce((sum, item) => sum + (item.total_tokens || 0), 0) || 1;
  const pins = providerBreakdown.slice(0, 3).map((item) => `${Math.round((item.total_tokens || 0) / providerTotal * 100)}%`);
  const recentCalls = stats?.recent_calls || [];
  const trend = stats?.trend || [];
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
        <article className="panel span-3">
          <div className="panel-head">
            <div><h3 className="panel-title">Provider 分布</h3><p className="panel-sub">地域视角展示调用分布。</p></div>
            <Select value={statsPeriod} options={PERIOD_OPTIONS} onChange={onStatsPeriodChange} />
          </div>
          <div className="world">
            <svg viewBox="0 0 520 260" aria-hidden="true">
              <path d="M83 112c32-42 95-57 151-34 38 16 66 12 102-5 51-24 108-11 135 34 21 36-4 75-46 81-48 7-79-24-119-26-55-3-88 36-145 24-54-12-105-38-78-74Z" fill="rgba(23,23,23,.08)" />
              <path d="M120 129c30-18 72-22 107-11 44 14 68 33 118 20 31-8 65 1 84 24" fill="none" stroke="rgba(52,104,255,.22)" strokeWidth="2" strokeDasharray="6 8" />
            </svg>
            <span className="map-pin pin-a">{pins[0] || '—'}</span>
            <span className="map-pin pin-b">{pins[1] || '—'}</span>
            <span className="map-pin pin-c">{pins[2] || '—'}</span>
          </div>
        </article>

        <article className="panel span-9 accent">
          <div className="panel-head">
            <div><h3 className="panel-title">请求趋势</h3><p className="panel-sub">请求量与缓存命中。</p></div>
            <Select value={statsPeriod} options={PERIOD_OPTIONS} onChange={onStatsPeriodChange} />
          </div>
          <div style={{ position: 'relative' }}>
            <svg className="line-chart" viewBox="0 0 620 200" aria-label="请求趋势图">
              <defs>
                <linearGradient id="areaBlue" x1="0" x2="0" y1="0" y2="1">
                  <stop offset="0%" stopColor="#3468ff" stopOpacity=".42" />
                  <stop offset="100%" stopColor="#3468ff" stopOpacity="0" />
                </linearGradient>
              </defs>
              <path className="axis-line" d="M20 175H600M20 132H600M20 89H600M20 46H600" />
              <path className="chart-area" d={trendPaths.area} />
              <path className="chart-line-a" d={trendPaths.lineA} />
              <path className="chart-line-b" d={trendPaths.lineB} />
            </svg>
            <div className="tooltip-bubble mono" style={{ left: '49%', top: '38%' }}>{trendPaths.maxRequests}</div>
          </div>
          <div className="chart-axis-labels" style={{ gridTemplateColumns: `repeat(${Math.max(trend.length, 1)}, minmax(0, 1fr))` }}>
            {trend.map((item) => <span key={item.date}>{(item.date || '').slice(5) || '--'}</span>)}
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
                  <td>{model.capability ? <Badge tone="blue">{model.capability}</Badge> : <span className="badge" style={{ opacity: 0.4 }}>—</span>}</td>
                  <td>
                    <button type="button" className={`pill-tag${model.enabled ? ' on' : ''}`} onClick={() => onToggleModel(model.id, !model.enabled)}>
                      {model.enabled ? '开' : '关'}
                    </button>
                  </td>
                  <td>
                    <button type="button" className="btn" style={{ minHeight: 30, padding: '0 12px', fontSize: 11.5 }} onClick={() => onTestModel(model.id)}>
                      {modelTests[model.id] || '测试连通'}
                    </button>
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
            <Select value={usagePeriod} options={PERIOD_OPTIONS} onChange={onUsagePeriodChange} id="usage-period" />
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
  const [activeSection, setActiveSection] = useState(getInitialSection);
  const [globalSearch, setGlobalSearch] = useState('');
  const [toast, setToast] = useState({ message: '已完成', visible: false });
  const [health, setHealth] = useState(null);
  const [stats, setStats] = useState(null);
  const [providers, setProviders] = useState([]);
  const [models, setModels] = useState([]);
  const [keysList, setKeysList] = useState([]);
  const [logs, setLogs] = useState(null);
  const [usage, setUsage] = useState(null);
  const [promptText, setPromptText] = useState('loading...');
  const [statsPeriod, setStatsPeriod] = useState('today');
  const [usagePeriod, setUsagePeriod] = useState('today');
  const [logStatus, setLogStatus] = useState('all');
  const [logSearch, setLogSearch] = useState('');
  const [modelTests, setModelTests] = useState({});
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
    Promise.allSettled([
      loadHealth(),
      loadProviders(),
      loadModels(),
      loadKeys(),
      loadConfig(),
    ]);
  }, [loadHealth, loadProviders, loadModels, loadKeys, loadConfig]);

  useEffect(() => {
    loadStats(statsPeriod);
  }, [statsPeriod, loadStats]);

  useEffect(() => {
    loadUsage(usagePeriod);
  }, [usagePeriod, loadUsage]);

  useEffect(() => {
    const timer = window.setTimeout(() => loadLogs(logStatus, logSearch.trim()), 150);
    return () => window.clearTimeout(timer);
  }, [logStatus, logSearch, loadLogs]);

  function navigate(sectionId) {
    setActiveSection(sectionId);
    if (window.location.hash !== `#${sectionId}`) {
      window.history.replaceState(null, '', `#${sectionId}`);
    }
  }

  function handleGlobalSearch(event) {
    const value = event.target.value;
    setGlobalSearch(value);
    if (value.trim()) {
      notify(`搜索: ${value.trim()} (使用各 tab 内搜索框)`);
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
    setModelTests((current) => ({ ...current, [id]: '...' }));
    try {
      const result = await apiRequest(`/models/${id}/test`, { method: 'POST' });
      setModelTests((current) => ({
        ...current,
        [id]: result.ok ? `✓ ${fmtMs(result.latency_ms)}` : `× ${result.error || 'fail'}`,
      }));
    } catch (error) {
      setModelTests((current) => ({ ...current, [id]: `× ${error.message.slice(0, 20)}` }));
    }
    window.setTimeout(() => {
      setModelTests((current) => {
        const next = { ...current };
        delete next[id];
        return next;
      });
    }, 2500);
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
    overview: <Overview health={health} stats={stats} statsPeriod={statsPeriod} onStatsPeriodChange={setStatsPeriod} />,
    providers: <Providers providers={providers} onToggleProvider={toggleProvider} />,
    models: <Models models={models} modelTests={modelTests} onToggleModel={toggleModel} onTestModel={testModel} />,
    keys: <Keys keysList={keysList} models={models} onToggleKeyModel={toggleKeyModel} />,
    logs: <Logs logs={logs} logStatus={logStatus} logSearch={logSearch} onLogStatusChange={setLogStatus} onLogSearchChange={setLogSearch} />,
    usage: <Usage usage={usage} usagePeriod={usagePeriod} onUsagePeriodChange={setUsagePeriod} />,
    settings: <Settings promptText={promptText} onPromptTextChange={setPromptText} onRefreshPrompt={refreshPrompt} onSavePrompt={saveGlobalPrompt} />,
  }[activeSection];

  return (
    <>
      <div className="page">
        <div className="shell glass">
          <AppBar
            activeSection={activeSection}
            baseUrl={health?.base_url || ''}
            globalSearch={globalSearch}
            onGlobalSearch={handleGlobalSearch}
            onNavigate={navigate}
          />
          <main className="content">{activeView}</main>
        </div>
      </div>
      <div className={`toast${toast.visible ? ' show' : ''}`}>{toast.message}</div>
    </>
  );
}
