// src/services/api.js
// Unified API layer with centralized error handling

const BASE_URL = '/api';

/**
 * Centralized fetch wrapper with error handling and toast dispatch.
 */
async function request(endpoint, options = {}) {
  const url = `${BASE_URL}${endpoint}`;
  const config = {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  };

  let response;
  try {
    response = await fetch(url, config);
  } catch (networkErr) {
    const msg = '网络连接失败，请检查后端服务是否启动';
    dispatchToast('error', msg);
    throw new Error(msg);
  }

  // Try to parse error body
  let body = {};
  try { body = await response.json(); } catch (_) { /* non-JSON response */ }

  if (!response.ok) {
    const message = body.error || body.message || `请求失败 (${response.status})`;
    dispatchToast('error', message);
    const err = new Error(message);
    err.status = response.status;
    err.body = body;
    throw err;
  }

  return body;
}

function dispatchToast(type, message) {
  try {
    window.dispatchEvent(new CustomEvent('app:toast', {
      detail: { type, message }
    }));
  } catch (_) { /* ignore if not supported */ }
}

// ── API functions ──────────────────────────────────────────────────

export async function analyzeKeyword(keyword, mode = 'multi-agent', platforms = ['微博', '小红书', '抖音']) {
  return request('/analyze', {
    method: 'POST',
    body: JSON.stringify({ keyword, mode, platforms })
  });
  // Returns { task_id: '...' }
}

export async function sendFollowup(taskId, message) {
  return request('/followup', {
    method: 'POST',
    body: JSON.stringify({ task_id: taskId, query: message })
  });
}

export async function getTaskStatus() {
  return request('/status');
}

export async function getTaskHistory() {
  return request('/history');
}

export async function getReport(taskId) {
  return request(`/report/${taskId}`);
}

export async function searchKnowledge(query, limit = 10) {
  return request(`/knowledge/search?q=${encodeURIComponent(query)}&limit=${limit}`);
}
