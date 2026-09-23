import React, { useState, useEffect } from 'react';
import {
  TrendingUp, PieChart, FileText, FileSearch, ExternalLink, Gavel, Minus,
  PanelRightClose, Info, ShieldCheck, AlertTriangle, BarChart3, Layers,
  ChevronDown, ChevronRight, Clock, CalendarDays, Radio,
} from 'lucide-react';
import clsx from 'clsx';
import { resolveDepth } from '../CenterWorkspace/DepthSelector';
import {
  Chart as ChartJS, CategoryScale, LinearScale, PointElement, LineElement,
  ArcElement, BarElement, RadarController, RadialLinearScale, Tooltip, Legend, Filler,
} from 'chart.js';
import { Line, Bar, Radar } from 'react-chartjs-2';
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

export default function RightInsightPanel({ activeTab, onTabChange, analysisData, onCollapse, depth }) {
  const { theme } = useTheme();
  const C = useChartColors(theme);
  // 右栏是"结论证据面板"，不是图表集合。四个 Tab 各自对应一类可复核的
  // 依据：趋势读数、可点开验证的证据、事件怎么发展到今天的、以及这批
  // 数据本身能信到什么程度。缺数据时明确说"本次运行未取得"。
  const tabs = [
    { id: 'trend', label: '趋势', icon: <TrendingUp size={14} /> },
    { id: 'evidence', label: '证据', icon: <FileSearch size={14} /> },
    { id: 'timeline', label: '事件脉络', icon: <CalendarDays size={14} /> },
    { id: 'quality', label: '数据质量', icon: <ShieldCheck size={14} /> },
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
        {activeTab === 'trend' && <TrendContent data={analysisData} depth={depth} />}
        {activeTab === 'evidence' && <EvidenceContent data={analysisData} />}
        {activeTab === 'timeline' && <TimelineContent data={analysisData} />}
        {activeTab === 'quality' && <QualityContent data={analysisData} />}
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

const TREND_DIRECTION_LABELS = {
  // 研判卡用的是确定性口径（按日序列前后半段对比）：升温/降温/横盘/反转风险
  heating: '升温', cooling: '降温', flat: '横盘',
  reversal_risk: '反转风险', unknown: '未知',
  // trend_summary 里的旧口径，只在没有研判卡时兜底
  positive: '积极', negative: '消极', neutral: '平稳',
};

// 按天真序列里可切换的维度。全部是后端按本批样本算出的真实日度量，
// 不含任何插值或拟合填充。
const DAILY_METRICS = [
  { key: 'sentiment_index', label: '情绪指数', color: 'accent', unit: '' },
  { key: 'negative_share', label: '负面占比', color: 'danger', unit: '%' },
  { key: 't1_share', label: 'T1 权威占比', color: 'success', unit: '%' },
  { key: 'volume', label: '声量', color: 'blue', unit: ' 条' },
];

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
 * 核心指标分组。
 *
 * 默认只展示四组：情绪指数、负面占比、讨论量与注意力爆发、极化度。它们直接
 * 支撑研判卡上的结论，是"这个事件现在什么态势"的四个读数。
 *
 * 来源多样性、权威占比、低可信占比、日期覆盖度同样重要，但它们回答的是
 * "这批数据能不能信"，不是"事件怎么样"——放在主区会和结论抢注意力，所以
 * 收进「数据质量与传播结构」抽屉，需要复核口径时再展开。
 */
const CORE_GROUPS = [
  {
    label: '情绪与负面',
    keys: ['sentiment_index', 'negative_share'],
    note: '整体情绪水位与负面绝对占比。均值尚可但负面占比高，说明少数极端个案在拉低整体。',
  },
  {
    label: '讨论量与注意力爆发',
    keys: ['volume', 'attention_burst'],
    note: '采集样本总量与单日峰值相对日均的倍数。尖峰通常对应事件爆发点，也是最可能继续升温的位置。',
  },
  {
    label: '情绪极化',
    keys: ['polarization'],
    note: '情绪分绝对值 ≥ 0.6 的样本占比。越高说明立场越两极、温和共识少——这种舆情转向也快。',
  },
];

// 数据质量与传播结构。默认收起：它们是结论的可信度前提，不是结论本身。
const QUALITY_KEYS = ['source_diversity', 'authority_share', 'low_credibility_share', 'date_coverage'];

/**
 * 多维舆情画像 + 按天真实序列 + 热度演化预警。
 *
 * 单一"情绪指数"读不出一次舆情的性质：同样的均值可能来自少量极端负面，
 * 也可能来自温和的全面偏负，两者风险完全不同。所以先给互相独立的维度
 * （全部由本批样本算出，见 sentiment_indicators.py），再看时序，最后才是
 * 外推。任何一环样本不足时明确说"本次运行未取得"，不补假数据。
 */
function TrendContent({ data, depth }) {
  const { theme } = useTheme();
  const C = useChartColors(theme);
  const [metric, setMetric] = useState('sentiment_index');
  const [showBasis, setShowBasis] = useState(false);
  // 数据质量抽屉默认收起。主区只留四组核心指标，避免九个维度把结论冲淡。
  // 深度切到"深度审计"时由 resolveDepth 展开，用户仍可手动收起。
  const expandQuality = resolveDepth(depth).expandQuality;
  const [showQuality, setShowQuality] = useState(expandQuality);
  useEffect(() => { setShowQuality(expandQuality); }, [expandQuality]);

  const predictions = data?.predictions || [];
  const summary = data?.trend_summary || {};
  const indicators = summary.indicators || {};
  const dims = Array.isArray(indicators.dimensions) ? indicators.dimensions : [];
  const byKey = Object.fromEntries(dims.map(d => [d.key, d]));
  const daily = (Array.isArray(indicators.daily) ? indicators.daily : [])
    .filter(d => d && d.date && d.date !== 'unknown');
  const sample = indicators.sample || {};
  const model = MODEL_META[summary.model_type] || MODEL_META.unknown;
  // 趋势方向与置信度必须和研判卡一致。研判卡那份是确定性计算（按有日期的
  // 自然日做前后半段对比），trend_summary 里这份是趋势 Agent 的自评口径。
  // 两份同时上一屏会互相打架——实测出现过一边"平稳 / 93.8%"、一边
  // "升温 / 65%"，读者无法判断该信哪个。以研判卡为准，没有研判卡时才退回
  // trend_summary。
  const card = data?.verdict_card || null;
  const direction = card?.trend?.direction
    || summary.trend_direction || data?.trend_direction || 'unknown';
  const confidence = (card && typeof card.confidence === 'number')
    ? card.confidence
    : (summary.confidence ?? data?.confidence ?? 0);
  const directionBasis = card?.trend?.basis || '';
  const forecastFeasible = summary.forecast_feasible !== false && daily.length >= 2;

  const radarKeys = CORE_GROUPS.flatMap(g => g.keys);
  const radarDims = radarKeys.map(k => byKey[k]).filter(Boolean);
  const radarData = radarDims.length > 0 ? {
    labels: radarDims.map(d => d.label),
    datasets: [{
      label: '归一化值（0-100）',
      data: radarDims.map(d => d.value),
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
        { label: '趋势方向', value: TREND_DIRECTION_LABELS[direction] || '未知' },
        { label: '研判置信度', value: fmtPct(confidence * 100) },
      ]} />
      {directionBasis && (
        <p className="text-[10px] text-text-secondary/80 leading-relaxed -mt-1">
          <span className="text-text-main/80">判据：</span>{directionBasis}
          <span className="opacity-70">（与研判卡同一口径，确定性计算）</span>
        </p>
      )}

      {/* ── 四组核心指标 ── */}
      {dims.length > 0 ? (
        <>
          <div className="bg-card border border-border rounded-xl p-4">
            <h3 className="text-xs font-semibold text-text-secondary mb-1">核心指标</h3>
            <p className="text-[10px] text-text-secondary mb-3 leading-relaxed">
              支撑研判结论的四个读数，样本共 {sample.total ?? 0} 条。传播结构与数据质量收在下方抽屉。
            </p>
            {radarData && (
              <div className="h-44">
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
                            const d = radarDims[ctx.dataIndex];
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
            )}
          </div>

          {CORE_GROUPS.map(group => {
            const rows = group.keys.map(k => byKey[k]).filter(Boolean);
            if (rows.length === 0) return null;
            return (
              <div key={group.label} className="bg-card border border-border rounded-xl p-4">
                <h3 className="text-xs font-semibold text-text-secondary mb-1">{group.label}</h3>
                <p className="text-[10px] text-text-secondary mb-3 leading-relaxed">{group.note}</p>
                <div className="space-y-2.5">
                  {rows.map(d => (
                    <DimensionRow key={d.key} dim={d} showBasis={showBasis} />
                  ))}
                </div>
              </div>
            );
          })}

          {/* ── 数据质量与传播结构（默认收起） ── */}
          <div className="bg-card border border-border rounded-xl overflow-hidden">
            <button
              onClick={() => setShowQuality(v => !v)}
              aria-expanded={showQuality}
              className="w-full flex items-center gap-2 px-4 py-3 text-left hover:bg-hover transition-colors"
            >
              {showQuality ? <ChevronDown size={13} className="text-text-secondary shrink-0" />
                            : <ChevronRight size={13} className="text-text-secondary shrink-0" />}
              <Layers size={12} className="text-text-secondary shrink-0" />
              <span className="text-xs font-medium text-text-main">数据质量与传播结构</span>
              <span className="ml-auto text-[10px] text-text-secondary shrink-0">
                {showQuality ? '收起' : '展开口径'}
              </span>
            </button>
            {showQuality && (
              <div className="px-4 pb-4 border-t border-border/60 pt-3 space-y-2.5">
                {QUALITY_KEYS.map(k => byKey[k]).filter(Boolean).map(d => (
                  <DimensionRow key={d.key} dim={d} showBasis={showBasis} />
                ))}
                <div className="flex items-center justify-between pt-1">
                  <span className="text-[10px] text-text-secondary">计算依据</span>
                  <button
                    onClick={() => setShowBasis(v => !v)}
                    className="text-[10px] text-accent hover:text-accent-strong"
                  >
                    {showBasis ? '隐藏' : '显示'}
                  </button>
                </div>
                <p className="text-[10px] text-text-secondary leading-relaxed">
                  这一组回答的是"这批数据能不能信"，不是"事件怎么样"。权威占比低或低可信占比高时，
                  上方核心指标的解读要相应打折。归一化只是为了横向比较，判读时以原始值为准。
                </p>
              </div>
            )}
          </div>
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

      {/* ── 热度演化预警 ──
          措辞刻意不用"预测未来一定如何"。这里给出的是"在既有采集口径不变的
          前提下，模型认为更可能落在哪一带"，是态势研判不是事实预告。 */}
      {forecastFeasible && predictions.length > 0 ? (
        <div className="bg-card border border-border rounded-xl p-4">
          <h3 className="text-xs font-semibold text-text-secondary mb-1">
            未来 {predictions.length} 日热度演化研判
          </h3>
          <p className="text-[10px] text-text-secondary mb-3 leading-relaxed">
            在采集口径不变的前提下，情绪指数更可能落在的区间。不是对事件结果的断言。
          </p>
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
            未出外推：{daily.length < 2
              ? `本次采集只覆盖 ${daily.length} 个有发布日期的自然日，构不成日粒度序列，"未来 N 日"没有依据。`
              : '模型未返回外推结果。'}
            上方核心指标与按天序列仍是本次运行的真实结果，可作为横截面快照判读。
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


// ── 热词（并入证据 Tab） ────────────────────────────────────────────

/**
 * 关键词权重区块。
 *
 * 归到"证据"Tab 而不是独立 Tab：TF-IDF 说的是"这批语料在讨论什么"，
 * 是证据的一个侧面，单独占一个 Tab 会把右栏撑成图表集合。
 *
 * 权重是 jieba 在本次标题语料上现算的真实统计量。拿不到权重时只列词表
 * 并明说柱高不可用——用排名反推高度等于编造数值。
 */
function KeywordSection({ data }) {
  const { theme } = useTheme();
  const C = useChartColors(theme);
  const weights = Array.isArray(data?.keyword_weights) ? data.keyword_weights : [];
  const plain = Array.isArray(data?.keywords) ? data.keywords : [];

  if (weights.length === 0 && plain.length === 0) return null;

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

      {/* 两个情绪数字的口径必须写在明处。标签是大模型校正后的分布判断，
          "初判分"是 SnowNLP 对单条文本的连续实测值——两者完全可能一正一负
          （实测有 +0.91 分却被校正为负面的条目）。不说明的话，读者会把这
          看成自相矛盾的坏数据。 */}
      <p className="text-[10px] text-text-secondary/80 leading-relaxed">
        标签为校正后判断；<span className="text-text-secondary">初判分</span>是 SnowNLP
        对单条文本的实测值（[-1, 1]），未经校正，两者口径不同。
      </p>

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

      {/* 关键词权重：这批语料在讨论什么。归到证据 Tab，不单独占一屏。 */}
      <KeywordSection data={data} />
    </div>
  );
}

/**
 * 证据卡。
 *
 * 一张卡只回答一个问题：这条证据为什么影响趋势判断。所以固定三段——
 * 标签（影响量级 · 信源层级 · 日期）、标题、"为什么重要"与"影响"。
 *
 * "为什么重要"和"影响"不是模型生成的句子，而是由真实字段推导的呈现层
 * 解释：信源层级决定这条证据能当"事实"读到什么程度，情绪标签决定它把
 * 结论往哪边推。推导规则写死在下面，不调用模型——否则每条证据都要等一次
 * LLM 往返，而且编出来的句子无法复核。
 */
const TIER_WEIGHT = {
  1: '权威信源层面的事实记载',
  2: '主流媒体的报道口径',
  3: '门户/地方转载，事实层较薄',
  4: '自媒体/论坛口径，仅作情绪信号',
};

const TIER_CAVEAT = {
  1: '可作为事实依据',
  2: '有编辑审核，可能带立场',
  3: '以转载为主，需回溯原始出处',
  4: '不作为事实依据，仅反映情绪面',
};

const LABEL_IMPACT = {
  negative: '把结论推向看空一侧',
  positive: '把结论推向看多一侧',
  neutral: '不改变方向，补充事件基本面貌',
};

const LABEL_TEXT = {
  negative: '负面', positive: '正面', neutral: '中性',
};

function EvidenceCard({ post, tier }) {
  const { theme } = useTheme();
  const C = useChartColors(theme);
  const score = typeof post.sentiment_score === 'number' ? post.sentiment_score : null;
  const labelCls = post.sentiment_label === 'negative' ? 'text-danger'
    : post.sentiment_label === 'positive' ? 'text-success' : 'text-text-secondary';
  const label = post.sentiment_label || 'neutral';

  // 影响量级只由两个可测字段决定：信源层级（T1/T2 的一手采编与审核流程
  // 让它们的记载更接近事实）和情绪极性（中性条目不改变结论方向）。
  // 不引入"热度""重要性评分"这类需要模型主观打分的量。
  const highImpact = tier <= 2 && label !== 'neutral';

  return (
    <div className="bg-card border border-border rounded-xl p-3 hover:border-accent/30 transition-colors group">
      {/* 标签行：影响量级 · 信源层级 · 日期 */}
      <div className="flex items-center gap-1.5 mb-1.5 flex-wrap">
        <span
          className={clsx(
            "text-[10px] font-semibold px-1.5 py-0.5 rounded shrink-0 border",
            highImpact
              ? "bg-accent/10 text-accent border-accent/25"
              : "bg-soft text-text-secondary border-border"
          )}
          title={highImpact
            ? 'T1/T2 信源且带明确情绪极性，对结论方向有直接影响'
            : '转载层信源或中性条目，对结论方向影响有限'}
        >
          {highImpact ? '高影响' : '参考'}
        </span>
        <span
          className="text-[10px] font-semibold px-1.5 py-0.5 rounded shrink-0"
          style={{ color: tierColors(C)[tier], backgroundColor: `${tierColors(C)[tier]}1F` }}
          title={`T${tier} ${TIER_LABELS[tier]} · ${TIER_DESC[tier]}`}
        >
          T{tier} {TIER_LABELS[tier]}
        </span>
        <span className="text-[10px] text-text-secondary shrink-0 tabular-nums">
          {post.publish_time || post.time || '未知时间'}
        </span>
        <span className="text-[11px] font-medium text-text-main truncate ml-auto">
          {post.source || post.source_domain || '未知来源'}
        </span>
      </div>

      <h5 className="text-xs text-text-main leading-snug mb-2">
        {post.original_title || post.title || '无标题'}
      </h5>

      {/* 为什么重要 + 影响。两句都由上面的真实字段推出，可逐条复核。 */}
      <div className="space-y-1 mb-2">
        <p className="text-[11px] text-text-secondary leading-relaxed">
          <span className="text-text-main/80 font-medium">为什么重要：</span>
          {TIER_WEIGHT[tier] || TIER_WEIGHT[4]}，{TIER_CAVEAT[tier] || TIER_CAVEAT[4]}。
        </p>
        <p className="text-[11px] text-text-secondary leading-relaxed">
          <span className="text-text-main/80 font-medium">影响：</span>
          <span className={labelCls}>{label === 'negative' ? '负面' : label === 'positive' ? '正面' : '中性'}</span>
          {LABEL_IMPACT[label] || LABEL_IMPACT.neutral}。
        </p>
      </div>

      <p className="text-[11px] text-text-secondary leading-relaxed mb-2 line-clamp-3 group-hover:line-clamp-none">
        {post.summary || post.content || post.snippet || '（无摘要）'}
      </p>

      <div className="flex items-center justify-between pt-2 border-t border-border/60">
        <div className="flex gap-3 text-[10px] text-text-secondary">
          {post.sentiment_label && (
            <span className={labelCls} title="经大模型校正后的标签">
              {LABEL_TEXT[label] || label}
            </span>
          )}
          {score !== null && (
            <span
              className="tabular-nums opacity-70"
              title="SnowNLP 实测分，[-1, 1]，未经校正"
            >
              初判分 {score > 0 ? '+' : ''}{score.toFixed(2)}
            </span>
          )}
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

// ── 事件脉络 ────────────────────────────────────────────────────────

/**
 * 事件脉络：这个事件是怎么发展到今天的。
 *
 * 和"证据"Tab 的分工：证据 Tab 按信源层级回答"谁能当事实读"，这里按时间
 * 回答"事情按什么顺序发生的"。所以节点是自然日，每天给出当日声量、情绪
 * 构成和最高信源层级——爆发点、权威回应时点、情绪转向都能在这里看出来。
 *
 * 不画趋势线：那是"趋势"Tab 的事。这里只做事实排列，不含任何外推。
 */
function TimelineContent({ data }) {
  const { theme } = useTheme();
  const C = useChartColors(theme);
  const [openDay, setOpenDay] = useState(null);

  const posts = data?.analyzed_news || [];
  if (posts.length === 0) {
    return <EmptyHint text="暂无事件记录" />;
  }

  // 按发布日期聚成自然日。没有可解析日期的单独归一组，不猜日期也不丢弃。
  const byDay = new Map();
  for (const p of posts) {
    const raw = String(p.publish_time || p.time || '').trim();
    const day = raw.length >= 10 ? raw.slice(0, 10) : 'unknown';
    if (!byDay.has(day)) byDay.set(day, []);
    byDay.get(day).push(p);
  }
  const days = [...byDay.entries()].sort((a, b) => {
    if (a[0] === 'unknown') return 1;
    if (b[0] === 'unknown') return -1;
    return b[0].localeCompare(a[0]);
  });

  const peak = Math.max(...days.map(([, items]) => items.length));

  return (
    <div className="space-y-4">
      <MethodNote>
        <p>
          节点为自然日，按当日全部样本统计。纵轴不是等比例时间轴——只列出有样本的日期，
          空档日不出现在这里。
        </p>
        <p>本 Tab 只排列已发生的事实，不含任何预测。外推见「趋势」Tab。</p>
      </MethodNote>

      <div className="relative pl-4">
        <div className="absolute left-[5px] top-2 bottom-2 w-px bg-border" />
        <div className="space-y-1.5">
          {days.map(([day, items]) => {
            const isOpen = openDay === day;
            const neg = items.filter(p => p.sentiment_label === 'negative').length;
            const pos = items.filter(p => p.sentiment_label === 'positive').length;
            const topTier = Math.min(...items.map(p => Number(p.source_tier) || 4));
            const isPeak = items.length === peak && days.length > 1;
            return (
              <div key={day} className="relative">
                <span
                  className={clsx(
                    "absolute -left-4 top-2.5 w-[11px] h-[11px] rounded-full border-2 transition-colors",
                    isPeak ? "bg-danger border-danger"
                      : isOpen ? "bg-accent border-accent" : "bg-panel border-border"
                  )}
                />
                <button
                  onClick={() => setOpenDay(isOpen ? null : day)}
                  className="w-full text-left px-2 py-2 rounded-lg hover:bg-hover transition-colors"
                >
                  <div className="flex items-center gap-2 flex-wrap">
                    <CalendarDays size={10} className="text-text-secondary shrink-0" />
                    <span className="text-[11px] font-medium text-text-main tabular-nums">
                      {day === 'unknown' ? '无发布日期' : day}
                    </span>
                    <span className="text-[10px] text-text-secondary tabular-nums">{items.length} 条</span>
                    {isPeak && (
                      <span className="text-[10px] text-danger font-medium">当日峰值</span>
                    )}
                    {neg > 0 && <span className="text-[10px] text-danger tabular-nums">负面 {neg}</span>}
                    {pos > 0 && <span className="text-[10px] text-success tabular-nums">正面 {pos}</span>}
                    <span
                      className="text-[10px] px-1 py-0.5 rounded shrink-0 ml-auto"
                      style={{ color: tierColors(C)[topTier], backgroundColor: `${tierColors(C)[topTier]}1F` }}
                      title={`当天最高信源层级：T${topTier} ${TIER_LABELS[topTier]}`}
                    >
                      最高 T{topTier}
                    </span>
                    <ChevronDown
                      size={11}
                      className={clsx("text-text-secondary shrink-0 transition-transform", !isOpen && "-rotate-90")}
                    />
                  </div>
                  {/* 当日声量条。长度相对峰值，让爆发点一眼可见。 */}
                  <div className="mt-1.5 h-1 rounded-full bg-soft overflow-hidden">
                    <div
                      className={clsx("h-full rounded-full", isPeak ? "bg-danger" : "bg-accent/60")}
                      style={{ width: `${(items.length / peak) * 100}%` }}
                    />
                  </div>
                </button>
                {isOpen && (
                  <div className="pl-2 pb-2 space-y-2">
                    {items.map((p, i) => (
                      <EvidenceCard key={`${day}-${i}`} post={p} tier={Number(p.source_tier) || 4} />
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ── 数据质量 ────────────────────────────────────────────────────────

/**
 * 数据质量：这批样本能不能支撑上面的结论。
 *
 * 三层口径：采集规模与信源分布（样本是谁说的）、情绪打分方法（SnowNLP 初判
 * 与 LLM 校正的差异，以及校正是否真的生效）、比例的统计不确定性（Wilson
 * 区间——"负面 34%" 在 n=12 和 n=1200 里的可信度完全不同）。
 *
 * 这一 Tab 不重新解释结论，只交代结论的地基。用户想复核时来这里，
 * 不想复核时不必看。
 */
function QualityContent({ data }) {
  const { theme } = useTheme();
  const C = useChartColors(theme);
  const total = data?.total_news || 0;
  const tierDist = data?.collect_meta?.tier_distribution || {};
  const sentiment = data?.sentiment_summary || {};
  const summary = data?.trend_summary || {};
  const indicators = summary.indicators || {};
  const sample = indicators.sample || {};

  const hasTierDist = Object.keys(tierDist).length > 0;
  const llmCorrected = Boolean(sentiment.llm_corrected);
  const algoTotal = (sentiment.algo_negative_count || 0) + (sentiment.algo_positive_count || 0) + (sentiment.algo_neutral_count || 0);
  const corrected = (sentiment.negative_count || 0) + (sentiment.positive_count || 0) + (sentiment.neutral_count || 0);
  const negCI = sentiment.total_news > 0 ? wilsonCI(sentiment.negative_count, sentiment.total_news) : null;

  return (
    <div className="space-y-4">
      <Section title="样本规模与信源分布" icon={<Layers size={12} />}>
        <div className="space-y-2">
          <div className="flex justify-between text-[11px]">
            <span className="text-text-secondary">纳入分析的样本</span>
            <span className="text-text-main tabular-nums">{total} 条</span>
          </div>
          <div className="flex justify-between text-[11px]">
            <span className="text-text-secondary">去重后来源数</span>
            <span className="text-text-main tabular-nums">{sample.sources ?? '—'} 个</span>
          </div>
          <div className="flex justify-between text-[11px]">
            <span className="text-text-secondary">有可解析发布日期</span>
            <span className="text-text-main tabular-nums">
              {sample.known_days ?? '—'} 个自然日
              {sample.undated ? `（${sample.undated} 条无日期）` : ''}
            </span>
          </div>
        </div>
        {hasTierDist ? (
          <div className="space-y-2 mt-3">
            <div className="flex gap-1.5 h-1.5 rounded-full overflow-hidden bg-soft">
              {['1', '2', '3', '4'].map(t => {
                const cnt = Number(tierDist[t] || 0);
                if (!cnt || !total) return null;
                return (
                  <div
                    key={t}
                    className="h-full"
                    style={{ width: `${(cnt / total) * 100}%`, backgroundColor: tierColors(C)[t] }}
                    title={`${TIER_LABELS[t]}：${cnt} 条`}
                  />
                );
              })}
            </div>
            <div className="flex flex-wrap gap-x-3 gap-y-1 text-[10px] text-text-secondary">
              {['1', '2', '3', '4'].map(t => (
                <span key={t} className="flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: tierColors(C)[t] }} />
                  {TIER_LABELS[t]} {tierDist[t] || 0}
                  <span className="opacity-60">
                    （{total ? Math.round((tierDist[t] || 0) / total * 100) : 0}%）
                  </span>
                </span>
              ))}
            </div>
            <p className="text-[10px] text-text-secondary leading-relaxed pt-1">
              层级按域名后缀判定，不按来源名字符串——来源名由搜索引擎给出，写法不一。
              未命中可信域名的归入待核验，不做主观拔高。
            </p>
          </div>
        ) : (
          <p className="text-[10px] text-text-secondary mt-2">本次运行未提供层级统计。</p>
        )}
      </Section>

      <Section title="情绪打分方法" icon={<BarChart3 size={12} />}>
        <div className="space-y-2">
          <div className="flex justify-between text-[11px]">
            <span className="text-text-secondary">算法</span>
            <span className="text-text-main">SnowNLP 初判 + 大模型校正</span>
          </div>
          <div className="flex justify-between text-[11px]">
            <span className="text-text-secondary">LLM 校正</span>
            <span className={clsx("font-medium", llmCorrected ? 'text-success' : 'text-warning')}>
              {llmCorrected ? '已生效' : '未生效（本地兜底）'}
            </span>
          </div>
          <div className="flex justify-between text-[11px]">
            <span className="text-text-secondary">情绪分覆盖</span>
            <span className="text-text-main tabular-nums">
              {sample.scored ?? 0}/{sample.total ?? 0} 条
            </span>
          </div>
        </div>
        {llmCorrected && algoTotal > 0 && corrected > 0 ? (
          <div className="space-y-2 mt-3">
            <p className="text-[10px] text-text-secondary leading-relaxed">
              SnowNLP 对中文财经/政治文本系统性低报负面，所以算法结果只作初判，
              最终标签按校正后分数排序重排。两者差异如下：
            </p>
            <div className="grid grid-cols-3 gap-2">
              {[
                { label: '负面', algo: sentiment.algo_negative_count, final: sentiment.negative_count, cls: 'text-danger' },
                { label: '中性', algo: sentiment.algo_neutral_count, final: sentiment.neutral_count, cls: 'text-text-secondary' },
                { label: '正面', algo: sentiment.algo_positive_count, final: sentiment.positive_count, cls: 'text-success' },
              ].map(row => (
                <div key={row.label} className="bg-soft/60 border border-border rounded-lg p-2">
                  <div className={clsx("text-[10px] mb-1", row.cls)}>{row.label}</div>
                  <div className="text-[11px] text-text-main tabular-nums">
                    {row.final}
                    <span className="text-text-secondary text-[10px]"> / 算法 {row.algo}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <p className="text-[10px] text-text-secondary mt-2 leading-relaxed">
            未配置可用的 LLM，或本次校正未返回结果。情绪标签由 SnowNLP 单独给出，
            对中文财经文本会系统性低报负面——负面占比应视为下限而非精确值。
          </p>
        )}
      </Section>

      <Section title="比例的统计不确定性" icon={<Info size={12} />}>
        {sentiment.total_news > 0 ? (
          <div className="space-y-2.5">
            {[
              { label: '负面占比', n: sentiment.negative_count, cls: 'text-danger', bar: 'bg-danger' },
              { label: '正面占比', n: sentiment.positive_count, cls: 'text-success', bar: 'bg-success' },
            ].map(row => {
              const ci = wilsonCI(row.n, sentiment.total_news);
              const pct = (row.n / sentiment.total_news) * 100;
              return (
                <div key={row.label}>
                  <div className="flex justify-between text-[11px] mb-1">
                    <span className="text-text-secondary">{row.label}</span>
                    <span className={clsx("tabular-nums font-medium", row.cls)}>{pct.toFixed(1)}%</span>
                  </div>
                  {ci && (
                    <>
                      <div className="relative h-3">
                        <div className="absolute inset-x-0 top-1/2 -translate-y-1/2 h-px bg-border" />
                        <div
                          className={clsx("absolute top-1/2 -translate-y-1/2 h-1.5 rounded-full opacity-40", row.bar)}
                          style={{
                            left: `${ci.lower}%`,
                            width: `${Math.max(ci.upper - ci.lower, 0.8)}%`,
                          }}
                        />
                        <div
                          className={clsx("absolute top-1/2 -translate-y-1/2 w-0.5 h-3 -translate-x-px", row.bar)}
                          style={{ left: `${pct}%` }}
                        />
                      </div>
                      <div className="flex justify-between text-[10px] text-text-secondary mt-0.5 tabular-nums">
                        <span>95% 区间下界 {ci.lower.toFixed(1)}%</span>
                        <span>上界 {ci.upper.toFixed(1)}%</span>
                      </div>
                    </>
                  )}
                </div>
              );
            })}
            <p className="text-[10px] text-text-secondary leading-relaxed pt-1">
              区间为 Wilson score interval（二项比例的小样本置信区间）。样本越少区间越宽——
              当前 n={sentiment.total_news}，负面占比的上下界相差{' '}
              {negCI ? (negCI.upper - negCI.lower).toFixed(1) : '—'} 个百分点。
              读结论时请连同区间一起读，不要只看点估计。
            </p>
          </div>
        ) : (
          <p className="text-[11px] text-text-secondary">本次运行未取得情绪分布样本。</p>
        )}
      </Section>

      <Section title="模型与数据口径" icon={<BarChart3 size={12} />}>
        <div className="space-y-2">
          <div className="flex justify-between text-[11px]">
            <span className="text-text-secondary">拟合模型</span>
            <span className="text-text-main">{(MODEL_META[summary.model_type] || MODEL_META.unknown).label}</span>
          </div>
          <div className="flex justify-between text-[11px]">
            <span className="text-text-secondary">时序观测点</span>
            <span className="text-text-main tabular-nums">{summary.data_points ?? '—'} 个</span>
          </div>
          <div className="flex justify-between text-[11px]">
            <span className="text-text-secondary">外推窗口</span>
            <span className="text-text-main tabular-nums">{(data?.predictions || []).length} 天</span>
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
            {(MODEL_META[summary.model_type] || MODEL_META.unknown).desc}
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

      <Disclaimer>
        本面板所有数字均由本次采集的样本算出，不含外部基准或行业均值。
        样本覆盖度受采集渠道与检索词影响，不应解读为全量舆情。
      </Disclaimer>
    </div>
  );
}
