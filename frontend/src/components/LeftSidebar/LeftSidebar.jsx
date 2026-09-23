import React, { useMemo, useState } from 'react';
import {
  Search, Plus, MessageSquare, Clock, LayoutTemplate, PanelLeftClose,
  Hash, RefreshCw, Inbox, Sparkles, Radar, Sun, Moon, FolderOpen, Brain,
  ChevronDown, X, Trash2, Settings, Eraser,
} from 'lucide-react';
import clsx from 'clsx';
import { useTheme } from '../../theme';

const STATUS_META = {
  running: { dot: 'bg-accent', label: '分析中' },
  completed: { dot: 'bg-success', label: '已完成' },
  error: { dot: 'bg-danger', label: '失败' },
  waiting: { dot: 'bg-warning', label: '等待中' },
};

// 分析模板带一句说明：光有"舆情总览"四个字，用户不知道点下去会发生什么
// （会不会真的去采集？跑多久？）。说明写清楚它触发的是同一套红蓝辩论流水线。
const ANALYSIS_TEMPLATES = [
  { label: '舆情总览', hint: '全量采集 + 红蓝辩论 + 结构化终裁' },
  { label: '传播路径分析', hint: '侧重信源层级与时间扩散' },
  { label: '争议点提取', hint: '裁判重点梳理红蓝分歧' },
  { label: '风险预警', hint: '红方危机视角优先' },
];

const CAPABILITIES = [
  ['多源实时采集', 'Google News / DDG / Bing 三层回退'],
  ['信源可信度分级', 'T1 权威 → T4 待核验，分层统计'],
  ['情绪建模', 'SnowNLP 初判 + 大模型校正'],
  ['趋势预测', 'Prophet 时序 + 数据质量评级'],
  ['红蓝辩论终裁', '红方看空 / 蓝方理性 / 裁判裁定'],
];

