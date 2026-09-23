import React, { useState, useEffect, useRef } from 'react';
import { Share, Download, MessageSquare, Bot, AlertTriangle, TrendingUp, Send, CheckCircle2, ChevronRight, Gavel, Database, FileText, User, Sparkles } from 'lucide-react';
import clsx from 'clsx';
import VerdictCard from './VerdictCard';
import AnalysisProcess from './AnalysisProcess';
import DepthSelector, { resolveDepth } from './DepthSelector';

// 角色 → 卡片样式（与后端 ROLE_MAP 对应）
const ROLE_STYLES = {
  red: {
    label: '红方 · 危机分析师',
    icon: <AlertTriangle size={16} />,
    accent: 'text-danger',
    bar: 'bg-danger',
    bg: 'bg-danger/5',
    border: 'border-danger/25',
    badge: 'bg-danger/15 text-danger border-danger/25',
  },
  blue: {
    label: '蓝方 · 理性分析师',
    icon: <TrendingUp size={16} />,
    accent: 'text-agent-trend',
    bar: 'bg-agent-trend',
    bg: 'bg-agent-trend/5',
    border: 'border-agent-trend/25',
    badge: 'bg-agent-trend/15 text-agent-trend border-agent-trend/25',
  },
  collect: {
    label: '采集 Agent',
    icon: <Database size={16} />,
    accent: 'text-agent-spread',
    bar: 'bg-agent-spread',
    bg: 'bg-agent-spread/5',
    border: 'border-agent-spread/25',
    badge: 'bg-agent-spread/15 text-agent-spread border-agent-spread/25',
  },
  report: {
    label: '报告 Agent',
    icon: <FileText size={16} />,
    accent: 'text-agent-sentiment',
    bar: 'bg-agent-sentiment',
    bg: 'bg-agent-sentiment/5',
    border: 'border-agent-sentiment/25',
    badge: 'bg-agent-sentiment/15 text-agent-sentiment border-agent-sentiment/25',
  },
  agent: {
    label: '分析 Agent',
    icon: <MessageSquare size={16} />,
    accent: 'text-text-secondary',
    bar: 'bg-text-secondary',
    bg: 'bg-card',
    border: 'border-border',
    badge: 'bg-soft text-text-secondary border-border',
  },
};

