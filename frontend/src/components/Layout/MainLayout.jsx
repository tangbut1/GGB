import React, { useState, useCallback, useEffect, useRef } from 'react';
import { PanelLeftOpen, PanelRightOpen } from 'lucide-react';
import LeftSidebar from '../LeftSidebar/LeftSidebar';
import CenterWorkspace from '../CenterWorkspace/CenterWorkspace';
import RightInsightPanel from '../RightInsightPanel/RightInsightPanel';
import { useAgentSocket } from '../../hooks/useAgentSocket';
import { analyzeKeyword, fetchHistory, fetchProjects, fetchTaskDetail, deleteTask } from '../../services/api';
import DepthSelector, { useAnalysisDepth, resolveDepth } from '../CenterWorkspace/DepthSelector';

// 侧栏宽度的取值范围。下限要能容纳图标 + 主按钮，上限按视口比例算，
// 不然 4K 屏上能把中间工作区挤到看不见。
const LEFT_MIN = 64;
const LEFT_MAX = 520;
const RIGHT_MIN = 320;
const RIGHT_MAX = 720;
// 双击把手回到这个宽度
const LEFT_DEFAULT = 280;
const RIGHT_DEFAULT = 360;

const clamp = (v, min, max) => Math.min(Math.max(v, min), max);

/** 把时间戳（秒）格式化成左栏用的 时间 + 日期。 */
function splitTime(value) {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    const raw = String(value || '');
    return { time: raw.split(' ')[1] || raw || '--:--', date: raw.split(' ')[0] || '' };
  }
  const d = new Date(value * 1000);
  const pad = (n) => String(n).padStart(2, '0');
  return {
    time: `${pad(d.getHours())}:${pad(d.getMinutes())}`,
    date: `${pad(d.getMonth() + 1)}-${pad(d.getDate())}`,
  };
}

/**
 * 左栏分组：项目（跨会话记忆的分组单位）在前，项目外的老记录归到
 * "未分组记录"。老记录指的是记忆层上线前跑的分析——task_history 里有，
 * 但没有 project_id，硬塞进某个项目等于编造归属。
 */
function buildGroups(projects, history) {
  const groups = (Array.isArray(projects) ? projects : []).map(p => ({
    id: p.project_id,
    name: p.name || '未命名项目',
    memoryCount: p.memory_count || 0,
    conversations: (p.conversations || []).map(c => {
      const t = splitTime(c.started_at);
      return {
        taskId: c.task_id,
        title: c.title || c.keyword || '未命名分析',
        summary: c.summary || '',
        status: c.status === 'error' ? 'error' : 'completed',
        ...t,
      };
    }),
  }));
  const known = new Set(groups.flatMap(g => g.conversations.map(c => c.taskId)));
  const loose = (Array.isArray(history) ? history : [])
    .filter(h => h?.task_id && !known.has(h.task_id))
    .map(h => ({ taskId: h.task_id, title: h.keyword || '未命名分析', summary: '', status: h.status || 'completed', ...splitTime(h.time) }));
  if (loose.length > 0) {
    groups.push({ id: '__loose__', name: '未分组记录', memoryCount: 0, conversations: loose });
  }
  return groups;
}

/**
 * 拖拽调宽把手。鼠标按下后进入"拖拽会话"：
 *  - 用 pointer events + setPointerCapture，指针移出把手甚至移出窗口都还能收到 move
 *  - 全局加 body.is-resizing，禁用文本选择并把光标锁成 col-resize
 *  - 宽度写进 state，松手即停；不持久化，刷新回到默认值
 */
function ResizeHandle({ side, width, min, max, onWidthChange, onDoubleClick }) {
  const [dragging, setDragging] = useState(false);
  const startX = useRef(0);
  const startWidth = useRef(0);

  const handlePointerDown = (e) => {
    // 只响应左键，避免和右键菜单/中键粘贴打架
    if (e.button !== 0) return;
    e.preventDefault();
    e.currentTarget.setPointerCapture(e.pointerId);
    startX.current = e.clientX;
    startWidth.current = width;
    setDragging(true);
    document.body.classList.add('is-resizing');
  };

  const handlePointerMove = (e) => {
    if (!dragging) return;
    // 左栏往右拖是变宽，右栏往左拖是变宽——方向相反
    const delta = side === 'left' ? e.clientX - startX.current : startX.current - e.clientX;
    onWidthChange(clamp(startWidth.current + delta, min, max));
  };

  const endDrag = (e) => {
    if (!dragging) return;
    if (e.currentTarget.hasPointerCapture?.(e.pointerId)) {
      e.currentTarget.releasePointerCapture(e.pointerId);
    }
    setDragging(false);
    document.body.classList.remove('is-resizing');
  };

  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label={side === 'left' ? '调整左侧栏宽度' : '调整右侧栏宽度'}
      title="拖拽调整宽度，双击还原"
      data-dragging={dragging ? 'true' : 'false'}
      className="resize-handle hidden lg:block"
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={endDrag}
      onPointerCancel={endDrag}
      onDoubleClick={onDoubleClick}
    />
  );
}

