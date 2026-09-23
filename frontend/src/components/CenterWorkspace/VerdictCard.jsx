import React from 'react';
import {
  AlertOctagon, AlertTriangle, ShieldCheck, Flame, Snowflake, Activity,
  Shuffle, ExternalLink, Clock, CircleDot, CheckCircle2, ChevronDown,
  ChevronUp, Gauge, Eye,
} from 'lucide-react';
import clsx from 'clsx';

/**
 * 研判卡（Layer 1 结论）。
 *
 * 这是每次分析完成后的默认主视图。它要回答的是"这个事件现在是什么态势、
 * 我下一步该看什么"，而不是"几个 Agent 分别说了什么"——后者属于分析过程，
 * 放在折叠区里。
 *
 * 卡片上的每个数字都由后端 build_verdict_card() 从实测指标确定性算出
 * （权重、窗口、选取口径见后端 verdict_card.py），不随模型措辞变化。
 * 所以这里不做任何二次加工：置信度不重新四舍五入、风险分不换算成别的
 * 刻度、样本不足时不藏起标记。缺数据时明确说缺，不画一个看着像有数的图。
 */

// 风险等级 → 视觉。四档各自有明确的动作含义，颜色从 success 一路升到 danger。
const RISK_META = {
  low: {
    label: '低', Icon: ShieldCheck,
    ring: 'border-success/30', chip: 'bg-success/12 text-success border-success/25',
    bar: 'bg-success',
  },
  medium: {
    label: '中', Icon: AlertTriangle,
    ring: 'border-warning/30', chip: 'bg-warning/12 text-warning border-warning/25',
    bar: 'bg-warning',
  },
  high: {
    label: '高', Icon: AlertTriangle,
    ring: 'border-danger/30', chip: 'bg-danger/12 text-danger border-danger/25',
    bar: 'bg-danger',
  },
  critical: {
    label: '紧急', Icon: AlertOctagon,
    ring: 'border-danger/50', chip: 'bg-danger/15 text-danger border-danger/40',
    bar: 'bg-danger',
  },
};

// 趋势方向四态。前三者说的是"声量还在不在涨"，反转风险说的是"立场本身
// 在换边"——性质不同，所以分开给图标和说明。
const TREND_META = {
  heating: { label: '升温', Icon: Flame, cls: 'text-danger bg-danger/10 border-danger/25' },
  cooling: { label: '降温', Icon: Snowflake, cls: 'text-agent-trend bg-agent-trend/10 border-agent-trend/25' },
  flat: { label: '横盘', Icon: Activity, cls: 'text-text-secondary bg-soft border-border' },
  reversal_risk: { label: '反转风险', Icon: Shuffle, cls: 'text-warning bg-warning/10 border-warning/25' },
  unknown: { label: '样本不足', Icon: CircleDot, cls: 'text-text-secondary bg-soft border-border' },
};

const STANCE_META = {
  negative: { text: '看空', cls: 'bg-danger/12 text-danger border-danger/25' },
  neutral: { text: '中性', cls: 'bg-soft text-text-secondary border-border' },
  positive: { text: '看多', cls: 'bg-success/12 text-success border-success/25' },
};

const TIER_LABEL = { 1: 'T1 权威', 2: 'T2 主流', 3: 'T3 门户', 4: 'T4 待核验' };

// 核心证据的来源徽标。层级直接决定这条证据能当"事实"读到什么程度，
// 所以徽标必须带层级而不是只写来源名。
function EvidenceTag({ item }) {
  const tier = Number(item.source_tier) || 4;
  return (
    <span className="text-[10px] px-1.5 py-0.5 rounded border border-border bg-soft text-text-secondary tabular-nums">
      {TIER_LABEL[tier] || `T${tier}`}
    </span>
  );
}

