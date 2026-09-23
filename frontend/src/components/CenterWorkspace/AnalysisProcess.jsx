import React, { useState, useEffect } from 'react';
import {
  ShieldCheck, Swords, Gavel, ChevronDown, ChevronRight,
  AlertTriangle, TrendingUp, MessageSquare, Bot,
} from 'lucide-react';
import clsx from 'clsx';

/**
 * 分析过程（Layer 3）。
 *
 * 辩论是后端的分析组织方式，不是前端的信息架构中心。所以它默认收起，
 * 只在用户点"查看分析依据"时展开，而且展开后也不是把四段发言原样铺开——
 * 那既是重复推理，也要求读者自己从两千字里提炼结论。
 *
 * 这里压成三个视图，各自回答一个问题：
 *   1. 支持结论的证据 —— 赢的一方的论据是什么
 *   2. 可能推翻结论的信号 —— 输的一方的哪条论据最可能翻盘
 *   3. 最终裁决逻辑 —— 裁判怎么取舍的
 *
 * 没有轮次编号、没有 Agent 自我介绍、没有检索日志。完整原始发言仍然
 * 保留在最后一个折叠块里——可审计性不能丢，只是不该占首屏。
 */

const VIEWS = [
  { id: 'support', label: '支持结论的证据', Icon: ShieldCheck },
  { id: 'challenge', label: '可能推翻结论的信号', Icon: Swords },
  { id: 'logic', label: '最终裁决逻辑', Icon: Gavel },
];

const ROLE_META = {
  red: { label: '红方', cls: 'text-danger' },
  blue: { label: '蓝方', cls: 'text-agent-trend' },
  judge: { label: '裁判', cls: 'text-accent' },
};

// 与终裁立场一致的那一方。neutral 时没有"赢家"，返回 null，由调用方
// 决定怎么呈现——不能默认塞一个红方进去。
function winningRole(stance) {
  if (stance === 'negative') return 'red';
  if (stance === 'positive') return 'blue';
  return null;
}

export default function AnalysisProcess({ turns, verdict, onOpenFullLog, defaultExpanded = false }) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const [view, setView] = useState('support');

  // 深度档位切换时同步开合。用户选"深度审计"就是要看过程，选"快速研判"
  // 就是要它让位——这一档不生效的话，选择器就只是个装饰。
  useEffect(() => { setExpanded(defaultExpanded); }, [defaultExpanded]);

  const speeches = (Array.isArray(turns) ? turns : []).filter(t => t.role !== 'collect' && t.role !== 'report');
  if (speeches.length === 0 && !verdict) return null;

  const stance = verdict?.stance;
  const winner = winningRole(stance);
  const loser = winner === 'red' ? 'blue' : winner === 'blue' ? 'red' : null;
  const winnerStrong = winner === 'red' ? verdict?.red_strongest : verdict?.blue_strongest;
  const loserStrong = loser === 'red' ? verdict?.red_strongest : verdict?.blue_strongest;

  return (
    <section className="bg-card border border-border rounded-card overflow-hidden">
      <button
        onClick={() => setExpanded(e => !e)}
        aria-expanded={expanded}
        className="w-full flex items-center gap-2 px-4 py-3 text-left hover:bg-hover transition-colors"
      >
        {expanded ? <ChevronDown size={14} className="text-text-secondary shrink-0" />
                  : <ChevronRight size={14} className="text-text-secondary shrink-0" />}
        <Bot size={13} className="text-text-secondary shrink-0" />
        <span className="text-[12px] font-medium text-text-main">分析过程</span>
        <span className="text-[10px] text-text-secondary/70">红蓝双方如何得出上述结论</span>
        <span className="ml-auto text-[10px] text-text-secondary shrink-0">
          {expanded ? '收起' : '查看分析依据'}
        </span>
      </button>

      {expanded && (
        <div className="border-t border-border/60">
          {/* 三个压缩视图的切换。不用 Tab 组件而用同组按钮：这三个视图是
              "同一个结论的三种读法"，不是三个平级的信息区。 */}
          <div className="flex border-b border-border/60">
            {VIEWS.map(v => (
              <button
                key={v.id}
                onClick={() => setView(v.id)}
                className={clsx(
                  "flex-1 flex items-center justify-center gap-1.5 px-2 py-2 text-[11px] transition-colors",
                  view === v.id
                    ? "text-text-main bg-soft/60 font-medium border-b-2 border-accent"
                    : "text-text-secondary hover:text-text-main border-b-2 border-transparent"
                )}
              >
                <v.Icon size={11} />
                <span className="hidden sm:inline">{v.label}</span>
              </button>
            ))}
          </div>

          <div className="p-4 space-y-3">
            {view === 'support' && (
              <SupportView stance={stance} winner={winner} strong={winnerStrong}
                           verdict={verdict} turns={speeches} />
            )}
            {view === 'challenge' && (
              <ChallengeView loser={loser} strong={loserStrong} verdict={verdict} turns={speeches} />
            )}
            {view === 'logic' && <LogicView verdict={verdict} />}
          </div>

          {/* 完整原始发言。可审计性保留，但默认不占地方。 */}
          <details className="border-t border-border/60 group">
            <summary className="px-4 py-2.5 text-[11px] text-text-secondary hover:text-text-main cursor-pointer select-none flex items-center gap-1.5">
              <MessageSquare size={11} />
              完整发言记录（{speeches.length} 条）
            </summary>
            <div className="px-4 pb-4 space-y-2.5">
              {speeches.map((t, i) => (
                <div key={t.id || i} className="border-l-2 border-border pl-3">
                  <div className={clsx("text-[10px] font-medium mb-0.5", ROLE_META[t.role]?.cls || 'text-text-secondary')}>
                    {ROLE_META[t.role]?.label || t.label || '分析 Agent'}
                  </div>
                  <p className="text-[11px] text-text-secondary leading-relaxed whitespace-pre-wrap">
                    {t.content}
                  </p>
                </div>
              ))}
              {speeches.length === 0 && (
                <p className="text-[11px] text-text-secondary">本次运行未产生发言记录。</p>
              )}
            </div>
          </details>
        </div>
      )}
    </section>
  );
}

