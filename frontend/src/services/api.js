// src/services/api.js

const JSON_HEADERS = { 'Content-Type': 'application/json' };

async function readError(response, fallback) {
  const err = await response.json().catch(() => ({}));
  throw new Error(err.error || fallback);
}

export async function analyzeKeyword(keyword, options = {}) {
  const { mode = 'multi-agent', platforms = ['微博', '小红书', '抖音'], srcMode = 'news' } = options;

  const response = await fetch('/api/analyze', {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({
      keyword,
      mode,
      platforms,
      srcMode,
    }),
  });

  if (!response.ok) {
    await readError(response, '分析请求失败');
  }

  return response.json(); // { task_id: '...' }
}

export async function fetchHistory() {
  const response = await fetch('/api/history');
  if (!response.ok) {
    await readError(response, '历史记录加载失败');
  }
  return response.json();
}

/**
 * 取一条历史记录的完整内容，用来"打开"那一场对话而不是重新分析。
 *
 * 返回 { task_id, keyword, status, time, restorable, turns, analysis_data }。
 * restorable 为 false 说明这次分析没有落盘完整结果（后端重启前跑的老任务），
 * 此时只能重新采集——调用方要明确告知用户，不能拿空数据冒充那次分析。
 */
export async function fetchTaskDetail(taskId) {
  const response = await fetch(`/api/history/${encodeURIComponent(taskId)}`);
  if (!response.ok) {
    await readError(response, '历史对话加载失败');
  }
  return response.json();
}

/**
 * 删除一条历史对话。
 *
 * 后端会同时清掉任务记录、完整结果 payload、以及项目记忆里的会话原文。
 * 正在分析中的任务会返回 409——那种任务的后台线程还活着，删了也会被写回。
 */
export async function deleteTask(taskId) {
  const response = await fetch(`/api/history/${encodeURIComponent(taskId)}`, {
    method: 'DELETE',
  });
  if (!response.ok) {
    await readError(response, '删除对话失败');
  }
  return response.json();
}

/**
 * 清空全部历史对话。
 *
 * 后端会跳过仍在分析中的任务（它的后台线程还活着，删了会被写回来）并如实
 * 报告跳过了几个——所以这里不能假设"返回成功就等于列表空了"，调用方要把
 * skipped 显示给用户。
 */
export async function clearHistory() {
  const response = await fetch('/api/history', { method: 'DELETE' });
  if (!response.ok) {
    await readError(response, '清空历史记录失败');
  }
  return response.json(); // { deleted, skipped, remaining }
}

// ── 自配模型 ────────────────────────────────────────────────────────────────

/**
 * 取模型列表与当前选用项。
 *
 * 返回的 api_key 是遮罩值（后 4 位）。完整 Key 不出这个接口，所以编辑表单里
 * 用户没改动 Key 时要原样提交遮罩串，后端会据此判断"不换 Key"。
 */
export async function fetchModels() {
  const response = await fetch('/api/models');
  if (!response.ok) {
    await readError(response, '模型列表加载失败');
  }
  return response.json(); // { models: [...], active_id }
}

/** 新增（不带 id）或更新（带 id）一个模型。 */
export async function saveModel(payload) {
  const response = await fetch('/api/models', {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    await readError(response, '保存模型失败');
  }
  return response.json();
}

export async function deleteModel(modelId) {
  const response = await fetch(`/api/models/${encodeURIComponent(modelId)}`, {
    method: 'DELETE',
  });
  if (!response.ok) {
    await readError(response, '删除模型失败');
  }
  return response.json();
}

/**
 * 切换当前选用的模型。传 null 表示回到 config.yaml 的默认配置。
 *
 * 换的是"下一次分析用哪个模型"：已经构造好的 Agent 会在下次调用时读到新
 * 配置，所以不必重启后端。
 */
export async function setActiveModel(modelId) {
  const response = await fetch('/api/models/active', {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({ id: modelId || '' }),
  });
  if (!response.ok) {
    await readError(response, '切换模型失败');
  }
  return response.json();
}

/** 项目列表（跨会话记忆的分组单位），每项附带会话摘要。 */
export async function fetchProjects() {
  const response = await fetch('/api/projects');
  if (!response.ok) {
    await readError(response, '项目列表加载失败');
  }
  return response.json();
}

/** 单个项目：会话原文 + 长期记忆。 */
export async function fetchProject(projectId) {
  const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}`);
  if (!response.ok) {
    await readError(response, '项目详情加载失败');
  }
  return response.json();
}

/** 按项目检索相关记忆与历史会话。 */
export async function recallMemories(projectId, query) {
  const params = new URLSearchParams({ project_id: projectId, q: query });
  const response = await fetch(`/api/recall?${params.toString()}`);
  if (!response.ok) {
    await readError(response, '记忆检索失败');
  }
  return response.json();
}

/** 手工追加一条项目记忆（用户自己确认的规则/决策）。 */
export async function addProjectMemory(projectId, content, kind = 'note') {
  const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}/memories`, {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({ content, kind }),
  });
  if (!response.ok) {
    await readError(response, '添加记忆失败');
  }
  return response.json();
}