// 证据卡必须回答"为什么它支撑这个结论"。后端只给事实字段（标题/来源/
// 日期/立场），"为什么重要"由前端按立场与层级拼出来——这属于呈现层的
// 解释，不该让模型去编一句通用废话。
function whyItMatters(item, stance) {
  const label = String(item.sentiment_label || '').toLowerCase();
  const tier = Number(item.source_tier) || 4;
  const when = item.publish_time ? `（${item.publish_time}）` : '';
  const who = item.source || '未知来源';

  if (stance === 'negative') {
    if (label === 'negative') {
      return tier <= 2
        ? `${who}${when}给出负面事实，权威信源层面的负面记载是本次看空判断的直接依据。`
        : `${who}${when}的负面口径反映情绪面压力，与权威信源的负面记载方向一致。`;
    }
    if (label === 'positive') return `${who}${when}持正面口径，是本次判断中的反向证据，已在辩论中计入。`;
    return `${who}${when}为中性事实陈述，提供事件基本面貌，不含方向性判断。`;
  }
  if (stance === 'positive') {
    if (label === 'positive') return `${who}${when}的正面事实支撑破局判断，是本次看多结论的直接依据。`;
    if (label === 'negative') return `${who}${when}的负面记载是反向证据，红方的主要论据来源。`;
    return `${who}${when}为中性事实陈述，提供事件基本面貌，不含方向性判断。`;
  }
  // 中性终裁没有方向可依附，但证据自身的情绪极性仍是实测事实——它是风险分
  // 与负面占比的来源，不能说成"没有方向性"。
  if (label === 'negative') {
    return `${who}${when}为负面记载，是风险分与负面占比的直接来源；终裁未定向前，负面面本身就是需要跟踪的事实。`;
  }
  if (label === 'positive') {
    return `${who}${when}为正面记载，与同批负面面相互抵消，是终裁未能定向上的原因之一。`;
  }
  return `${who}${when}为中性事实陈述，提供事件基本面貌，不含方向性判断。`;
}