function SupportView({ stance, winner, strong, verdict, turns }) {
  if (!stance) {
    return <p className="text-[11px] text-text-secondary leading-relaxed">本次运行未记录终裁立场。</p>;
  }
  // 中性终裁没有"赢家"，但也不是没有依据——双方最有力的论据都摆出来，
  // 让读者自己看天平为什么平。塞一个默认赢家进去等于伪造结论。
  if (stance === 'neutral') {
    const red = verdict?.red_strongest;
    const blue = verdict?.blue_strongest;
    if (!red && !blue) {
      return (
        <p className="text-[11px] text-text-secondary leading-relaxed">
          终裁未倾向任一方（中性），且未记录双方最强论据，请查看「完整发言记录」自行判断。
        </p>
      );
    }
    return (
      <>
        <p className="text-[11px] text-text-secondary leading-relaxed">
          终裁未倾向任一方（中性）。双方最有力的论据强度接近，分列如下。
        </p>
        <div className="grid gap-2 sm:grid-cols-2">
          {red && (
            <div className="bg-soft/50 border border-border rounded-lg p-3">
              <div className={clsx("text-[10px] font-medium mb-1", ROLE_META.red.cls)}>
                红方最有力的论据
              </div>
              <p className="text-[12px] text-text-main leading-relaxed">{red}</p>
            </div>
          )}
          {blue && (
            <div className="bg-soft/50 border border-border rounded-lg p-3">
              <div className={clsx("text-[10px] font-medium mb-1", ROLE_META.blue.cls)}>
                蓝方最有力的论据
              </div>
              <p className="text-[12px] text-text-main leading-relaxed">{blue}</p>
            </div>
          )}
        </div>
      </>
    );
  }
  const roleMeta = ROLE_META[winner];
  return (
    <>
      {strong && (
        <div className="bg-soft/50 border border-border rounded-lg p-3">
          <div className={clsx("text-[10px] font-medium mb-1", roleMeta.cls)}>
            {roleMeta.label}最有力的论据
          </div>
          <p className="text-[12px] text-text-main leading-relaxed">{strong}</p>
        </div>
      )}
      <div className="text-[10px] text-text-secondary">
        该立场与终裁一致（{stance === 'negative' ? '看空' : '看多'}），其论据被裁判采纳为结论的主要支撑。
      </div>
      <SpeakerTurns turns={turns} role={winner} limit={2} />
    </>
  );
}

