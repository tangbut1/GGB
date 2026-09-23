import { useEffect, useRef, useState, useCallback } from 'react';
import { io } from 'socket.io-client';
import { debateFollowup, cancelFollowup } from '../services/api';

// 与后端 ROLE_MAP 对应：前端按 role 渲染红/蓝/裁判/采集卡片
const ROLE_BY_AGENT = {
  CollectAgent: 'collect',
  SentimentAgent: 'red',
  TrendAgent: 'blue',
  ReportAgent: 'report',
  HOST: 'judge',
};

const AGENT_LABELS = {
  CollectAgent: '采集 Agent',
  SentimentAgent: '红方 · 危机分析师',
  TrendAgent: '蓝方 · 理性分析师',
  ReportAgent: '报告 Agent',
  HOST: '裁判 · Judge',
};

function normalizeTurn(data) {
  const author = data.author || data.agent || 'Unknown';
  return {
    author,
    label: AGENT_LABELS[author] || author,
    role: data.role || ROLE_BY_AGENT[author] || 'agent',
    round: Number(data.round) || 0,
    content: data.content || '',
    kind: 'agent',
  };
}

/**
 * 后端 /history/<task_id> 回放的发言已是最终形态（id/label/kind/verdict 都有），
 * 这里只做兜底：补齐缺失字段、去掉空内容、保证 id 唯一。
 * 直接信任返回值得到一个 React key 为 undefined 的列表，控制台会刷屏告警。
 */
function normalizeRestoredTurns(turns) {
  if (!Array.isArray(turns)) return [];
  const seen = new Set();
  const out = [];
  turns.forEach((t, i) => {
    const content = t?.content || '';
    if (!content.trim()) return;
    let id = t.id || `restored_${i}`;
    while (seen.has(id)) id = `${id}_${i}`;
    seen.add(id);
    out.push({
      id,
      author: t.author || 'Unknown',
      label: t.label || AGENT_LABELS[t.author] || t.author || 'Agent',
      role: t.role || ROLE_BY_AGENT[t.author] || 'agent',
      round: Number(t.round) || 0,
      content,
      kind: t.kind || (t.role === 'judge' ? 'verdict' : 'agent'),
      verdict: t.verdict || null,
    });
  });
  return out;
}

/**
 * @param taskId 当前任务 id；为空表示没有进行中的会话
 * @param restored 历史对话载荷（/history/<task_id> 的返回值）。非空时进入
 *        "只读回放"模式：不开 socket、不重新采集，直接把那一场的发言与
 *        分析数据播种进状态。红蓝辩论的追问仍可用（走 /debate_followup）。
 */