export default function CenterWorkspace({
  onSelectAgent,
  onStartAnalysis,
  onSendFollowup,
  turns,
  followups,
  status,
  systemState,
  progress,
  currentQuery,
  taskId,
  followupStreaming,
  debatePending,
  restored,
  analysisData,
  depth,
  onDepthChange,
}) {
  const [inputValue, setInputValue] = useState('');
  const scrollRef = useRef(null);

  const isAnalyzing = status === 'analyzing';
  // 追问是一场完整的红蓝复辩：从发出问题到裁判给出新终裁，输入框必须锁住。
  // 不锁的话用户会在辩论中途再发一条，两轮发言交错，"第 N 轮"就串了。
  const busy = isAnalyzing || Boolean(debatePending);
  const hasSession = Boolean(currentQuery);

  // 研判卡由后端从实测指标算出，是这一屏的主视图。拿不到就退回聊天流——
  // 老任务（后端上线研判卡之前跑的）没有这个字段，不能因此什么都不显示。
  const verdictCard = analysisData?.verdict_card || null;

  // 新内容到达时自动滚动到底部
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [turns.length, followups.length, systemState, debatePending]);

  const handleSend = () => {
    const text = inputValue.trim();
    if (!text) return;
    if (hasSession && !busy) {
      onSendFollowup(text);
    } else if (!hasSession) {
      onStartAnalysis(text);
    }
    setInputValue('');
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const placeholder = isAnalyzing
    ? '正在分析中，请稍候...'
    : debatePending
      ? debatePending
      : hasSession ? '继续追问，红蓝双方将基于已采集的数据复辩...' : '输入你的分析目标，开始红蓝辩论...';

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden relative">
      <div className="h-14 border-b border-border/50 flex items-center justify-between px-6 shrink-0 bg-app/80 backdrop-blur-sm z-10">
        <div className="flex items-center gap-4">
          <h1 className="font-semibold text-text-main truncate max-w-sm">
            {currentQuery || '新的分析会话'}
          </h1>
          {hasSession && (
            <span className="text-[11px] text-text-secondary bg-soft px-2 py-1 rounded-full border border-border">
              {restored ? '历史对话' : verdictCard ? '态势研判 · 裁判终裁' : '红蓝辩论 · 裁判终裁'}
            </span>
          )}
          {/* 回放历史时"重新分析"必须是显式动作：点左侧记录要看的是那一次
              的原始结论，重新采集只会得到另一批数据。 */}
          {restored && hasSession && (
            <button
              onClick={() => onStartAnalysis(currentQuery)}
              disabled={busy}
              title="用同样的关键词重新采集并分析"
              className="text-[11px] text-accent hover:text-accent-strong disabled:opacity-50 bg-accent/10 hover:bg-accent/15 px-2.5 py-1 rounded-full border border-accent/25 transition-colors"
            >
              重新分析
            </button>
          )}
        </div>
        <div className="flex items-center gap-3">
          {isAnalyzing && (
            <span className="text-[11px] text-text-secondary tabular-nums">{progress}%</span>
          )}
          <div className="w-px h-4 bg-border mx-2" />
          <button
            onClick={() => onSelectAgent('evidence')}
            title="查看证据流"
            className="p-1.5 text-text-secondary hover:text-text-main hover:bg-hover rounded-md"
          >
            <Share size={16} />
          </button>
          <a
            href={taskId ? `/report/${taskId}` : undefined}
            title={taskId ? '查看 HTML 报告' : '分析完成后可查看报告'}
            target="_blank"
            rel="noreferrer"
            className={clsx(
              "p-1.5 rounded-md",
              taskId ? "text-text-secondary hover:text-text-main hover:bg-hover" : "text-text-secondary/30 pointer-events-none"
            )}
          >
            <Download size={16} />
          </a>
        </div>
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto px-6 py-6 pb-32 custom-scrollbar">
        {/* mx-auto 是关键：左右侧栏折叠后这一列会跟着变宽，没有 mx-auto 时
            内容死贴左边缘，看着像页面塌了半边。 */}
        <div className="max-w-4xl mx-auto space-y-5">

        {hasSession && (
          <div className="flex justify-end">
            <div className="bg-card border border-border rounded-card rounded-tr-sm p-4 max-w-2xl shadow-sm">
              <p className="text-sm">{currentQuery}</p>
              <div className="flex gap-2 mt-3">
                <span className="text-[10px] text-text-secondary bg-sidebar px-2 py-0.5 rounded-full">红蓝多轮辩论</span>
                <span className="text-[10px] text-text-secondary bg-sidebar px-2 py-0.5 rounded-full">裁判结构化终裁</span>
              </div>
            </div>
          </div>
        )}

        {systemState && (
          <div className="flex items-center justify-center">
            <div className="flex items-center gap-2 text-xs text-text-secondary bg-sidebar/50 px-4 py-1.5 rounded-full border border-border/50">
              {status === 'completed'
                ? <CheckCircle2 size={14} className="text-success" />
                : status === 'error'
                  ? <AlertTriangle size={14} className="text-danger" />
                  : <div className="w-3 h-3 border-2 border-accent border-t-transparent rounded-full animate-spin" />}
              <span>{systemState}</span>
            </div>
          </div>
        )}

        {debatePending && (
          <div className="flex items-center justify-center">
            <div className="flex items-center gap-2 text-xs text-accent bg-accent/10 px-4 py-1.5 rounded-full border border-accent/25">
              <div className="w-3 h-3 border-2 border-accent border-t-transparent rounded-full animate-spin" />
              <span>{debatePending}</span>
            </div>
          </div>
        )}

        {/* 主视图是研判卡，不是聊天流。有结论时把四段发言从主列撤下来，
            折叠进「分析过程」；分析进行中还没有结论，此时显示实时发言，
            让用户看到流水线确实在跑、而不是对着一块空白等。 */}
        {verdictCard ? (
          <>
            <VerdictCard card={verdictCard} />
            <AnalysisProcess
              turns={turns}
              verdict={analysisData?.verdict}
              defaultExpanded={resolveDepth(depth).expandProcess}
            />
          </>
        ) : (
          turns.map((turn) => (
            <TurnCard key={turn.id} turn={turn} onSelectAgent={onSelectAgent} />
          ))
        )}

        {followups.map((f) => (
          <FollowupBubble key={f.id} followup={f} />
        ))}

        {!hasSession && turns.length === 0 && (
          <div className="flex flex-col items-center justify-center py-16 text-text-secondary">
            <Sparkles size={32} className="mb-3 opacity-40" />
            <p className="text-sm">输入一个事件、品牌或话题，生成态势研判</p>
            <p className="text-xs mt-1 opacity-70">先给结论、风险等级与可验证的核心依据，分析过程折叠在后</p>
          </div>
        )}

        </div>
      </div>

      <div className="absolute bottom-0 left-0 w-full p-6 bg-gradient-to-t from-app via-app to-transparent pt-12 pointer-events-none">
        <div className="max-w-4xl mx-auto pointer-events-auto">
            <div className="flex justify-between items-center px-2 mb-2">
              <div className="flex gap-2">
                {['红方观点是否成立？', '蓝方的数据依据是什么？', '综合双方论据给出结论'].map(tag => (
                  <span
                    key={tag}
                    onClick={() => !busy && setInputValue(prev => prev + tag + ' ')}
                    className="text-[11px] text-text-secondary hover:text-text-main cursor-pointer bg-soft px-2 py-1 rounded-md border border-border"
                  >
                    {tag}
                  </span>
                ))}
              </div>
              <DepthSelector depth={depth} onChange={onDepthChange} />
            </div>

          <div className="bg-sidebar border border-border rounded-input shadow-lg flex flex-col p-2 focus-within:border-border/80 focus-within:ring-1 focus-within:ring-border/50 transition-all relative">
            <textarea
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={handleKeyDown}
              className="w-full bg-transparent border-none resize-none text-sm p-2 outline-none text-text-main placeholder-text-secondary/50 min-h-[60px]"
              placeholder={placeholder}
              disabled={busy}
            />
            <div className="flex justify-between items-center px-2 pb-1">
              <div className="flex items-center gap-2">
                <span className="text-xs text-text-secondary bg-soft px-2 py-0.5 rounded-md">
                  {hasSession ? '基于已采集数据复辩' : '红蓝辩论模式'}
                </span>
              </div>
              <button
                onClick={handleSend}
                disabled={busy || !inputValue.trim() || followupStreaming}
                className="bg-accent hover:bg-accent-strong disabled:bg-accent/50 disabled:cursor-not-allowed text-on-accent p-2 rounded-lg transition-colors"
              >
                <Send size={16} className="ml-0.5" />
              </button>
            </div>
          </div>
          {restored && (
            <p className="text-[11px] text-text-secondary mt-2 px-2 leading-relaxed">
              正在回放历史对话。追问需要该任务仍在本次服务运行中；后端重启后请点顶部的「重新分析」。
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

// 首轮辩论最多两轮（立论 + 反驳），追问产生的复辩从第 3 轮起编号。
// 后端 OrchestratorAgent.followup_round 同此约定。
const FOLLOWUP_ROUND_MIN = 3;

// 报告链接需要 task_id，由 MainLayout 通过 taskId prop 注入。

// 发言气泡的最大宽度。对话列本身是 max-w-4xl，气泡再收一档，
// 双方对峙时中间留出一道视觉间距，观感才像聊天而不是满屏表格。
const BUBBLE_MAX = 'max-w-[42rem]';

function RoundBadges({ turn, style }) {
  if (!(turn.round > 0)) return null;
  return (
    <>
      <span className={clsx("text-[10px] px-2 py-0.5 rounded-full border", style.badge)}>
        第 {turn.round} 轮
      </span>
      {FOLLOWUP_ROUND_MIN <= turn.round && (
        <span className="text-[10px] px-2 py-0.5 rounded-full border border-accent/25 bg-accent/10 text-accent">
          追问复辩
        </span>
      )}
    </>
  );
}

function TurnCard({ turn, onSelectAgent }) {
  // 裁判是流水线内的一等公民，位置和红蓝双方分开：居中通栏。
  if (turn.role === 'judge') {
    return <JudgeCard turn={turn} />;
  }
  const style = ROLE_STYLES[turn.role] || ROLE_STYLES.agent;

  // 采集 / 报告 / 未归类 Agent 不是辩论双方，渲染成居中的系统注记。
  // 硬塞进左右某一侧会让人误以为它们参与了立场对抗。
  if (turn.role !== 'red' && turn.role !== 'blue') {
    return (
      <div className="flex justify-center">
        <div className="max-w-md w-full bg-card/60 border border-border rounded-card p-3">
          <div className="flex items-center gap-2 mb-1.5">
            <span className={clsx("p-1 rounded-md bg-soft", style.accent)}>{style.icon}</span>
            <span className="font-medium text-xs text-text-main">{turn.label || style.label}</span>
            <RoundBadges turn={turn} style={style} />
          </div>
          <p className="text-xs text-text-secondary leading-relaxed whitespace-pre-wrap">{turn.content}</p>
        </div>
      </div>
    );
  }

  // 红蓝对峙：蓝（理性）居左，红（危机）居右。左右按角色固定，不随轮次
  // 翻转——否则第二轮互换位置，读者要重新找谁是谁。
  const isRed = turn.role === 'red';
  return (
    <div className={clsx('flex flex-col', isRed ? 'items-end' : 'items-start')}>
      <div className="flex items-center gap-2 mb-1 px-1">
        <span className={style.accent}>{style.icon}</span>
        <span className="font-medium text-xs text-text-main">{turn.label || style.label}</span>
        <RoundBadges turn={turn} style={style} />
      </div>
      <div
        className={clsx(
          'w-full p-4 rounded-card border shadow-sm',
          BUBBLE_MAX,
          style.bg,
          style.border,
          isRed ? 'rounded-tr-sm' : 'rounded-tl-sm'
        )}
      >
        <p className="text-sm text-text-main/90 leading-relaxed whitespace-pre-wrap">
          {turn.content}
        </p>
        <div className="flex items-center gap-3 mt-3 pt-3 border-t border-border/60">
          <button
            onClick={() => onSelectAgent('evidence')}
            className="text-xs text-text-secondary hover:text-text-main flex items-center gap-1 transition-colors"
          >
            查看证据 <ChevronRight size={12} />
          </button>
        </div>
      </div>
    </div>
  );
}

function JudgeCard({ turn }) {
  const isVerdict = turn.kind === 'verdict';
  const verdict = turn.verdict;

  return (
    <div className="mx-auto max-w-3xl bg-panel border border-border shadow-md rounded-panel p-6 relative overflow-hidden mt-6">
      <div className="absolute top-0 left-0 w-1 h-full bg-accent" />
      <div className="flex items-center gap-2 mb-4 flex-wrap">
        {isVerdict ? <Gavel className="text-accent" size={20} /> : <Bot className="text-accent" size={20} />}
        <h3 className="font-semibold text-base">{isVerdict ? '裁判终裁 (Judge)' : '裁判引导 (Judge)'}</h3>
        {turn.round > 0 && (
          <span className="text-[10px] text-text-secondary bg-soft px-2 py-0.5 rounded-full border border-border">
            第 {turn.round} 轮
          </span>
        )}
        {FOLLOWUP_ROUND_MIN <= turn.round && (
          <span className="text-[10px] text-accent bg-accent/10 px-2 py-0.5 rounded-full border border-accent/25">
            追问复辩
          </span>
        )}
      </div>

      {isVerdict && verdict && (
        <div className="flex flex-wrap gap-2 mb-4">
          <VerdictBadge verdict={verdict} />
        </div>
      )}

      <div className="space-y-4 text-sm text-text-main leading-relaxed whitespace-pre-wrap">
        {turn.content}
      </div>
    </div>
  );
}

const STANCE_META = {
  negative: { text: '看空', cls: 'bg-danger/15 text-danger border-danger/25' },
  neutral: { text: '中性', cls: 'bg-soft text-text-secondary border-border' },
  positive: { text: '看多', cls: 'bg-success/15 text-success border-success/25' },
};

const SIGNAL_META = {
  watch_out: { text: '警惕风险', cls: 'bg-danger/15 text-danger border-danger/25' },
  neutral: { text: '维持观察', cls: 'bg-soft text-text-secondary border-border' },
  buy_attention: { text: '值得关注', cls: 'bg-success/15 text-success border-success/25' },
};

function VerdictBadge({ verdict }) {
  const stance = STANCE_META[verdict.stance] || STANCE_META.neutral;
  const signal = SIGNAL_META[verdict.action_signal] || SIGNAL_META.neutral;
  const confidence = typeof verdict.confidence === 'number'
    ? `${Math.round(verdict.confidence * 100)}%`
    : null;

  return (
    <>
      <span className={clsx("text-[11px] px-2 py-1 rounded-full border font-medium", stance.cls)}>
        立场：{stance.text}
      </span>
      {confidence && (
        <span className="text-[11px] px-2 py-1 rounded-full border border-border bg-soft text-text-secondary">
          置信度 {confidence}
        </span>
      )}
      <span className={clsx("text-[11px] px-2 py-1 rounded-full border", signal.cls)}>
        信号：{signal.text}
      </span>
    </>
  );
}

function FollowupBubble({ followup }) {
  if (followup.role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="bg-accent/10 border border-accent/25 rounded-card rounded-tr-sm p-4 max-w-2xl">
          <div className="flex items-center gap-2 mb-1 text-accent">
            <User size={14} />
            <span className="text-xs font-medium">你的追问</span>
          </div>
          <p className="text-sm whitespace-pre-wrap">{followup.content}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-card border border-border rounded-card rounded-tl-sm p-4 max-w-2xl">
      <div className="flex items-center gap-2 mb-1 text-text-secondary">
        <Bot size={14} />
        <span className="text-xs font-medium">分析师回答</span>
        {followup.streaming && (
          <div className="w-2.5 h-2.5 border-2 border-accent border-t-transparent rounded-full animate-spin" />
        )}
      </div>
      <p className={clsx(
        "text-sm leading-relaxed whitespace-pre-wrap",
        followup.error ? "text-danger" : "text-text-main/90"
      )}>
        {followup.content}
        {followup.streaming && !followup.content && (
          <span className="text-text-secondary">正在生成回答...</span>
        )}
      </p>
    </div>
  );
}
