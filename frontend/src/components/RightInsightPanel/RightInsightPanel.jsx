import React, { useState } from 'react';
import {
  TrendingUp, PieChart, FileText, FileSearch, ExternalLink, Gavel, Minus,
  PanelRightClose, Info, ShieldCheck, AlertTriangle, BarChart3, Layers,
  ChevronDown, Clock,
} from 'lucide-react';
import clsx from 'clsx';
import {
  Chart as ChartJS, CategoryScale, LinearScale, PointElement, LineElement,
  ArcElement, BarElement, RadarController, RadialLinearScale, Tooltip, Legend, Filler,
} from 'chart.js';
import { Line, Doughnut, Bar, Radar } from 'react-chartjs-2';
import { useChartColors, useTheme } from '../../theme';

ChartJS.register(
  CategoryScale, LinearScale, PointElement, LineElement, ArcElement,
  BarElement, RadarController, RadialLinearScale, Tooltip, Legend, Filler,
);

// Canvas 里的颜色必须给具体色值（Tailwind class 在 <canvas> 里不生效），
// 所以从 CSS 变量现取一份，而不是在 JS 里另抄一套配色。theme 变化时
// useChartColors 重新求值，图表跟着换明暗。
const scaleOptionsFor = (C) => ({
  x: { ticks: { color: C.axis, maxTicksLimit: 8 }, grid: { color: C.grid } },
  y: { ticks: { color: C.axis }, grid: { color: C.grid } },
});

const optionsFor = (C) => ({
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: { labels: { color: C.axis, boxWidth: 12, font: { size: 11 } } },
    tooltip: {
      backgroundColor: C.tooltipBg,
      borderColor: C.tooltipBorder,
      borderWidth: 1,
      titleColor: C.tooltipTitle,
      bodyColor: C.tooltipBody,
      padding: 10,
    },
  },
});

// ── 统计工具 ────────────────────────────────────────────────────────

/**
 * Wilson score interval：二项比例的置信区间。
 *
 * 情绪占比是比例不是计数，"负面 34%" 在 n=12 和 n=1200 里的可信度完全
 * 不同。正态近似（p ± 1.96·√(p(1-p)/n)）在小样本或 p 接近 0/1 时会给出
 * 越界的区间，Wilson 用分母重参数化避免了这一点，是小样本比例的标配做法。
 * z=1.96 对应 95% 置信水平。
 */
function wilsonCI(successes, n, z = 1.96) {
  if (!n || n <= 0) return null;
  const p = Math.min(Math.max(successes / n, 0), 1);
  const denom = 1 + (z * z) / n;
  const center = (p + (z * z) / (2 * n)) / denom;
  const margin = (z / denom) * Math.sqrt((p * (1 - p)) / n + (z * z) / (4 * n * n));
  return {
    lower: Math.max(0, center - margin) * 100,
    upper: Math.min(1, center + margin) * 100,
  };
}

const fmtPct = (v) => `${Number(v || 0).toFixed(1)}%`;
const fmtNum = (v, d = 2) => (typeof v === 'number' ? v.toFixed(d) : String(v ?? '—'));

// ── 面板外壳 ────────────────────────────────────────────────────────

export default function RightInsightPanel({ activeTab, onTabChange, analysisData, onCollapse }) {
  const { theme } = useTheme();
  const C = useChartColors(theme);
  const tabs = [
    { id: 'verdict', label: '终裁', icon: <Gavel size={14} /> },
    { id: 'trend', label: '趋势', icon: <TrendingUp size={14} /> },
    { id: 'sentiment', label: '情感', icon: <PieChart size={14} /> },
    { id: 'keywords', label: '热词', icon: <FileText size={14} /> },
    { id: 'evidence', label: '证据', icon: <FileSearch size={14} /> },
  ];

  return (
    <div className="h-full flex flex-col bg-panel">
      <div className="h-14 border-b border-border flex items-center pl-4 pr-2 shrink-0 gap-1 bg-app/50 backdrop-blur-sm">
        <div className="flex items-center gap-1 overflow-x-auto custom-scrollbar flex-1">
          {tabs.map(tab => (
            <button
              key={tab.id}
              onClick={() => onTabChange(tab.id)}
              className={clsx(
                "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm transition-colors whitespace-nowrap",
                activeTab === tab.id
                  ? "bg-active text-text-main font-medium"
                  : "text-text-secondary hover:text-text-main hover:bg-hover"
              )}
            >
              {tab.icon}
              {tab.label}
            </button>
          ))}
        </div>
        {onCollapse && (
          <button
            onClick={onCollapse}
            title="收起右侧栏（可拖回）"
            className="p-2 rounded-md hover:bg-hover text-text-secondary hover:text-text-main transition-colors shrink-0"
          >
            <PanelRightClose size={16} />
          </button>
        )}
      </div>

      <div className="flex-1 overflow-y-auto p-4 custom-scrollbar">
        {activeTab === 'verdict' && <VerdictContent data={analysisData} />}
        {activeTab === 'trend' && <TrendContent data={analysisData} />}
        {activeTab === 'sentiment' && <SentimentContent data={analysisData} />}
        {activeTab === 'keywords' && <KeywordContent data={analysisData} />}
        {activeTab === 'evidence' && <EvidenceContent data={analysisData} />}
      </div>
    </div>
  );
}

function EmptyHint({ text }) {
  return (
    <div className="bg-card border border-border rounded-xl p-8 flex flex-col items-center justify-center text-text-secondary">
      <Minus size={24} className="mb-2 opacity-30" />
      <span className="text-xs text-center leading-relaxed">{text}</span>
    </div>
  );
}

function StatRow({ items }) {
  return (
    <div className="grid grid-cols-2 gap-2">
      {items.map(({ label, value }) => (
        <div key={label} className="bg-card border border-border rounded-xl p-3">
          <div className="text-[10px] text-text-secondary mb-1">{label}</div>
          <div className="text-sm font-medium text-text-main tabular-nums">{value}</div>
        </div>
      ))}
    </div>
  );
}

function Section({ title, icon, children, aside, action }) {
  return (
    <div className="bg-card border border-border rounded-xl p-4">
      <div className="flex items-center justify-between mb-2">
        <h4 className="text-xs font-semibold text-text-secondary flex items-center gap-1.5">
          {icon}{title}
        </h4>
        <div className="flex items-center gap-2">
          {aside}
          {action}
        </div>
      </div>
      {children}
    </div>
  );
}