export function useAgentSocket(taskId, restored) {
  const [socket, setSocket] = useState(null);
  const [turns, setTurns] = useState([]);
  const [followups, setFollowups] = useState([]);
  const [status, setStatus] = useState('idle'); // idle, analyzing, completed, error
  const [systemState, setSystemState] = useState('');
  const [progress, setProgress] = useState(0);
  const [analysisData, setAnalysisData] = useState(null);
  const [usage, setUsage] = useState(null);
  const [followupStreaming, setFollowupStreaming] = useState(false);
  // 追问辩论状态：null=空闲，字符串=当前阶段提示。追问是同步跑完的，
  // 期间输入框要禁用，否则用户会在辩论中途再发一条，两轮辩论的发言交错
  // 在一起，卡片上的"第 N 轮"就串了。
  const [debatePending, setDebatePending] = useState(null);
  // 非 null 表示上一轮追问被用户中止、且还没续跑。前端据此显示"继续"按钮。
  // 只有"中止"会产生这个状态：正常结束、失败、以及用户另发新问题都会清掉它。
  const [followupCancelled, setFollowupCancelled] = useState(null);

  // 去重：同一 (author, round, content) 只渲染一次
  const seenTurns = useRef(new Set());
  const completedRef = useRef(false);

  useEffect(() => {
    // 新建分析（taskId 置空）时把会话状态整体复位。若上一场分析异常终止
    // （没收到 task_complete），不复位会让 status 永远停在 analyzing，
    // 输入框保持禁用，用户再也无法开始新分析。
    if (!taskId) {
      setSocket(null);
      setStatus('idle');
      setTurns([]);
      setFollowups([]);
      setAnalysisData(null);
      setProgress(0);
      setSystemState('');
      setDebatePending(null);
      setFollowupCancelled(null);
      return;
    }

    seenTurns.current = new Set();
    completedRef.current = false;

    // ── 历史回放：没有 socket 生命周期，直接播种 ──
    // 上一场还在跑时用户点了历史记录，socket 必须在这里断掉，否则旧的
    // task_complete 会覆盖回放状态。
    if (restored) {
      setSocket(null);
      const ok = restored.status === 'completed' && restored.restorable !== false;
      setStatus(ok ? 'completed' : 'error');
      setProgress(100);
      setSystemState(
        ok
          ? '已打开历史对话'
          : (restored.restorable === false
            ? '该次分析没有留存完整结果，无法回放原文'
            : '该次分析未正常结束')
      );
      setTurns(normalizeRestoredTurns(restored.turns));
      setFollowups([]);
      setAnalysisData(restored.analysis_data || null);
      setDebatePending(null);
      setFollowupCancelled(null);
      return;
    }

    let disposed = false;
    let reconnectTimer = null;
    const newSocket = io({
      path: '/socket.io',
      transports: ['websocket', 'polling'],
    });

    setSocket(newSocket);
    setStatus('analyzing');
    setTurns([]);
    setFollowups([]);
    setAnalysisData(null);
    setProgress(0);
    setSystemState('已开始分析...');

    newSocket.on('connect', () => {
      if (reconnectTimer) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }
      newSocket.emit('join', { task_id: taskId });
      // 长轮询掉线后会自动重连：重新 join 时后端会回放全部发言、
      // 裁判事件和（已结束任务的）终态，这里把断开提示撤掉，
      // 恢复等待状态，除非早已收到完成事件。
      if (!completedRef.current) {
        setStatus('analyzing');
        setSystemState('已重新连接，正在同步分析进度...');
      }
    });

    // 辩论发言（后台日志广播器统一推送，结构已归一）
    newSocket.on('debate_turn', (data) => {
      const turn = normalizeTurn(data);
      if (!turn.content) return;
      const key = `${turn.author}|${turn.round}|${turn.content}`;
      if (seenTurns.current.has(key)) return;
      seenTurns.current.add(key);
      setTurns(prev => [...prev, { ...turn, id: key }]);
    });

    // 裁判事件：中期引导 / 结构化终裁
    newSocket.on('forum_message', (data) => {
      if (!data?.content) return;
      const key = `HOST|${data.round || 0}|${data.kind || 'guidance'}|${data.content}`;
      if (seenTurns.current.has(key)) return;
      seenTurns.current.add(key);
      setTurns(prev => [...prev, {
        id: key,
        author: 'HOST',
        label: data.kind === 'verdict' ? '裁判终裁' : '裁判引导',
        role: 'judge',
        round: Number(data.round) || 0,
        content: data.content,
        kind: data.kind === 'verdict' ? 'verdict' : 'guidance',
        verdict: data.verdict || null,
      }]);
    });

    newSocket.on('api_usage_update', (data) => setUsage(data));

    // 追问辩论产生的新终裁。右侧"终裁"Tab 和中间的最新终裁卡片要跟着换，
    // 否则用户追问完看到的还是首轮那份裁定。
    newSocket.on('verdict_update', (data) => {
      if (!data?.verdict) return;
      setAnalysisData(prev => (prev ? { ...prev, verdict: data.verdict } : prev));
    });

    // 追问辩论期间后端会把 agent_update 的 progress 推到 74/82/88/100，
    // round 大于 2 就说明这是用户追问引发的轮次，用它驱动阶段提示。
    newSocket.on('agent_update', (data) => {
      if (Number(data.round) > 2) {
        const who = data.agent === 'SentimentAgent' ? '红方'
          : data.agent === 'TrendAgent' ? '蓝方'
            : data.agent === 'HOST' ? '裁判' : data.agent;
        const doing = data.status === 'active' ? '正在就你的追问复辩'
          : data.status === 'done' ? '已完成本轮发言' : '发言异常';
        setDebatePending(`${who}${doing}`);
        return;
      }
      const statusText = data.status === 'active' ? '运行中'
        : data.status === 'done' ? '已完成' : '异常';
      setSystemState(`${data.agent} ${statusText}`);
      if (typeof data.progress === 'number') setProgress(data.progress);
    });

    // 后端重启/网络中断时流水线不会再发 task_complete，不能把用户
    // 永久困在"分析中"。但 threading 模式下只有 HTTP 长轮询，客户端
    // 会在轮询切换时周期性掉线又立刻重连——这种抖动不是故障：一旦立刻
    // 判失败，输入框会被提前解禁，下一次 connect 又把它拉回"分析中"，
    // 用户只看到状态闪跳和一句"分析可能未完成"的误报。所以先给一个
    // 宽限期，只有始终没重连才真正标记中断。
    newSocket.on('disconnect', () => {
      if (disposed) return;
      setSystemState('连接抖动，正在自动重连...');
      reconnectTimer = setTimeout(() => {
        if (disposed || newSocket.connected || completedRef.current) return;
        setStatus('error');
        setSystemState('连接已断开，分析可能未完成，请重新开始');
      }, 15000);
    });

    // 'error' 是传输层错误（长轮询单次请求失败等），不是业务错误：
    // 业务失败一律由 task_complete(status='error') 传达。socket.io 会
    // 自动重试，这里只做一句不带结论的提示，不改变 status。
    newSocket.on('error', () => {
      if (disposed) return;
      setSystemState('网络波动，正在自动重连...');
    });

    newSocket.on('task_complete', (data) => {
      completedRef.current = true;
      setStatus(data.status);
      setProgress(100);
      // 失败时优先显示后端给的原因（如"服务已重启，任务不存在"），
      // 笼统的"分析终止"对用户没有任何可操作的指引。
      setSystemState(
        data.status === 'completed'
          ? '分析完成'
          : (data.message || '分析终止')
      );
      if (data.data) setAnalysisData(data.data);
    });

    return () => {
      disposed = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      newSocket.disconnect();
    };
  }, [taskId, restored]);

  // 追问 = 新一轮红蓝辩论。发言由 SocketIO 的 debate_turn / forum_message
  // 实时推进（和首轮同一条渲染管线），这里只负责发问、等待和收尾。
  const sendFollowup = useCallback(async (message) => {
    if (!taskId || !message.trim() || followupStreaming || debatePending) return;

    const question = message.trim();
    setFollowups(prev => [...prev, {
      id: `u_${Date.now()}`,
      role: 'user',
      content: question,
    }]);
    // 新问题是一个新指令：上一轮留下的"可续跑"状态到此作废
    setFollowupCancelled(null);
    setDebatePending('红蓝双方正在就你的追问复辩');

    try {
      const res = await debateFollowup(taskId, question);
      if (res?.status === 'cancelled') {
        setFollowupCancelled(res.message || '已中止本轮追问');
        return;
      }
      if (res?.verdict) {
        setAnalysisData(prev => (prev ? { ...prev, verdict: res.verdict } : prev));
      }
      const answered = (res?.turns || []).length;
      if (answered === 0) {
        setFollowups(prev => [...prev, {
          id: `e_${Date.now()}`,
          role: 'assistant',
          content: '本轮追问没有得到任何一方的发言，请检查 LLM 配置后重试。',
          error: true,
        }]);
      }
    } catch (err) {
      if (err.name !== 'AbortError') {
        setFollowups(prev => [...prev, {
          id: `e_${Date.now()}`,
          role: 'assistant',
          content: `追问失败：${err.message}`,
          error: true,
        }]);
      }
    } finally {
      setDebatePending(null);
    }
  }, [taskId, followupStreaming, debatePending]);

  /**
   * 中止当前这轮追问。
   *
   * 只发一个停止标记就返回，不等辩论真的停下来——真正的中断发生在后端下一
   * 次 LLM 往返之后，由 sendFollowup 那次 await 收到 status=cancelled 来收尾。
   * 所以这里不能清 debatePending，否则输入框会在辩论还在跑的时候解禁。
   */
  const stopFollowup = useCallback(async () => {
    if (!taskId || debatePending) return;
    try {
      await cancelFollowup(taskId);
    } catch (err) {
      // 停止请求本身失败（网络抖动等）不改变界面状态：用户会看到辩论继续
      // 跑完，这比弹一个错又留下一个按了没反应的按钮要好。
      console.error('中止追问失败', err);
    }
  }, [taskId, debatePending]);

  /**
   * 续跑被中止的那一轮。
   *
   * 服务端持有"这一轮进行到哪了"：红方已经说完的不会再问一遍，直接从蓝方或
   * 裁判接着跑。问题原文也由服务端保留——用户中途改输入框不该影响正在续的
   * 这一轮，所以这里不传问题。
   */
  const resumeFollowup = useCallback(async () => {
    if (!taskId || followupStreaming || debatePending) return;
    setDebatePending('正在接着中止处继续复辩');
    try {
      const res = await debateFollowup(taskId, '', { resume: true });
      if (res?.status === 'cancelled') {
        setFollowupCancelled(res.message || '已中止本轮追问');
        return;
      }
      setFollowupCancelled(null);
      if (res?.verdict) {
        setAnalysisData(prev => (prev ? { ...prev, verdict: res.verdict } : prev));
      }
      const answered = (res?.turns || []).length;
      if (answered === 0) {
        setFollowups(prev => [...prev, {
          id: `e_${Date.now()}`,
          role: 'assistant',
          content: '续跑没有得到任何一方的发言，请检查 LLM 配置后重试。',
          error: true,
        }]);
      }
    } catch (err) {
      setFollowupCancelled(null);
      if (err.name !== 'AbortError') {
        setFollowups(prev => [...prev, {
          id: `e_${Date.now()}`,
          role: 'assistant',
          content: `续跑失败：${err.message}`,
          error: true,
        }]);
      }
    } finally {
      setDebatePending(null);
    }
  }, [taskId, followupStreaming, debatePending]);

  /**
   * 放弃续跑。用户看到"已中止"的提示但不打算继续时，把这条提示收掉——
   * 否则它会一直挂在输入框上方，而用户其实已经决定换下一个问题了。
   */
  const dismissFollowupCancel = useCallback(() => setFollowupCancelled(null), []);

  return {
    socket,
    turns,
    followups,
    status,
    systemState,
    progress,
    analysisData,
    usage,
    followupStreaming,
    debatePending,
    followupCancelled,
    sendFollowup,
    stopFollowup,
    resumeFollowup,
    dismissFollowupCancel,
  };
}