/** 停用一条记忆（过时或提炼错误）。软删除，来源仍可查。 */
export async function retireMemory(memoryId) {
  const response = await fetch(`/api/memories/${encodeURIComponent(memoryId)}`, {
    method: 'DELETE',
  });
  if (!response.ok) {
    await readError(response, '删除记忆失败');
  }
  return response.json();
}

/**
 * 流式追问：读取 /api/followup 的 SSE 响应，逐段回调。
 *
 * 后端每帧为 {"chunk": "..."}，结束帧为 [DONE]，错误帧为 {"error": "..."}。
 * onChunk 收到增量文本；返回完整答案文本。
 */
export async function streamFollowup(taskId, message, { onChunk, signal } = {}) {
  const response = await fetch('/api/followup', {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({ task_id: taskId, query: message }),
    signal,
  });

  if (!response.ok || !response.body) {
    await readError(response, '追问请求失败');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let full = '';

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // SSE 帧以空行分隔； buffer 可能残留半个帧，留到下一轮
    const frames = buffer.split('\n\n');
    buffer = frames.pop() || '';

    for (const frame of frames) {
      const dataLine = frame.split('\n').find(l => l.startsWith('data:'));
      if (!dataLine) continue;
      const payload = dataLine.slice(5).trim();
      if (payload === '[DONE]') continue;
      try {
        const parsed = JSON.parse(payload);
        if (parsed.error) throw new Error(parsed.error);
        if (parsed.chunk) {
          full += parsed.chunk;
          onChunk?.(parsed.chunk, full);
        }
      } catch (e) {
        if (e instanceof SyntaxError) continue; // 忽略不完整帧
        throw e;
      }
    }
  }

  return full;
}

/** 非流式兜底：一次性拿完整答案（不推荐，会丢失打字机效果）。 */
export async function sendFollowup(taskId, message) {
  return streamFollowup(taskId, message);
}

/**
 * 追问触发新一轮红蓝辩论。
 *
 * 与 streamFollowup 的区别：这里会让红蓝双方就追问各自复辩、裁判再出补充
 * 裁定。发言通过 SocketIO 的 debate_turn / forum_message 实时推到房间，
 * 这个 HTTP 响应只用来告知"这一轮辩论跑完了"以及最终的补充裁定。
 *
 * ``resume=True`` 是"继续"：接着上一次被中止的轮次往下跑，红方已经说完的
 * 就不再问一遍。问题文本由服务端的续跑现场持有，前端传空即可。
 */
export async function debateFollowup(taskId, message, { resume = false } = {}) {
  const response = await fetch('/api/debate_followup', {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({ task_id: taskId, query: message, resume }),
  });

  if (!response.ok) {
    await readError(response, '追问辩论请求失败');
  }

  return response.json(); // { status, turns, verdict }
}

/**
 * 中止当前这轮追问。
 *
 * 中断不是瞬时的：orchestrator 在每一次 LLM 往返之后才检查停止标记，最坏
 * 情况要等当前那次请求返回。已经跑出来的发言会随下一次响应交回前端。
 */
export async function cancelFollowup(taskId) {
  const response = await fetch('/api/followup/cancel', {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({ task_id: taskId }),
  });
  if (!response.ok) {
    await readError(response, '中止追问失败');
  }
  return response.json();
}