export default function LeftSidebar({
  collapsed,
  onToggle,
  groups,
  onOpenSession,
  onQuickStart,
  onRefreshHistory,
  onNewAnalysis,
  onDeleteSession,
  onOpenSettings,
  activeTaskId,
}) {
  // 宽度由 MainLayout 的拖拽把手控制，本组件只负责"展开/收起"两个状态。
  // 收起时父组件直接不渲染本组件（改用一条竖排展开按钮），所以这里
  // 正常路径一定是展开态，不需要再写一套窄态布局。
  const { theme, toggleTheme } = useTheme();
  const [query, setQuery] = useState('');
  // 项目默认全部展开（多数用户只跟踪一两个主题），可手动折叠。
  // 搜索态下强制展开，否则用户搜完还要逐个点开项目。
  const [collapsedGroups, setCollapsedGroups] = useState(() => new Set());

  const list = Array.isArray(groups) ? groups : [];
  const total = list.reduce((n, g) => n + (g.conversations?.length || 0), 0);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    // 无搜索态：没有对话的组不进列表。项目是按会话分组的单位，一个组里
    // 一条对话都没有时，渲染出来只是个带 "0" 的空壳——用户刚清空完历史
    // 就会看到四五个这样的标题挂在"分析记录"底下，以为没删干净。
    // 项目记忆仍然保留在库里（那是跨会话沉淀的知识，不是某次对话的副本），
    // 只是不该由历史列表来展示。
    if (!q) return list.filter(g => (g.conversations || []).length > 0);
    return list
      .map(g => ({
        ...g,
        conversations: (g.conversations || []).filter(c =>
          `${c.title || ''} ${c.summary || ''}`.toLowerCase().includes(q)
        ),
      }))
      .filter(g => (g.conversations || []).length > 0 || (g.name || '').toLowerCase().includes(q));
  }, [list, query]);

  const toggleGroup = (id) => {
    setCollapsedGroups(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  // 搜索态下全部展开，否则用户搜完还要逐个点开项目
  const isCollapsed = (id) => query.trim() ? false : collapsedGroups.has(id);

  return (
    <div className="h-full bg-sidebar border-r border-border flex flex-col overflow-hidden">
      <div className="h-14 flex items-center justify-between px-4 shrink-0 border-b border-border">
        <div className="flex items-center gap-2.5 min-w-0">
          {/* 纯色标记，不用渐变：工程工具的品牌位是一个符号而不是一张海报 */}
          <span className="w-7 h-7 rounded-lg bg-accent flex items-center justify-center shrink-0">
            <Radar size={15} className="text-on-accent" />
          </span>
          <div className="min-w-0">
            <div className="font-bold text-sm tracking-widest text-text-main leading-none">GGB</div>
            <div className="text-[10px] text-text-secondary leading-none mt-1 truncate">红蓝辩论舆情研判</div>
          </div>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <button
            onClick={toggleTheme}
            title={theme === 'dark' ? '切换到亮色主题' : '切换到暗色主题'}
            aria-label="切换明暗主题"
            className="p-2 rounded-md hover:bg-hover text-text-secondary hover:text-text-main transition-colors"
          >
            {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
          </button>
          <button
            onClick={() => onOpenSettings?.('appearance')}
            title="设置：主题、字号、历史记录、模型与 API"
            aria-label="打开设置"
            className="p-2 rounded-md hover:bg-hover text-text-secondary hover:text-text-main transition-colors"
          >
            <Settings size={16} />
          </button>
          <button
            onClick={onToggle}
            title="收起左侧栏（可拖回）"
            className="p-2 rounded-md hover:bg-hover text-text-secondary hover:text-text-main transition-colors"
          >
            <PanelLeftClose size={16} />
          </button>
        </div>
      </div>

      <div className="px-4 pt-4 pb-3 shrink-0">
        <button
          onClick={onNewAnalysis}
          className="w-full flex items-center justify-center gap-2 bg-accent hover:bg-accent-strong active:bg-accent-strong text-on-accent rounded-lg transition-colors px-4 py-2.5 font-medium text-sm"
        >
          <Plus size={17} />
          <span className="font-medium text-sm">新建分析</span>
        </button>
        <p className="text-[11px] text-text-secondary mt-2 text-center leading-relaxed">
          输入事件、人物、品牌或话题
        </p>
      </div>

      {/* 历史检索。记录多起来之后，靠滚轮找某一次分析是不可接受的。 */}
      <div className="px-4 pb-3 shrink-0">
        <div className="relative">
          <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-text-secondary pointer-events-none" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="搜索历史对话"
            className="w-full bg-soft border border-border rounded-lg pl-8 pr-7 py-1.5 text-xs text-text-main placeholder-text-secondary/60 outline-none focus:border-accent/50 transition-colors"
          />
          {query && (
            <button
              onClick={() => setQuery('')}
              title="清空"
              className="absolute right-2 top-1/2 -translate-y-1/2 text-text-secondary hover:text-text-main"
            >
              <X size={12} />
            </button>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto overflow-x-hidden px-3 pb-3 space-y-5 custom-scrollbar">

        <section>
          <div className="flex items-center justify-between mb-2 px-1">
            <h3 className="text-[11px] font-semibold text-text-secondary uppercase tracking-wider flex items-center gap-1.5">
              <MessageSquare size={12} /> 历史对话
              {total > 0 && (
                <span className="text-text-secondary/60 font-normal tabular-nums">{total}</span>
              )}
            </h3>
            <div className="flex items-center gap-0.5">
              {/* 逐条删除在记录多起来之后不够用，批量管理放在设置面板里——
                  侧栏只留一个直达入口，不在这里展开第二套勾选界面。 */}
              <button
                onClick={() => onOpenSettings?.('history')}
                title="批量管理 / 清空历史记录"
                className="p-1 rounded hover:bg-hover text-text-secondary hover:text-text-main transition-colors"
              >
                <Eraser size={12} />
              </button>
              <button
                onClick={onRefreshHistory}
                title="刷新记录"
                className="p-1 rounded hover:bg-hover text-text-secondary hover:text-text-main transition-colors"
              >
                <RefreshCw size={12} />
              </button>
            </div>
          </div>

          <div className="space-y-1.5">
            {filtered.length === 0 ? (
              <div className="flex flex-col items-center gap-2 py-6 text-text-secondary">
                <Inbox size={20} className="opacity-40" />
                <span className="text-[11px]">
                  {query ? '没有匹配的历史对话' : '暂无分析记录'}
                </span>
              </div>
            ) : (
              filtered.map(group => (
                <ProjectGroup
                  key={group.id}
                  group={group}
                  collapsed={isCollapsed(group.id)}
                  onToggle={() => toggleGroup(group.id)}
                  onOpenSession={onOpenSession}
                  onDeleteSession={onDeleteSession}
                  activeTaskId={activeTaskId}
                />
              ))
            )}
          </div>
        </section>

        <section>
          <div className="flex items-center gap-2 text-[11px] font-semibold text-text-secondary uppercase tracking-wider mb-2 px-1">
            <LayoutTemplate size={12} /> 分析模板
          </div>
          <div className="space-y-1">
            {ANALYSIS_TEMPLATES.map(tpl => (
              <div
                key={tpl.label}
                onClick={() => onQuickStart?.(tpl.label)}
                title={tpl.hint}
                className="group px-3 py-2 rounded-lg cursor-pointer border border-transparent hover:border-border hover:bg-hover transition-colors"
              >
                <div className="flex items-center gap-2 text-sm text-text-main">
                  <Hash size={13} className="text-text-secondary group-hover:text-accent transition-colors" />
                  {tpl.label}
                </div>
                <div className="text-[10px] text-text-secondary/80 mt-0.5 pl-[21px] leading-snug">
                  {tpl.hint}
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* 把系统真实在做什么讲清楚，避免用户以为这只是个聊天框 */}
        <section>
          <div className="flex items-center gap-2 text-[11px] font-semibold text-text-secondary uppercase tracking-wider mb-2 px-1">
            <Sparkles size={12} /> 系统能力
          </div>
          <div className="rounded-lg border border-border bg-soft p-3 space-y-2">
            {CAPABILITIES.map(([title, desc]) => (
              <div key={title} className="flex gap-2">
                <span className="w-1 h-1 rounded-full bg-accent mt-1.5 shrink-0" />
                <div className="min-w-0">
                  <div className="text-[11px] text-text-main leading-tight">{title}</div>
                  <div className="text-[10px] text-text-secondary/80 leading-tight truncate">{desc}</div>
                </div>
              </div>
            ))}
          </div>
        </section>

      </div>
    </div>
  );
}

/**
 * 一个项目 = 同一关键词下的多场对话 + 这个项目的长期记忆。
 * 跨会话记忆的意义就在这一层：第二次分析同一主题时，前一次得出的结论
 * （含"已确认/待验证"状态）会作为背景进入双方视野。
 */
function ProjectGroup({ group, collapsed, onToggle, onOpenSession, onDeleteSession, activeTaskId }) {
  const convs = group.conversations || [];
  return (
    <div className="rounded-lg border border-border bg-soft/40 overflow-hidden">
      <button
        onClick={onToggle}
        className="w-full flex items-center gap-2 px-2.5 py-2 text-left hover:bg-hover transition-colors"
      >
        <FolderOpen size={13} className="text-accent shrink-0" />
        <span className="text-[12px] font-medium text-text-main truncate flex-1">{group.name}</span>
        {group.memoryCount > 0 && (
          <span
            title={`${group.memoryCount} 条项目记忆`}
            className="flex items-center gap-0.5 text-[10px] text-text-secondary shrink-0"
          >
            <Brain size={10} /> {group.memoryCount}
          </span>
        )}
        <span className="text-[10px] text-text-secondary tabular-nums shrink-0">{convs.length}</span>
        <ChevronDown
          size={12}
          className={clsx(
            "text-text-secondary shrink-0 transition-transform",
            collapsed && "-rotate-90"
          )}
        />
      </button>

      {!collapsed && (
        <div className="px-1.5 pb-1.5 space-y-0.5">
          {convs.length === 0 ? (
            <p className="text-[10px] text-text-secondary px-1.5 py-2">暂无对话</p>
          ) : (
            convs.map(c => (
              <SessionItem
                key={c.taskId}
                item={c}
                active={c.taskId === activeTaskId}
                onClick={() => onOpenSession?.(c.taskId)}
                onDelete={() => onDeleteSession?.(c.taskId)}
              />
            ))
          )}
        </div>
      )}
    </div>
  );
}

function SessionItem({ item, active, onClick, onDelete }) {
  const meta = STATUS_META[item.status] || STATUS_META.completed;
  // 删除是不可恢复的，确认放在条目内联做两步：第一次点露出"确认删除"，
  // 第二次才真正发请求。不用 window.confirm——它会中断浏览并禁用页面样式。
  const [confirming, setConfirming] = useState(false);
  const running = item.status === 'running' || item.status === 'waiting';

  const handleDelete = (e) => {
    e.stopPropagation();
    if (running) return;
    if (!confirming) {
      setConfirming(true);
      return;
    }
    onDelete?.();
  };

  return (
    <div
      onClick={onClick}
      title={`${item.title} · ${meta.label}${item.summary ? `\n${item.summary}` : ''}`}
      className={clsx(
        "group p-2 rounded-lg cursor-pointer transition-colors border",
        active
          ? "bg-accent/10 border-accent/25"
          : "border-transparent hover:border-border hover:bg-hover"
      )}
    >
      <div className="flex justify-between items-start gap-2 mb-0.5">
        <div className="font-medium text-[12px] text-text-main truncate">{item.title}</div>
        <div className={clsx("w-1.5 h-1.5 rounded-full shrink-0 mt-1", meta.dot)} />
      </div>
      {item.summary && (
        <p className="text-[10px] text-text-secondary/80 leading-snug line-clamp-2 mb-1">
          {item.summary}
        </p>
      )}
      <div className="flex items-center gap-2 text-[10px] text-text-secondary">
        <span className="flex items-center gap-1">
          <Clock size={9} /> {item.time || '--:--'}
        </span>
        {item.date && <span className="opacity-60">{item.date}</span>}
        {confirming ? (
          <>
            <button
              onClick={handleDelete}
              title="确认删除，不可恢复"
              className="ml-auto flex items-center gap-1 text-danger hover:text-danger/80 font-medium"
            >
              <Trash2 size={9} /> 确认删除
            </button>
            <button
              onClick={(e) => { e.stopPropagation(); setConfirming(false); }}
              title="取消"
              className="text-text-secondary hover:text-text-main"
            >
              取消
            </button>
          </>
        ) : (
          <button
            onClick={(e) => { e.stopPropagation(); setConfirming(true); }}
            disabled={running}
            title={running ? '分析进行中，暂不能删除' : '删除这条对话（含原始数据）'}
            className={clsx(
              "ml-auto flex items-center gap-1 transition-opacity",
              running
                ? "opacity-30 cursor-not-allowed"
                : "opacity-0 group-hover:opacity-100 hover:text-danger"
            )}
          >
            <Trash2 size={9} /> 删除
          </button>
        )}
      </div>
    </div>
  );
}