function ChallengeView({ loser, strong, verdict, turns }) {
  const disagreements = Array.isArray(verdict?.key_disagreements) ? verdict.key_disagreements : [];
  const neutral = !loser;
  return (
    <>
      {strong && loser && (
        <div className="bg-warning/[0.05] border border-warning/25 rounded-lg p-3">
          <div className={clsx("text-[10px] font-medium mb-1", ROLE_META[loser].cls)}>
            {ROLE_META[loser].label}最有力的反驳（未被采纳，但仍是主要风险点）
          </div>
          <p className="text-[12px] text-text-main leading-relaxed">{strong}</p>
        </div>
      )}
      {neutral && (
        <p className="text-[11px] text-text-secondary leading-relaxed">
          终裁为中性，没有被否决的一方。下面这些正是让裁判无法定论的分歧点，
          任何一条被新证据支持，结论都可能偏向对应一侧。
        </p>
      )}
      {disagreements.length > 0 && (
        <div>
          <div className="text-[10px] font-semibold text-text-secondary uppercase tracking-wider mb-1.5">
            核心分歧
          </div>
          <ul className="space-y-1.5">
            {disagreements.map((d, i) => (
              <li key={i} className="flex gap-2 text-[11px] text-text-secondary leading-relaxed">
                <AlertTriangle size={11} className="shrink-0 mt-0.5 text-warning/70" />
                <span>{d}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      <p className="text-[10px] text-text-secondary/70 leading-relaxed">
        这些是可能推翻当前结论的信号。若后续采集到新的权威证据支持其中任一条，研判结论应重新评估。
      </p>
    </>
  );
}

function LogicView({ verdict }) {
  if (!verdict) {
    return <p className="text-[11px] text-text-secondary">本次运行未产生终裁记录。</p>;
  }
  return (
    <>
      {verdict.summary && (
        <div className="bg-soft/50 border border-border rounded-lg p-3">
          <div className="text-[10px] font-medium text-text-secondary mb-1">裁定理由</div>
          <p className="text-[12px] text-text-main leading-relaxed">{verdict.summary}</p>
        </div>
      )}
      {verdict.recommendation && (
        <div className="flex gap-2 items-start bg-accent/[0.06] border border-accent/20 rounded-lg p-3">
          <TrendingUp size={12} className="text-accent shrink-0 mt-0.5" />
          <div>
            <div className="text-[10px] font-medium text-text-secondary mb-0.5">行动建议</div>
            <p className="text-[12px] text-text-main leading-relaxed">{verdict.recommendation}</p>
          </div>
        </div>
      )}
      <p className="text-[10px] text-text-secondary/70 leading-relaxed">
        风险分与趋势方向不来自裁判模型，而是由实测指标加权算出（权重见研判卡），因此不会随模型措辞变化。
      </p>
    </>
  );
}

// 从某一方的发言里挑几条有信息量的。不按字数硬切——直接切片会把句子断在
// 半中间（后端 extract_opponent_claim 踩过这个坑），这里按句末截断。
function SpeakerTurns({ turns, role, limit = 2 }) {
  const picks = (turns || []).filter(t => t.role === role).slice(0, limit);
  if (picks.length === 0) return null;
  return (
    <div className="space-y-2">
      {picks.map((t, i) => (
        <div key={t.id || i} className="border-l-2 border-border pl-3">
          <p className="text-[11px] text-text-secondary leading-relaxed">
            {clipAtSentence(t.content, 180)}
          </p>
        </div>
      ))}
    </div>
  );
}

function clipAtSentence(text, max) {
  const s = String(text || '').trim();
  if (s.length <= max) return s;
  // 在 max 范围内找最后一个句末标点，从那里断；找不到就退到空格，
  // 再找不到才硬切——保证不会切出一个半截词。
  const window = s.slice(0, max);
  const stop = Math.max(
    window.lastIndexOf('。'), window.lastIndexOf('！'), window.lastIndexOf('？'),
    window.lastIndexOf('. '), window.lastIndexOf('\n'),
  );
  if (stop > max * 0.4) return window.slice(0, stop + 1) + ' …';
  const space = window.lastIndexOf(' ');
  if (space > max * 0.4) return window.slice(0, space) + ' …';
  return window + ' …';
}