export default function MainLayout() {
  const [leftCollapsed, setLeftCollapsed] = useState(false);
  const [rightCollapsed, setRightCollapsed] = useState(false);
  const [leftWidth, setLeftWidth] = useState(LEFT_DEFAULT);
  const [rightWidth, setRightWidth] = useState(RIGHT_DEFAULT);
  const [activeTab, setActiveTab] = useState('trend');

  // App state
  const [currentTaskId, setCurrentTaskId] = useState(null);
  const [currentQuery, setCurrentQuery] = useState('');
  const [history, setHistory] = useState([]);
  const [groups, setGroups] = useState([]);
  // 非空表示正在回放一场历史对话。此时 useAgentSocket 不开 socket、不采集，
  // 直接把那一次的发言和分析数据播种进界面。
  const [restored, setRestored] = useState(null);

  // 查看深度。它决定结果默认展开到哪一层、右栏默认停在哪个 Tab——
  // 后端全量流水线每次都完整跑，这一档只影响呈现，不影响计算。
  const { depth, setDepth, meta: depthMeta } = useAnalysisDepth();

  // Socket hook
  const {
    turns, followups, status, systemState, progress,
    analysisData, followupStreaming, debatePending, sendFollowup,
  } = useAgentSocket(currentTaskId, restored);

  const loadHistory = useCallback(async () => {
    try {
      const list = await fetchHistory();
      setHistory(Array.isArray(list) ? list : []);
    } catch {
      setHistory([]);
    }
  }, []);

  const loadGroups = useCallback(async () => {
    try {
      const list = await fetchProjects();
      setGroups(buildGroups(list, history));
    } catch {
      setGroups(buildGroups([], history));
    }
  }, [history]);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  // 任务到达终态时刷新左侧历史。否则刚跑完的分析不会出现在"分析记录"
  // 里，列表仍显示"暂无分析记录"，用户会以为任务丢了。
  useEffect(() => {
    if (status === 'completed' || status === 'error') {
      loadHistory();
    }
  }, [status, loadHistory]);

  // 项目分组依赖 history（用于兜底老记录），history 到了再拉一次
  useEffect(() => {
    loadGroups();
  }, [loadGroups]);

  /**
   * 打开一场历史对话。和"重新分析"是两件事：点历史记录要看的是**那一次**
   * 采集到的数据和双方发言，重新采集只会拿到另一批数据。
   */
  const openSession = useCallback(async (taskId) => {
    if (!taskId) return;
    try {
      const detail = await fetchTaskDetail(taskId);
      setRestored(detail);
      setCurrentTaskId(detail.task_id || taskId);
      setCurrentQuery(detail.keyword || '');
      setActiveTab('trend');
    } catch (err) {
      alert(err.message || '打开历史对话失败');
    }
  }, []);

  const handleStartAnalysis = async (keyword) => {
    const text = keyword.trim();
    if (!text) return;
    // 分析进行中忽略重复启动：否则连点模板/历史会话会并发拉起多个
    // 孤儿任务，前端只跟踪最后一个，前面的结果全部丢失。
    if (status === 'analyzing') return;
    try {
      setRestored(null);
      setCurrentQuery(text);
      const res = await analyzeKeyword(text, { mode: 'multi-agent', srcMode: 'news' });
      setCurrentTaskId(res.task_id);
    } catch (err) {
      console.error(err);
      alert(err.message || '分析失败');
    }
  };

  const handleSendFollowup = useCallback(async (message) => {
    if (!currentTaskId) return;
    try {
      await sendFollowup(message);
    } catch (err) {
      console.error(err);
      alert(err.message || '追问失败');
    }
  }, [currentTaskId, sendFollowup]);

  /**
   * 删除一条历史对话。
   *
   * 删的是磁盘上的任务记录、完整结果和项目记忆里的会话原文——不可恢复，
   * 所以确认放在调用方（左栏）做，这里只负责发请求和同步三份状态：
   * 历史列表、项目分组、以及"当前正在看的那一场"。如果删的正是当前场次，
   * 必须立刻清空主区，否则界面还留着一段已经不存在的数据。
   */
  const handleDeleteSession = useCallback(async (taskId) => {
    if (!taskId) return;
    try {
      await deleteTask(taskId);
      setHistory(prev => prev.filter(h => h.task_id !== taskId));
      setGroups(prev => prev
        .map(g => ({ ...g, conversations: (g.conversations || []).filter(c => c.taskId !== taskId) }))
        .filter(g => (g.conversations || []).length > 0 || g.id === '__loose__'));
      if (currentTaskId === taskId) {
        setRestored(null);
        setCurrentTaskId(null);
        setCurrentQuery('');
      }
    } catch (err) {
      alert(err.message || '删除对话失败');
    }
  }, [currentTaskId]);

  const handleNewAnalysis = useCallback(() => {
    setRestored(null);
    setCurrentTaskId(null);
    setCurrentQuery('');
    setActiveTab('trend');
  }, []);

  // 换深度时把右栏切到该档的默认 Tab。用户选了"深度审计"却还停在核心指标
  // 上，等于这一档没生效——切过去才是"我会拿到什么"的即时反馈。
  const handleDepthChange = useCallback((next) => {
    setDepth(next);
    setActiveTab(resolveDepth(next).tab);
  }, [setDepth]);

  // 折叠时把手也要能点：整条都收起来之后，用户需要一个明显的入口把它拉回来。
  // 这里在折叠态下保留一个常驻小按钮，不依赖把手的热区。
  return (
    <div className="flex h-screen w-full bg-app overflow-hidden text-text-main">
      {!leftCollapsed && (
        <>
          <div style={{ width: leftWidth }} className="shrink-0">
            <LeftSidebar
              collapsed={false}
              onToggle={() => setLeftCollapsed(true)}
              groups={groups}
              onOpenSession={openSession}
              onRerun={handleStartAnalysis}
              onRefreshHistory={() => { loadHistory(); loadGroups(); }}
              onNewAnalysis={handleNewAnalysis}
              onDeleteSession={handleDeleteSession}
              activeTaskId={currentTaskId}
            />
          </div>
          <ResizeHandle
            side="left"
            width={leftWidth}
            min={LEFT_MIN}
            max={LEFT_MAX}
            onWidthChange={setLeftWidth}
            onDoubleClick={() => setLeftWidth(LEFT_DEFAULT)}
          />
        </>
      )}

      {/* 左栏收起后的展开入口 */}
      {leftCollapsed && (
        <button
          onClick={() => setLeftCollapsed(false)}
          title="展开左侧栏"
          className="hidden lg:flex items-center justify-center w-6 shrink-0 border-r border-border bg-sidebar/60 text-text-secondary hover:text-accent hover:bg-sidebar transition-colors"
        >
          <PanelLeftOpen size={14} />
        </button>
      )}

      <div className="flex-1 min-w-0 flex flex-col border-r border-border bg-app">
        <CenterWorkspace
          onSelectAgent={(type) => setActiveTab(type)}
          onStartAnalysis={handleStartAnalysis}
          onSendFollowup={handleSendFollowup}
          turns={turns}
          followups={followups}
          status={status}
          systemState={systemState}
          progress={progress}
          currentQuery={currentQuery}
          taskId={currentTaskId}
          followupStreaming={followupStreaming}
          debatePending={debatePending}
          restored={Boolean(restored)}
          analysisData={analysisData}
          depth={depth}
          onDepthChange={handleDepthChange}
        />
      </div>

      {!rightCollapsed && (
        <>
          <ResizeHandle
            side="right"
            width={rightWidth}
            min={RIGHT_MIN}
            max={RIGHT_MAX}
            onWidthChange={setRightWidth}
            onDoubleClick={() => setRightWidth(RIGHT_DEFAULT)}
          />
          <div style={{ width: rightWidth }} className="shrink-0 bg-panel border-l border-border flex flex-col">
            <RightInsightPanel
              activeTab={activeTab}
              onTabChange={setActiveTab}
              analysisData={analysisData}
              onCollapse={() => setRightCollapsed(true)}
              depth={depth}
            />
          </div>
        </>
      )}

      {/* 右栏收起后的展开入口 */}
      {rightCollapsed && (
        <button
          onClick={() => setRightCollapsed(false)}
          title="展开右侧研究面板"
          className="hidden lg:flex items-center justify-center w-6 shrink-0 border-l border-border bg-panel/60 text-text-secondary hover:text-accent hover:bg-panel transition-colors"
        >
          <PanelRightOpen size={14} />
        </button>
      )}
    </div>
  );
}