// 方法论说明块。右侧五个 Tab 讲的是"结论"，但结论的可信度取决于样本与
// 方法，每个 Tab 都必须把口径交代清楚，否则数字无从复核。
function MethodNote({ children }) {
  return (
    <div className="rounded-xl border border-border bg-soft p-3 flex gap-2">
      <Info size={13} className="text-accent shrink-0 mt-0.5" />
      <div className="text-[11px] text-text-secondary leading-relaxed space-y-1">
        {children}
      </div>
    </div>
  );
}

function Disclaimer({ children }) {
  return (
    <div className="rounded-xl border border-warning/25 bg-warning/[0.06] p-3 flex gap-2">
      <AlertTriangle size={13} className="text-warning shrink-0 mt-0.5" />
      <div className="text-[11px] text-warning/90 leading-relaxed">{children}</div>
    </div>
  );
}

const TREND_LABELS = {
  positive: '积极', negative: '消极', neutral: '平稳', unknown: '未知',
};

// 按天真序列里可切换的维度。全部是后端按本批样本算出的真实日度量，
// 不含任何插值或拟合填充。
const DAILY_METRICS = [
  { key: 'sentiment_index', label: '情绪指数', color: 'accent', unit: '' },
  { key: 'negative_share', label: '负面占比', color: 'danger', unit: '%' },
  { key: 't1_share', label: 'T1 权威占比', color: 'success', unit: '%' },
  { key: 'volume', label: '声量', color: 'blue', unit: ' 条' },
];

// ── 终裁 ────────────────────────────────────────────────────────────

