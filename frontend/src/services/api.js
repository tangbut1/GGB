// src/services/api.js

export async function analyzeKeyword(keyword, mode = 'multi-agent', platforms = ['微博', '小红书', '抖音']) {
  // Use fetch instead of axios to reduce dependencies
  const response = await fetch('/api/analyze', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      keyword,
      mode,
      platforms
    })
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.error || '分析请求失败');
  }

  return response.json(); // { task_id: '...' }
}

export async function sendFollowup(taskId, message) {
  const response = await fetch('/api/followup', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      task_id: taskId,
      query: message
    })
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.error || '追问请求失败');
  }

  return response.json();
}