export default function VerdictCard({ card, onJumpToEvidence }) {
  if (!card) return null;

  const risk = RISK_META[card.risk?.level] || RISK_META.low;
  const trend = TREND_META[card.trend?.direction] || TREND_META.unknown;
  const stance = STANCE_META[card.stance] || STANCE_META.neutral;
  const score = Number(card.risk?.score) || 0;
  const evidence = Array.isArray(card.core_evidence) ? card.core_evidence : [];
  const watch = Array.isArray(card.watch_items) ? card.watch_items : [];
  const window = card.window || {};

  // 置信度是裁判自评，不是统计显著性。文案必须说清这一点，否则用户会把
  // "78%" 当成"这个结论有 78% 的概率为真"来用。
  const confidencePct = typeof card.confidence === 'number'
    ? Math.round(card.confidence * 100)
    : null;

  return (
    <section
      aria-label="研判结论"
      className={clsx(
        "bg-panel border rounded-panel shadow-panel overflow-hidden",
        risk.ring
      )}
    >
      {/* 顶部：一句话结论。这一屏只讲"现在是什么态势"，别的不放。 */}
      <div className="p-5 pb-4">
        <div className="flex items-start justify-between gap-3 mb-3">
          <div className="flex items-center gap-2 text-[11px] text-text-secondary">
            <Gauge size={13} className="text-accent" />
            <span className="uppercase tracking-wider font-semibold">态势研判</span>
            <span className={clsx("text-[11px] px-2 py-0.5 rounded-full border font-medium", stance.cls)}>
              {stance.text}
            </span>
          </div>
          <div className="flex items-center gap-1.5 shrink-0">
            <span className={clsx("text-[11px] px-2 py-0.5 rounded-full border font-medium flex items-center gap-1", trend.cls)}>
              <trend.Icon size={11} /> {trend.label}
            </span>
            <span className={clsx("text-[11px] px-2 py-0.5 rounded-full border font-medium flex items-center gap-1", risk.chip)}>
              <risk.Icon size={11} /> 风险{risk.label}
            </span>
          </div>
        </div>

        <h2 className="text-[17px] font-semibold text-text-main leading-relaxed">
          {card.headline || '本次分析未生成结论摘要。'}
        </h2>

        {/* 风险分的构成。给出来是因为"高风险"三个字无法复核——权重和分量
            摆在这里，用户能自己重算，而不是只能选择相信。 */}
        <div className="mt-4">
          <div className="flex items-baseline justify-between mb-1.5">
            <span className="text-[11px] text-text-secondary">综合风险分</span>
            <span className="text-sm font-semibold text-text-main tabular-nums">
              {score.toFixed(1)}
              <span className="text-[10px] text-text-secondary font-normal"> / 100</span>
            </span>
          </div>
          <div className="h-1.5 rounded-full bg-soft overflow-hidden">
            <div
              className={clsx("h-full rounded-full transition-all", risk.bar)}
              style={{ width: `${Math.max(2, Math.min(100, score))}%` }}
            />
          </div>
          <div className="flex flex-wrap gap-x-3 gap-y-1 mt-2 text-[10px] text-text-secondary">
            {Object.entries(card.risk?.components || {}).map(([key, value]) => (
              <span key={key} className="tabular-nums">
                {COMPONENT_LABEL[key] || key} {Number(value).toFixed(0)}
                <span className="opacity-50"> ×{card.risk?.weights?.[key]}</span>
              </span>
            ))}
          </div>
          {/* 行动建议必须来自裁判对本次事件的具体判断。这里曾经显示按风险
              档位写死的通用话术（"建议立即介入并准备对外口径"），读起来像
              建议、实际和这个事件无关，还把真正的建议挤掉了。 */}
          <p className="text-[11px] text-text-main leading-relaxed mt-2">
            <span className="text-text-secondary">行动建议：</span>
            {card.recommendation || '本次运行未给出行动建议。'}
          </p>
        </div>
      </div>

      {/* 中部：趋势方向与观察窗口的判据。方向词下面必须跟一句"怎么判的"，
          否则用户只能接受一个没有出处的结论。 */}
      <div className="px-5 py-3 border-t border-border/60 bg-soft/40 grid grid-cols-2 gap-4">
        <div>
          <div className="text-[10px] text-text-secondary mb-1">趋势判据</div>
          <p className="text-[11px] text-text-main leading-relaxed">
            {card.trend?.basis || '样本不足，无法判断时序方向'}
          </p>
        </div>
        <div>
          <div className="text-[10px] text-text-secondary mb-1">观察窗口</div>
          <p className="text-[11px] text-text-main leading-relaxed tabular-nums">
            {window.from && window.to
              ? `${window.from} → ${window.to} · ${window.days} 个自然日`
              : '无可解析日期的样本'}
            <span className="block text-text-secondary">
              {window.samples || 0} 条样本 · {window.sources || 0} 个信源
              {window.undated ? ` · ${window.undated} 条无日期` : ''}
            </span>
          </p>
        </div>
      </div>

      {/* 置信度。样本不足时后端已压到 0.5 以下并置 low_confidence，
          这里必须如实显示，不能只展示百分比。 */}
      {confidencePct !== null && (
        <div className={clsx(
          "px-5 py-2.5 border-t border-border/60 flex items-center gap-2 text-[11px]",
          card.low_confidence ? "bg-warning/[0.06]" : "bg-soft/40"
        )}>
          {card.low_confidence
            ? <AlertTriangle size={12} className="text-warning shrink-0" />
            : <Eye size={12} className="text-text-secondary shrink-0" />}
          <span className="text-text-secondary">
            置信度 <span className="text-text-main font-medium tabular-nums">{confidencePct}%</span>
            <span className="opacity-70">（裁判自评，非统计显著性）</span>
            {card.low_confidence && ' · 样本量偏少，结论需更多数据复核'}
          </span>
        </div>
      )}

      {/* 三条核心依据。要能点开验证，所以标题带外链；没有 URL 的证据
          降级成纯文本，不给一个点了没反应的按钮。 */}
      <div className="p-5 border-t border-border/60">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-[11px] font-semibold text-text-secondary uppercase tracking-wider">
            核心依据
          </h3>
          <span className="text-[10px] text-text-secondary/70">按信源层级与时间排序选取</span>
        </div>
        {evidence.length === 0 ? (
          <p className="text-[11px] text-text-secondary">本次运行未取得可引用的证据样本。</p>
        ) : (
          <ol className="space-y-2.5">
            {evidence.map((item, i) => {
              const why = whyItMatters(item, card.stance);
              const linked = Boolean(item.url);
              return (
                <li key={`${item.title}-${i}`} className="flex gap-2.5">
                  <span className="shrink-0 w-4 h-4 rounded-full bg-soft border border-border flex items-center justify-center text-[10px] text-text-secondary tabular-nums mt-0.5">
                    {i + 1}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5 flex-wrap mb-1">
                      <EvidenceTag item={item} />
                      <span className="text-[10px] text-text-secondary truncate max-w-[10rem]">
                        {item.source}
                      </span>
                      {item.publish_time && (
                        <span className="text-[10px] text-text-secondary/70 flex items-center gap-0.5 tabular-nums">
                          <Clock size={8} /> {item.publish_time}
                        </span>
                      )}
                    </div>
                    <div className="text-[12px] font-medium text-text-main leading-snug">
                      {linked ? (
                        <a
                          href={item.url}
                          target="_blank"
                          rel="noreferrer noopener"
                          className="hover:text-accent transition-colors inline-flex items-start gap-1 group/link"
                        >
                          <span className="underline decoration-border group-hover/link:decoration-accent/50 underline-offset-2">
                            {item.title}
                          </span>
                          <ExternalLink size={10} className="shrink-0 mt-1 opacity-40 group-hover/link:opacity-100" />
                        </a>
                      ) : (
                        <span>{item.title}</span>
                      )}
                    </div>
                    <p className="text-[11px] text-text-secondary leading-relaxed mt-1">
                      <span className="text-text-main/80">为什么重要：</span>{why}
                    </p>
                  </div>
                </li>
              );
            })}
          </ol>
        )}
      </div>

      {/* 待验证项。明确不确定性是专业性的一部分：把"这个结论还缺什么"
          写出来，比把结论说满更可信。 */}
      {watch.length > 0 && (
        <div className="px-5 pb-5">
          <h3 className="text-[11px] font-semibold text-text-secondary uppercase tracking-wider mb-2">
            待验证项
          </h3>
          <ul className="space-y-1.5">
            {watch.map((w, i) => (
              <li key={i} className="flex gap-2 text-[11px] text-text-secondary leading-relaxed">
                <CircleDot size={11} className="shrink-0 mt-0.5 text-warning/70" />
                <span>{w}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* 口径说明。每个数字都要能回答"怎么算的"。 */}
      <div className="px-5 pb-5">
        <p className="text-[10px] text-text-secondary/70 leading-relaxed border-t border-border/60 pt-3">
          {card.method_note}
        </p>
      </div>
    </section>
  );
}

// 风险分量的中文名。与后端 _RISK_WEIGHTS 的键一一对应。
const COMPONENT_LABEL = {
  negative_share: '负面占比',
  attention_burst: '关注度峰值',
  low_credibility_share: '低可信占比',
  authority_gap: '无把关来源占比',
  sentiment_pessimism: '情绪悲观度',
};

// 待验证项支持收起：多数用户看一眼就过，但列表长时会占掉首屏。
export function WatchList({ items }) {
  const [open, setOpen] = React.useState(false);
  if (!Array.isArray(items) || items.length === 0) return null;
  return (
    <div>
      <button
        onClick={() => setOpen(o => !o)}
        className="flex items-center gap-1 text-[11px] text-text-secondary hover:text-text-main transition-colors"
      >
        {open ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
        {open ? '收起待验证项' : `展开待验证项（${items.length}）`}
      </button>
      {open && (
        <ul className="space-y-1.5 mt-2">
          {items.map((w, i) => (
            <li key={i} className="flex gap-2 text-[11px] text-text-secondary leading-relaxed">
              <CircleDot size={11} className="shrink-0 mt-0.5 text-warning/70" />
              <span>{w}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