function VerdictContent({ data }) {
  const { theme } = useTheme();
  const C = useChartColors(theme);
  const verdict = data?.verdict;
  if (!verdict || !verdict.stance) {
    return <EmptyHint text="暂无终裁数据，请先完成一次分析" />;
  }

  const stanceCls = verdict.stance === 'negative' ? 'text-danger'
    : verdict.stance === 'positive' ? 'text-success' : 'text-text-main';

  // 终裁的说服力完全建立在样本上：多少条数据、都是谁说的。追问轮产生的
  // 终裁样本与首轮相同，也要说明这一点，否则用户会以为是新采集的数据。
  const total = data?.total_news || 0;
  const tierDist = data?.collect_meta?.tier_distribution || {};

  return (
    <div className="space-y-4">
      <div className="bg-card border border-border rounded-xl p-4">
        <div className="flex items-center justify-between mb-3">
          <span className="text-xs text-text-secondary">裁判立场</span>
          <span className={clsx("text-lg font-semibold", stanceCls)}>
            {TREND_LABELS[verdict.stance] || verdict.stance}
          </span>
        </div>
        <div className="flex items-center justify-between mb-3">
          <span className="text-xs text-text-secondary">置信度</span>
          <span className="text-sm text-text-main tabular-nums">
            {Math.round((verdict.confidence || 0) * 100)}%
          </span>
        </div>
        <div className="w-full h-1.5 bg-soft rounded-full overflow-hidden">
          <div
            className={clsx("h-full rounded-full",
              verdict.stance === 'negative' ? 'bg-danger'
                : verdict.stance === 'positive' ? 'bg-success' : 'bg-text-secondary')}
            style={{ width: `${Math.round((verdict.confidence || 0) * 100)}%` }}
          />
        </div>
        <p className="text-[10px] text-text-secondary mt-2 leading-relaxed">
          置信度由裁判模型自评，反映其对双方论据一致性的判断，不是统计显著性。
        </p>
      </div>

      <Section title="裁定样本口径" icon={<Layers size={12} />}>
        <div className="space-y-2">
          <div className="flex justify-between text-[11px]">
            <span className="text-text-secondary">纳入分析的新闻样本</span>
            <span className="text-text-main tabular-nums">{total} 条</span>
          </div>
          {Object.keys(tierDist).length > 0 && (
            <div className="flex gap-1.5 h-1.5 rounded-full overflow-hidden bg-soft">
              {['1', '2', '3', '4'].map(t => {
                const cnt = Number(tierDist[t] || 0);
                if (!cnt || !total) return null;
                return (
                  <div
                    key={t}
                    className="h-full"
                    style={{
                      width: `${(cnt / total) * 100}%`,
                      backgroundColor: tierColors(C)[t],
                    }}
                    title={`${TIER_LABELS[t]}：${cnt} 条`}
                  />
                );
              })}
            </div>
          )}
          {Object.keys(tierDist).length > 0 && (
            <div className="flex flex-wrap gap-x-3 gap-y-1 text-[10px] text-text-secondary">
              {['1', '2', '3', '4'].map(t => (
                <span key={t} className="flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: tierColors(C)[t] }} />
                  {TIER_LABELS[t]} {tierDist[t] || 0}
                </span>
              ))}
            </div>
          )}
        </div>
      </Section>

      {verdict.summary && (
        <Section title="裁定理由">
          <p className="text-xs text-text-main/90 leading-relaxed">{verdict.summary}</p>
        </Section>
      )}

      {verdict.key_disagreements?.length > 0 && (
        <Section title="核心分歧">
          <ul className="space-y-1.5">
            {verdict.key_disagreements.map((d, i) => (
              <li key={i} className="text-xs text-text-main/90 leading-relaxed flex gap-2">
                <span className="text-text-secondary shrink-0">{i + 1}.</span>
                <span>{d}</span>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {(verdict.red_strongest || verdict.blue_strongest) && (
        <Section title="双方最有力论据">
          <div className="space-y-2">
            {verdict.red_strongest && (
              <div className="border-l-2 border-danger pl-2">
                <div className="text-[10px] text-danger mb-0.5">红方 · 危机视角</div>
                <p className="text-xs text-text-main/90 leading-relaxed">{verdict.red_strongest}</p>
              </div>
            )}
            {verdict.blue_strongest && (
              <div className="border-l-2 border-agent-trend pl-2">
                <div className="text-[10px] text-agent-trend mb-0.5">蓝方 · 理性视角</div>
                <p className="text-xs text-text-main/90 leading-relaxed">{verdict.blue_strongest}</p>
              </div>
            )}
          </div>
        </Section>
      )}

      {verdict.recommendation && (
        <Section title="行动建议">
          <p className="text-xs text-text-main/90 leading-relaxed">{verdict.recommendation}</p>
        </Section>
      )}

      <MethodNote>
        <p>终裁由裁判模型在读完红蓝双方全部发言后作出，流程为：立论 → 追问引导 → 反驳 → 终裁。</p>
        <p>它是两个对抗视角的收敛结果，不是事实认定；涉及具体决策时请以原始信源（见"证据"Tab）为准。</p>
      </MethodNote>

      <Disclaimer>
        本结论基于公开网络信息的舆情研判，不构成投资、法律或商业决策建议。
      </Disclaimer>
    </div>
  );
}

// ── 趋势 ────────────────────────────────────────────────────────────

const MODEL_META = {
  prophet: {
    label: 'Prophet 时序模型',
    desc: 'Facebook Prophet 拟合趋势项 + 年度季节性，changepoint_prior_scale=0.05。' +
          '不确定性区间来自模型对趋势、季节性与观测噪声的分解，随外推步长自然变宽。',
  },
  baseline: {
    label: '线性回归基线',
    desc: 'Prophet 不可用时退化为对时间索引做最小二乘直线拟合，' +
          '区间按残差标准差 ×1.96 构造，是恒定宽度的对称带，不含季节性成分——' +
          '因此该模式下的区间语义与 Prophet 不同，只应作方向性参考。',
  },
  unknown: {
    label: '模型未标注',
    desc: '后端未返回模型类型，无法说明预测值的构造方式。',
  },
};
/**
 * 多维舆情画像 + 按天真实序列 + 情绪指数预测。
 *
 * 单一"情绪指数"读不出一次舆情的性质：同样的均值可能来自少量极端负面，
 * 也可能来自温和的全面偏负，两者风险完全不同。所以先给互相独立的九个
 * 维度（全部由本批样本算出，见 sentiment_indicators.py），再看时序，最后
 * 才是预测。任何一环样本不足时明确说"本次运行未取得"，不补假数据。
 */
function TrendContent({ data }) {
  const { theme } = useTheme();
  const C = useChartColors(theme);
  const [metric, setMetric] = useState('sentiment_index');
  const [showBasis, setShowBasis] = useState(false);

  const predictions = data?.predictions || [];
  const summary = data?.trend_summary || {};
  const indicators = summary.indicators || {};
  const dims = Array.isArray(indicators.dimensions) ? indicators.dimensions : [];
  const daily = (Array.isArray(indicators.daily) ? indicators.daily : [])
    .filter(d => d && d.date && d.date !== 'unknown');
  const sample = indicators.sample || {};
  const model = MODEL_META[summary.model_type] || MODEL_META.unknown;
  const direction = summary.trend_direction || data?.trend_direction || 'unknown';
  const confidence = summary.confidence ?? data?.confidence ?? 0;
  const forecastFeasible = summary.forecast_feasible !== false && daily.length >= 2;

  const radarData = dims.length > 0 ? {
    labels: dims.map(d => d.label),
    datasets: [{
      label: '归一化值（0-100）',
      data: dims.map(d => d.value),
      borderColor: C.accent,
      backgroundColor: C.accentSoft,
      pointBackgroundColor: C.accent,
      pointRadius: 2.5,
      borderWidth: 1.5,
    }],
  } : null;

  const activeMetric = DAILY_METRICS.find(m => m.key === metric) || DAILY_METRICS[0];
  const dailyChart = daily.length > 0 ? {
    labels: daily.map(d => d.date.slice(5)),
    datasets: [{
      label: activeMetric.label,
      data: daily.map(d => d[metric]),
      borderColor: C[activeMetric.color],
      backgroundColor: C[activeMetric.color] + '2E',
      fill: true,
      tension: 0.3,
      pointRadius: 2.5,
      spanGaps: true,
    }],
  } : null;

  return (
    <div className="space-y-4">
      <StatRow items={[
        { label: '趋势方向', value: TREND_LABELS[direction] || '未知' },
        { label: '预测置信度', value: fmtPct(confidence * 100) },
      ]} />

      {/* ── 多维画像 ── */}
      {dims.length > 0 ? (
        <>
          <div className="bg-card border border-border rounded-xl p-4">
            <h3 className="text-xs font-semibold text-text-secondary mb-1">舆情多维画像</h3>
            <p className="text-[10px] text-text-secondary mb-3 leading-relaxed">
              九个互相独立的维度，各归一化到 0-100 便于横向比较。样本共 {sample.total ?? 0} 条。
            </p>
            <div className="h-52">
              <Radar
                data={radarData}
                options={{
                  responsive: true,
                  maintainAspectRatio: false,
                  plugins: {
                    legend: { display: false },
                    tooltip: {
                      backgroundColor: C.tooltipBg,
                      borderColor: C.tooltipBorder,
                      borderWidth: 1,
                      titleColor: C.tooltipTitle,
                      bodyColor: C.tooltipBody,
                      padding: 10,
                      callbacks: {
                        label: (ctx) => {
                          const d = dims[ctx.dataIndex];
                          return d ? `${d.label}：${d.value} → ${d.display}` : '';
                        },
                      },
                    },
                  },
                  scales: {
                    r: {
                      min: 0, max: 100,
                      ticks: { color: C.axis, backdropColor: 'transparent', font: { size: 9 }, stepSize: 25 },
                      grid: { color: C.grid },
                      angleLines: { color: C.grid },
                      pointLabels: { color: C.axis, font: { size: 10 } },
                    },
                  },
                }}
              />
            </div>
          </div>

          <Section
            title="维度明细"
            icon={<BarChart3 size={12} />}
            action={
              <button
                onClick={() => setShowBasis(v => !v)}
                className="text-[10px] text-accent hover:text-accent-strong"
              >
                {showBasis ? '隐藏计算依据' : '显示计算依据'}
              </button>
            }
          >
            <div className="space-y-2.5">
              {dims.map(d => (
                <DimensionRow key={d.key} dim={d} showBasis={showBasis} />
              ))}
            </div>
            <p className="text-[10px] text-text-secondary mt-3 leading-relaxed">
              标灰的维度样本量不足，其数值仅供参考，不参与结论推导。
              归一化只是为了放进同一张图，判读时以原始值为准。
            </p>
          </Section>
        </>
      ) : (
        <EmptyHint text="本次运行未取得多维指标（缺少情绪打分样本）" />
      )}

      {/* ── 按天真实序列 ── */}
      {dailyChart ? (
        <div className="bg-card border border-border rounded-xl p-4">
          <div className="flex items-center justify-between mb-3 gap-2">
            <h3 className="text-xs font-semibold text-text-secondary">按天序列（实测）</h3>
            <div className="flex gap-1">
              {DAILY_METRICS.map(m => (
                <button
                  key={m.key}
                  onClick={() => setMetric(m.key)}
                  className={clsx(
                    "text-[10px] px-1.5 py-0.5 rounded border transition-colors",
                    metric === m.key
                      ? "border-accent/40 bg-accent/10 text-accent"
                      : "border-border bg-soft text-text-secondary hover:text-text-main"
                  )}
                >
                  {m.label}
                </button>
              ))}
            </div>
          </div>
          <div className="h-40">
            <Line
              data={dailyChart}
              options={{
                ...optionsFor(C),
                plugins: {
                  ...optionsFor(C).plugins,
                  legend: { display: false },
                  tooltip: {
                    ...optionsFor(C).plugins.tooltip,
                    callbacks: {
                      label: (ctx) => `${activeMetric.label}：${ctx.parsed.y}${activeMetric.unit}`,
                    },
                  },
                },
                scales: scaleOptionsFor(C),
              }}
            />
          </div>
          <p className="text-[10px] text-text-secondary mt-2 leading-relaxed">
            共 {daily.length} 个有发布日期的自然日
            {sample.undated > 0 && `，另有 ${sample.undated} 条样本没有可解析的发布日期，未计入序列`}。
            每个点是当日全部样本的统计量，没有插值。
          </p>
        </div>
      ) : (
        <EmptyHint text="本次运行未取得可用的日期序列（样本缺少发布日期）" />
      )}

      {/* ── 情绪指数预测 ── */}
      {forecastFeasible && predictions.length > 0 ? (
        <div className="bg-card border border-border rounded-xl p-4">
          <h3 className="text-xs font-semibold text-text-secondary mb-3">
            未来 {predictions.length} 天情绪指数预测
          </h3>
          <div className="h-56">
            <Line data={forecastChartData(predictions, C)} options={{ ...optionsFor(C), scales: scaleOptionsFor(C) }} />
          </div>
          <p className="text-[10px] text-text-secondary mt-2 leading-relaxed">
            虚线为模型区间。注意 {model.label}的区间不含采集口径变化带来的误差
            （信源构成一变，情绪指数的绝对水平就会位移）。
          </p>
        </div>
      ) : (
        <MethodNote>
          <p>
            未出预测：{daily.length < 2
              ? `本次采集只覆盖 ${daily.length} 个有发布日期的自然日，构不成日粒度序列，"未来 N 天"没有依据。`
              : '模型未返回预测结果。'}
            上方多维画像与按天序列仍是本次运行的真实结果，可作为横截面快照判读。
          </p>
        </MethodNote>
      )}

      <Section title="模型与数据口径" icon={<BarChart3 size={12} />}>
        <div className="space-y-2">
          <div className="flex justify-between text-[11px]">
            <span className="text-text-secondary">拟合模型</span>
            <span className="text-text-main">{model.label}</span>
          </div>
          <div className="flex justify-between text-[11px]">
            <span className="text-text-secondary">时序观测点</span>
            <span className="text-text-main tabular-nums">{summary.data_points ?? '—'} 个</span>
          </div>
          <div className="flex justify-between text-[11px]">
            <span className="text-text-secondary">外推窗口</span>
            <span className="text-text-main tabular-nums">{predictions.length} 天</span>
          </div>
          <div className="flex justify-between text-[11px]">
            <span className="text-text-secondary">数据质量评级</span>
            <span className={clsx(
              "font-medium",
              summary.data_quality === '高' ? 'text-success'
                : summary.data_quality === '中' ? 'text-warning' : 'text-danger'
            )}>
              {summary.data_quality || '未知'}
            </span>
          </div>
          <p className="text-[11px] text-text-secondary leading-relaxed pt-1 border-t border-border/60">
            {model.desc}
          </p>
          {summary.model_type === 'baseline' && summary.fallback_reason && (
            <p className="text-[11px] text-danger/90 leading-relaxed">
              降级原因：{summary.fallback_reason}
            </p>
          )}
          {summary.data_note && (
            <p className="text-[11px] text-text-main/80 leading-relaxed">{summary.data_note}</p>
          )}
        </div>
      </Section>

      {summary.recommendation && (
        <Section title="模型建议">
          <p className="text-xs text-text-main/90 leading-relaxed">{summary.recommendation}</p>
        </Section>
      )}
    </div>
  );
}

/** 情绪指数预测的折线 + 上下界。单独拆出来，避免 TrendContent 里再套一层缩进。 */
function forecastChartData(predictions, C) {
  return {
    labels: predictions.map(p => p.ds || ''),
    datasets: [
      {
        label: '预测值',
        data: predictions.map(p => p.yhat),
        borderColor: C.accent,
        backgroundColor: C.accentSoft,
        fill: true,
        tension: 0.35,
        pointRadius: 2,
      },
      {
        label: '上界',
        data: predictions.map(p => p.yhat_upper),
        borderColor: C.accentLine,
        borderDash: [4, 4],
        pointRadius: 0,
        fill: false,
        tension: 0.35,
      },
      {
        label: '下界',
        data: predictions.map(p => p.yhat_lower),
        borderColor: C.accentLine,
        borderDash: [4, 4],
        pointRadius: 0,
        fill: false,
        tension: 0.35,
      },
    ],
  };
}

function DimensionRow({ dim, showBasis }) {
  const hasValue = typeof dim.value === 'number' && Number.isFinite(dim.value);
  return (
    <div className={clsx(!dim.sufficient && 'opacity-55')}>
      <div className="flex justify-between items-baseline gap-2 mb-1">
        <span className="text-[11px] text-text-main shrink-0">{dim.label}</span>
        <span className="text-[11px] text-text-secondary tabular-nums text-right truncate">
          {dim.display}
        </span>
      </div>
      {hasValue ? (
        <div className="h-1.5 rounded-full bg-soft overflow-hidden">
          <div
            className="h-full rounded-full bg-accent/70"
            style={{ width: `${Math.min(Math.max(dim.value, 0), 100)}%` }}
          />
        </div>
      ) : (
        /* 没有数据时不画 0 长度的条：0 长度看起来像"测出来是 0"，
           而这里的事实是"没测"。 */
        <div className="h-1.5 rounded-full border border-dashed border-border" />
      )}
      {showBasis && (
        <div className="mt-1 space-y-0.5">
          <p className="text-[10px] text-text-secondary leading-relaxed">{dim.hint}</p>
          <p className="text-[10px] text-text-secondary/70 leading-relaxed font-mono">
            依据：{dim.basis} · 归一 {hasValue ? dim.value : '无数据'}
          </p>
        </div>
      )}
      {!dim.sufficient && (
        <p className="text-[10px] text-warning/80 mt-0.5">样本量不足，仅供参考</p>
      )}
    </div>
  );
}

// ── 情感 ────────────────────────────────────────────────────────────

function SentimentContent({ data }) {
  const { theme } = useTheme();
  const C = useChartColors(theme);
  const s = data?.sentiment_summary || {};
  const pos = data?.positive_pct || 0;
  const neg = data?.negative_pct || 0;
  const neu = data?.neutral_pct || 0;
  const total = data?.total_news || 0;

  if (total === 0) {
    return <EmptyHint text="暂无情绪分布数据，请先完成一次分析" />;
  }

  const posN = data?.positive_count ?? 0;
  const negN = data?.negative_count ?? 0;
  const neuN = s.neutral_count ?? Math.max(total - posN - negN, 0);

  const ciPos = wilsonCI(posN, total);
  const ciNeg = wilsonCI(negN, total);
  const ciNeu = wilsonCI(neuN, total);

  // ── 从 analyzed_news 现算两个派生视图 ──
  // 分层拆分与分箱直方图都必须来自同一次运行的真实样本。后端没带
  // analyzed_news 时（老任务载荷）这两块直接不渲染，不猜。
  const posts = Array.isArray(data?.analyzed_news) ? data.analyzed_news : [];
  const scored = posts.filter(p => typeof p.sentiment_score === 'number' && Number.isFinite(p.sentiment_score));
  const scoredCount = scored.length;

  const tierRows = [1, 2, 3, 4].map(t => {
    const items = posts.filter(p => Number(p.source_tier) === t);
    if (items.length === 0) return null;
    const neg = items.filter(p => p.sentiment_label === 'negative').length;
    const pos = items.filter(p => p.sentiment_label === 'positive').length;
    const neu = items.length - neg - pos;
    return {
      tier: t,
      total: items.length,
      neg, neu, pos,
      negPct: (neg / items.length) * 100,
      posPct: (pos / items.length) * 100,
      ci: wilsonCI(neg, items.length),
    };
  }).filter(Boolean);

  // 情绪分分箱：-1.0 ~ 1.0，每 0.2 一箱
  const histBins = Array.from({ length: 10 }, (_, i) => {
    const lo = -1 + i * 0.2;
    return { lo, hi: lo + 0.2, label: `${lo.toFixed(1)}~${(lo + 0.2).toFixed(1)}`, count: 0 };
  });
  for (const p of scored) {
    const idx = Math.min(9, Math.max(0, Math.floor((p.sentiment_score + 1) / 0.2)));
    histBins[idx].count += 1;
  }
  const histData = scoredCount > 0 ? {
    labels: histBins.map(b => b.label),
    datasets: [{
      data: histBins.map(b => b.count),
      backgroundColor: histBins.map(b => (b.lo + b.hi) / 2 >= 0.1 ? C.success : (b.lo + b.hi) / 2 <= -0.1 ? C.danger : C.neutral),
      borderRadius: 3,
      barThickness: 10,
    }],
  } : null;
  const polarCount = scored.filter(p => Math.abs(p.sentiment_score) >= 0.6).length;
  const meanScore = scoredCount ? scored.reduce((a, p) => a + p.sentiment_score, 0) / scoredCount : 0;
  const sampleStd = scoredCount > 1
    ? Math.sqrt(scored.reduce((a, p) => a + (p.sentiment_score - meanScore) ** 2, 0) / (scoredCount - 1))
    : 0;

  const chartData = {
    labels: ['负面', '中性', '正面'],
    datasets: [{
      data: [neg, neu, pos],
      backgroundColor: [C.danger, C.neutral, C.success],
      borderColor: C.card,
      borderWidth: 2,
    }],
  };

  return (
    <div className="space-y-4">
      <div className="bg-card border border-border rounded-xl p-4">
        <h3 className="text-xs font-semibold text-text-secondary mb-3">
          全网情绪分布（n = {total}）
        </h3>
        <div className="h-44">
          <Doughnut
            data={chartData}
            options={{
              ...optionsFor(C),
              cutout: '68%',
              plugins: {
                ...optionsFor(C).plugins,
                legend: {
                  position: 'bottom',
                  labels: { color: C.axis, boxWidth: 12, font: { size: 11 } },
                },
              },
            }}
          />
        </div>
      </div>

      <Section title="比例估计与 95% 置信区间" icon={<ShieldCheck size={12} />}>
        <div className="space-y-3">
          <CIBar label="负面" pct={neg} ci={ciNeg} color={C.danger} />
          <CIBar label="中性" pct={neu} ci={ciNeu} color={C.neutral} />
          <CIBar label="正面" pct={pos} ci={ciPos} color={C.success} />
        </div>
        <p className="text-[10px] text-text-secondary mt-3 leading-relaxed">
          圆点为该类占比的点估计，横带是 Wilson score 95% 置信区间。
          样本越少区间越宽——区间宽到跨过半程时，这个比例不具备区分度。
        </p>
      </Section>

      {tierRows.length > 0 && (
        <Section title="按信源层级拆分" icon={<Layers size={12} />}>
          <div className="space-y-3">
            {tierRows.map(r => (
              <div key={r.tier}>
                <div className="flex justify-between items-baseline text-[11px] mb-1">
                  <span className="text-text-secondary">
                    T{r.tier} {TIER_LABELS[r.tier]}
                    <span className="text-text-secondary/60 ml-1">n={r.total}</span>
                  </span>
                  <span className="tabular-nums" style={{ color: tierColors(C)[r.tier] }}>
                    {fmtPct(r.negPct)}
                    </span>
                </div>
                <div className="relative h-2.5 rounded-md bg-soft overflow-hidden">
                  <div className="absolute inset-y-0 left-0 bg-danger/70"
                    style={{ width: `${r.negPct}%` }} />
                  <div className="absolute inset-y-0 left-0 bg-success/70"
                    style={{ left: `${r.negPct}%`, width: `${r.posPct}%` }} />
                </div>
                <p className="text-[10px] text-text-secondary/70 mt-0.5 tabular-nums">
                  负面 {r.neg} · 中性 {r.neu} · 正面 {r.pos}
                  {r.ci && ` · 负面 95% CI [${r.ci.lower.toFixed(0)}–${r.ci.upper.toFixed(0)}]`}
                </p>
              </div>
            ))}
          </div>
          <p className="text-[10px] text-text-secondary mt-3 leading-relaxed">
            同一批样本按信源层级分开统计才有解释力：T4 自媒体通常系统性放大负面，
            把它和新华社快讯算进同一个分母，整体"负面占比"会被稀释得看不出结构。
            层级按域名后缀判定，不做主观拔高。
          </p>
        </Section>
      )}

      {histData && (
        <div className="bg-card border border-border rounded-xl p-4">
          <h3 className="text-xs font-semibold text-text-secondary mb-1">情绪分分布</h3>
          <p className="text-[10px] text-text-secondary mb-3 leading-relaxed">
            {scoredCount} 条已打分样本，按 0.2 分箱。三档标签会掩盖形态：
            均值相同的两个分布，一个可能集中在两端（立场对立），
            另一个集中在中间（共识模糊）。
          </p>
          <div className="h-36">
            <Bar
              data={histData}
              options={{
                ...optionsFor(C),
                plugins: {
                  ...optionsFor(C).plugins,
                  legend: { display: false },
                  tooltip: {
                    ...optionsFor(C).plugins.tooltip,
                    callbacks: {
                      label: (ctx) => `${ctx.parsed.y} 条 · 区间 ${histBins[ctx.dataIndex]?.label || ''}`,
                    },
                  },
                },
                scales: {
                  x: { ticks: { color: C.axis, font: { size: 9 }, maxRotation: 0 }, grid: { display: false } },
                  y: { ticks: { color: C.axis, font: { size: 10 } }, grid: { color: C.grid } },
                },
              }}
            />
          </div>
          <p className="text-[10px] text-text-secondary mt-2 leading-relaxed">
            标准差 {fmtNum(sampleStd, 3)}，绝对值 ≥ 0.6 的极端样本 {polarCount} 条
            （{fmtPct(scoredCount ? (polarCount / scoredCount) * 100 : 0)}）。
          </p>
        </div>
      )}

      <StatRow items={[
        { label: '正面', value: `${posN} 条 · ${fmtPct(pos)}` },
        { label: '负面', value: `${negN} 条 · ${fmtPct(neg)}` },
        { label: '中性', value: `${neuN} 条 · ${fmtPct(neu)}` },
        { label: '情绪均分', value: fmtNum(data?.avg_sentiment ?? s.avg_sentiment) },
      ]} />

      <Section title="方法论" icon={<Info size={12} />}>
        <ol className="text-[11px] text-text-secondary leading-relaxed space-y-1.5 list-decimal list-inside">
          <li>
            初判：SnowNLP 对「标题 + 摘要」打情绪分（-1 ~ 1），按阈值划为
            负 / 中 / 正三档。SnowNLP 的训练语料以电商评论为主，对中文财经
            与政治文本存在系统性偏正，因此它的结果只作为基线。
          </li>
          <li>
            校正：{s.llm_corrected
              ? '大模型读取前 25 条样本的算法标签后给出校正后的三档计数，再按分数排序把标签重新分配到个体新闻上。'
              : '大模型校正未生效（无可用 API Key 或调用失败），此处展示的是 SnowNLP 原始分布。'}
          </li>
          <li>
            分母：分母是去重后的新闻条数，不是曝光量。同一事件被 30 家媒体
            转载会贡献 30 条样本，占比反映的是「报道口径」而非「公众情绪」。
          </li>
        </ol>
      </Section>

      {s.llm_corrected && (
        <Section title="算法基线 vs 校正后" icon={<Layers size={12} />}>
          <div className="space-y-2">
            {[
              ['负面', negN, s.algo_negative_count ?? 0, C.danger],
              ['中性', neuN, s.algo_neutral_count ?? 0, C.neutral],
              ['正面', posN, s.algo_positive_count ?? 0, C.success],
            ].map(([label, corrected, algo, color]) => (
              <div key={label} className="flex items-center gap-2">
                <span className="text-[11px] text-text-secondary w-8 shrink-0">{label}</span>
                <div className="flex-1 h-2 rounded-full bg-soft relative overflow-hidden">
                  <div className="absolute inset-y-0 left-0 rounded-full opacity-45"
                    style={{ width: `${(algo / total) * 100}%`, backgroundColor: color }} />
                  <div className="absolute inset-y-0 left-0 rounded-full"
                    style={{ width: `${(corrected / total) * 100}%`, backgroundColor: color }} />
                </div>
                <span className="text-[10px] text-text-secondary tabular-nums w-16 text-right shrink-0">
                  {algo} → {corrected}
                </span>
              </div>
            ))}
            <p className="text-[10px] text-text-secondary leading-relaxed pt-1">
              浅色为 SnowNLP 基线，实色为校正后结果。两组数字都来自同一次运行，
              差异即大模型校正的净效果。
            </p>
          </div>
        </Section>
      )}
    </div>
  );
}

// 点估计 + 置信区间的「Dot-and-interval」图：竖线是点估计，横带是区间。
function CIBar({ label, pct, ci, color }) {
  const lo = ci ? ci.lower : pct;
  const hi = ci ? ci.upper : pct;
  return (
    <div>
      <div className="flex justify-between items-baseline text-[11px] mb-1">
        <span className="text-text-secondary">{label}</span>
        <span className="text-text-main tabular-nums">
          {fmtPct(pct)}
          {ci && (
            <span className="text-text-secondary/70 ml-1.5">
              [{lo.toFixed(0)}–{hi.toFixed(0)}]
            </span>
          )}
        </span>
      </div>
      <div className="relative h-3.5 rounded-md bg-soft overflow-hidden">
        {ci && (
          <div
            className="absolute top-1 bottom-1 rounded-full opacity-35"
            style={{ left: `${lo}%`, width: `${Math.max(hi - lo, 0.6)}%`, backgroundColor: color }}
          />
        )}
        <div
          className="absolute top-0.5 bottom-0.5 w-[2px] rounded-full"
          style={{ left: `calc(${Math.min(Math.max(pct, 0), 100)}% - 1px)`, backgroundColor: color }}
        />
      </div>
    </div>
  );
}

// ── 热词 ────────────────────────────────────────────────────────────

function KeywordContent({ data }) {
  const { theme } = useTheme();
  const C = useChartColors(theme);
  const weights = Array.isArray(data?.keyword_weights) ? data.keyword_weights : [];
  const plain = Array.isArray(data?.keywords) ? data.keywords : [];

  if (weights.length === 0 && plain.length === 0) {
    return <EmptyHint text="暂无热词数据" />;
  }

  // 有权重就直接画真实 TF-IDF 权重；没有就只列词表并说明柱高不可用，
  // 绝不拿排名冒充权重。
  const rows = weights.length > 0
    ? weights.slice(0, 12).map(w => ({ term: w.term, value: w.tfidf, doc: w.doc_freq }))
    : [];

  const chartData = {
    labels: rows.map(r => r.term),
    datasets: [{
      label: 'TF-IDF 权重',
      data: rows.map(r => r.value),
      backgroundColor: C.accentSoft,
      hoverBackgroundColor: C.accentLine,
      borderRadius: 4,
      barThickness: 12,
    }],
  };

  const topTerms = rows.length > 0 ? rows : plain.slice(0, 12).map(t => ({ term: t, value: null, doc: null }));

  return (
    <div className="space-y-4">
      {rows.length > 0 ? (
        <div className="bg-card border border-border rounded-xl p-4">
          <h3 className="text-xs font-semibold text-text-secondary mb-3">
            关键词 TF-IDF 权重 Top {rows.length}
          </h3>
          <div className="h-64">
            <Bar
              data={chartData}
              options={{
                ...optionsFor(C),
                indexAxis: 'y',
                plugins: {
                  ...optionsFor(C).plugins,
                  legend: { display: false },
                  tooltip: {
                    ...optionsFor(C).plugins.tooltip,
                    callbacks: {
                      label: (ctx) => {
                        const r = rows[ctx.dataIndex];
                        if (!r) return '';
                        return [
                          `TF-IDF 权重：${Number(r.value).toFixed(4)}`,
                          `出现在 ${r.doc} 条标题中`,
                        ];
                      },
                    },
                  },
                },
                scales: {
                  x: {
                    ticks: { color: C.axis, font: { size: 10 } },
                    grid: { color: C.grid },
                    title: { display: true, text: 'TF-IDF 权重', color: C.axis, font: { size: 10 } },
                  },
                  y: { ticks: { color: C.axis, font: { size: 11 } }, grid: { display: false } },
                },
              }}
            />
          </div>
        </div>
      ) : (
        <div className="bg-card border border-border rounded-xl p-4">
          <h3 className="text-xs font-semibold text-text-secondary mb-2">关键词词表</h3>
          <p className="text-[11px] text-text-secondary leading-relaxed">
            本次运行未取得 TF-IDF 权重（jieba 权重提取不可用），因此不绘制柱状图——
            用排名反推高度等于编造数值。以下仅按出现频次列出词表。
          </p>
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        {topTerms.map((r, i) => (
          <span
            key={r.term}
            className={clsx(
              "px-2 py-1 rounded-full border border-border bg-soft text-text-secondary",
              i < 3 ? "text-xs text-agent-sentiment border-agent-sentiment/30 bg-agent-sentiment/10" : "text-[11px]"
            )}
            title={r.value != null ? `TF-IDF ${Number(r.value).toFixed(4)} · 出现于 ${r.doc} 条标题` : undefined}
          >
            {r.term}
          </span>
        ))}
      </div>

      <MethodNote>
        <p>
          <span className="text-text-main">TF-IDF</span> = 词频 × 逆文档频率，由 jieba
          在本次采集的标题语料上现算，权重是该语料内的真实统计量，可跨运行复现。
        </p>
        <p>
          <span className="text-text-main">文档频率</span>（doc_freq）指前 50 条标题中
          有多少条出现了该词，用来区分「一篇里反复出现」和「很多篇都提到」——
          后者才是真正的舆论热点，前者可能只是某篇报道的行文习惯。
        </p>
        <p>
          语料是新闻标题而非正文，所以高频词偏向事件主体与机构名，
          不宜直接当作公众情绪词表。
        </p>
      </MethodNote>
    </div>
  );
}

// ── 证据 ────────────────────────────────────────────────────────────

const TIER_LABELS = { 1: '权威信源', 2: '专业媒体', 3: '门户转载', 4: '待核验' };
const TIER_DESC = {
  1: '通讯社 / 央媒 / 监管机构，有一线采编与事实核查流程',
  2: '主流财经与行业媒体，有编辑审核，可能带立场',
  3: '门户 / 地方媒体 / 聚合站，以转载为主',
  4: '自媒体 / 论坛 / 未识别来源，仅作情绪信号，不作为事实依据',
};
// 层级色直接映射到语义色（成功/强调/警示/危险），不另设第四套色值，
// 亮暗切换时跟着主题走。
const tierColors = (C) => ({
  1: C.success, 2: C.accent, 3: C.warning, 4: C.danger,
});

function EvidenceContent({ data }) {
  const { theme } = useTheme();
  const C = useChartColors(theme);
  const [sentiment, setSentiment] = useState('all');
  const [openDays, setOpenDays] = useState(() => new Set());
  const [touched, setTouched] = useState(false);

  const posts = data?.analyzed_news || [];
  const tierDist = data?.collect_meta?.tier_distribution || {};

  if (posts.length === 0) {
    return <EmptyHint text="暂无证据记录" />;
  }

  const counts = {
    negative: posts.filter(p => p.sentiment_label === 'negative').length,
    neutral: posts.filter(p => p.sentiment_label !== 'negative' && p.sentiment_label !== 'positive').length,
    positive: posts.filter(p => p.sentiment_label === 'positive').length,
  };

  // 先按情绪分组——读者要的是"消极的报道有哪些、积极的有哪些"，
  // 混在一起按时间排就等于把危机信号和利好通稿摆在同一个权重上。
  const filtered = sentiment === 'all'
    ? posts
    : posts.filter(p => (p.sentiment_label || 'neutral') === sentiment);

  // 再按发布日期聚成时间线节点。没有可解析日期的样本单独归为一组，
  // 不猜日期也不丢掉。
  const byDay = new Map();
  for (const p of filtered) {
    const raw = String(p.publish_time || p.time || '');
    const day = /^\d{4}-\d{2}-\d{2}/.test(raw) ? raw.slice(0, 10) : '日期未知';
    if (!byDay.has(day)) byDay.set(day, []);
    byDay.get(day).push(p);
  }
  const days = [...byDay.entries()].sort((a, b) => {
    if (a[0] === '日期未知') return 1;
    if (b[0] === '日期未知') return -1;
    return a[0] < b[0] ? 1 : -1;
  });

  // 默认只展开最新的一天：一屏能看完结构，其余按需点开。
  // 用户手动展开/收起之后不再自动改，否则每次切情绪分组都会把他的选择冲掉。
  const defaultOpen = new Set(touched ? [] : (days.length ? [days[0][0]] : []));
  const open = touched ? openDays : defaultOpen;
  const toggleDay = (day) => {
    setTouched(true);
    setOpenDays(prev => {
      // prev 是裸 state，open 才是当前生效的集合。默认展开的那天只存在于
      // defaultOpen 里、不在 prev 中，所以第一次点它时会走 else 分支把它
      // add 回去——界面毫无反应，用户要再点一次才收起。以生效集为基准
      // 做增减，第一次点击就是真正的切换。
      const next = new Set(touched ? prev : defaultOpen);
      if (next.has(day)) next.delete(day);
      else next.add(day);
      return next;
    });
  };

  const groups = [1, 2, 3, 4].map(t => ({
    tier: t,
    items: posts.filter(p => Number(p.source_tier) === t),
  })).filter(g => g.items.length > 0);

  return (
    <div className="space-y-4">
      <div className="bg-card border border-border rounded-xl p-3">
        <h3 className="text-xs font-semibold text-text-secondary mb-2 flex items-center gap-1.5">
          <Layers size={12} /> 信源可信度构成（{posts.length} 条）
        </h3>
        <div className="flex gap-1.5 h-2 rounded-full overflow-hidden bg-soft mb-2">
          {groups.map(g => (
            <div
              key={g.tier}
              className="h-full"
              style={{ width: `${(g.items.length / posts.length) * 100}%`, backgroundColor: tierColors(C)[g.tier] }}
              title={`${TIER_LABELS[g.tier]}：${g.items.length} 条`}
            />
          ))}
        </div>
        <div className="flex flex-wrap gap-x-3 gap-y-1 text-[10px] text-text-secondary">
          {groups.map(g => (
            <span key={g.tier} className="flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: tierColors(C)[g.tier] }} />
              {TIER_LABELS[g.tier]} {g.items.length}
            </span>
          ))}
        </div>
        <p className="text-[10px] text-text-secondary mt-2 leading-relaxed">
          {Object.keys(tierDist).length === 0
            ? '本次运行未提供层级统计。'
            : '层级按域名后缀判定，未命中可信域名的来源归入待核验，不做主观拔高。'}
        </p>
      </div>

      {/* 情绪分组筛选 */}
      <div className="flex gap-1.5">
        {[
          { id: 'all', label: '全部', n: posts.length, cls: 'text-text-main' },
          { id: 'negative', label: '负面', n: counts.negative, cls: 'text-danger' },
          { id: 'neutral', label: '中性', n: counts.neutral, cls: 'text-text-secondary' },
          { id: 'positive', label: '正面', n: counts.positive, cls: 'text-success' },
        ].map(t => (
          <button
            key={t.id}
            onClick={() => setSentiment(t.id)}
            className={clsx(
              "flex-1 text-[11px] px-2 py-1.5 rounded-lg border transition-colors",
              sentiment === t.id
                ? "border-accent/40 bg-accent/10 text-accent font-medium"
                : "border-border bg-soft text-text-secondary hover:text-text-main"
            )}
          >
            {t.label}
            <span className="tabular-nums ml-1 opacity-70">{t.n}</span>
          </button>
        ))}
      </div>

      {/* 时间线：竖线是轴，节点是按天聚合的一批证据，点一下展开。
          比一长条平铺更容易看清"舆情哪天起的头、哪天到顶"。 */}
      {days.length === 0 ? (
        <EmptyHint text="该情绪分组下没有证据" />
      ) : (
        <div className="relative pl-4">
          <div className="absolute left-[5px] top-2 bottom-2 w-px bg-border" />
          <div className="space-y-1">
            {days.map(([day, items]) => {
              const isOpen = open.has(day);
              const neg = items.filter(p => p.sentiment_label === 'negative').length;
              const topTier = Math.min(...items.map(p => Number(p.source_tier) || 4));
              return (
                <div key={day} className="relative">
                  <span
                    className={clsx(
                      "absolute -left-4 top-2.5 w-[11px] h-[11px] rounded-full border-2 transition-colors",
                      isOpen ? "bg-accent border-accent" : "bg-panel border-border"
                    )}
                  />
                  <button
                    onClick={() => toggleDay(day)}
                    className="w-full text-left px-2 py-1.5 rounded-lg hover:bg-hover transition-colors"
                  >
                    <div className="flex items-center gap-2">
                      <Clock size={10} className="text-text-secondary shrink-0" />
                      <span className="text-[11px] font-medium text-text-main tabular-nums">{day}</span>
                      <span className="text-[10px] text-text-secondary tabular-nums">{items.length} 条</span>
                      {neg > 0 && (
                        <span className="text-[10px] text-danger tabular-nums">负面 {neg}</span>
                      )}
                      <span
                        className="text-[10px] px-1 py-0.5 rounded shrink-0 ml-auto"
                        style={{ color: tierColors(C)[topTier], backgroundColor: `${tierColors(C)[topTier]}1F` }}
                        title={`当天最高信源层级：T${topTier} ${TIER_LABELS[topTier]} · ${TIER_DESC[topTier]}`}
                      >
                        最高 T{topTier}
                      </span>
                      <ChevronDown
                        size={11}
                        className={clsx("text-text-secondary shrink-0 transition-transform", !isOpen && "-rotate-90")}
                      />
                    </div>
                  </button>
                  {isOpen && (
                    <div className="pl-2 pb-2 space-y-2">
                      {items.map((post, i) => (
                        <EvidenceCard key={`${day}-${i}`} post={post} tier={Number(post.source_tier) || 4} />
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      <MethodNote>
        <p>同一事件常被多家媒体转载，本列表已按标题签名与链接去重，但无法识别改头换面的洗稿。</p>
        <p>点击"原文"可跳转核验；本面板只做呈现，不对链接内容做二次校验。</p>
      </MethodNote>
    </div>
  );
}

function EvidenceCard({ post, tier }) {
  const { theme } = useTheme();
  const C = useChartColors(theme);
  const score = typeof post.sentiment_score === 'number' ? post.sentiment_score : null;
  const labelCls = post.sentiment_label === 'negative' ? 'text-danger'
    : post.sentiment_label === 'positive' ? 'text-success' : 'text-text-secondary';

  return (
    <div className="bg-card border border-border rounded-xl p-3 hover:border-accent/30 transition-colors group">
      <div className="flex items-center gap-2 mb-1.5">
        <span
          className="text-[10px] font-semibold px-1.5 py-0.5 rounded shrink-0"
          style={{ color: tierColors(C)[tier], backgroundColor: `${tierColors(C)[tier]}1F` }}
          title={`T${tier} ${TIER_LABELS[tier]} · ${TIER_DESC[tier]}`}
        >
          T{tier}
        </span>
        <span className="text-[11px] font-medium text-text-main truncate">
          {post.source || post.source_domain || '未知来源'}
        </span>
        <span className="text-[10px] text-text-secondary ml-auto shrink-0 tabular-nums">
          {post.publish_time || post.time || '未知时间'}
        </span>
      </div>
      <h5 className="text-xs text-text-main leading-snug mb-1.5">{post.title || '无标题'}</h5>
      <p className="text-[11px] text-text-secondary leading-relaxed mb-2 line-clamp-3 group-hover:line-clamp-none">
        {post.summary || post.content || post.snippet || '（无摘要）'}
      </p>
      <div className="flex items-center justify-between pt-2 border-t border-border/60">
        <div className="flex gap-3 text-[10px] text-text-secondary">
          {score !== null && <span className="tabular-nums">情绪分 {score.toFixed(2)}</span>}
          {post.sentiment_label && <span className={labelCls}>{post.sentiment_label}</span>}
        </div>
        {post.url && (
          <a
            href={post.url}
            target="_blank"
            rel="noreferrer"
            className="text-[10px] text-accent flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity"
          >
            <ExternalLink size={10} /> 原文
          </a>
        )}
      </div>
    </div>
  );
}
