import re

with open('MarketPulse/templates/index.html', 'r', encoding='utf-8') as f:
    html = f.read()

css_addition = """
/* ── Chat Panel ── */
.chat-panel {
  display: flex; flex-direction: column; background: var(--s0);
}
.chat-header {
  height: 56px; border-bottom: 1px solid var(--b); padding: 0 20px;
  display: flex; justify-content: space-between; align-items: center;
  background: var(--bg); flex-shrink: 0;
}
.chat-messages {
  flex: 1; overflow-y: auto; padding: 20px; background: var(--bg);
  display: flex; flex-direction: column; gap: 16px; scroll-behavior: smooth;
}
.chat-empty {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  height: 100%; color: var(--tx3); font-size: 14px;
}
.chat-input-area {
  padding: 16px 20px; background: var(--bg); border-top: 1px solid var(--b);
  flex-shrink: 0;
}
.chat-input-area .search-wrap {
  background: var(--s1); box-shadow: 0 4px 20px rgba(0,0,0,0.05); border-color: var(--bhi);
}
.chat-msg {
  display: flex; flex-direction: column; width: 100%;
}
.chat-left { align-items: flex-start; }
.chat-right { align-items: flex-end; }
.chat-center { align-items: center; }

.chat-bubble {
  max-width: 80%; background: var(--s1); padding: 12px 16px; border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.04); border: 1px solid var(--b);
  position: relative;
}
.chat-left .chat-bubble { border-bottom-left-radius: 4px; }
.chat-right .chat-bubble { border-bottom-right-radius: 4px; background: #fff8f8; }
[data-theme="dark"] .chat-right .chat-bubble { background: rgba(224,108,117,0.05); }

.chat-name {
  font-size: 11px; font-weight: 600; color: var(--tx2); margin-bottom: 6px;
}
.chat-content {
  font-size: 13px; line-height: 1.6; color: var(--tx); white-space: pre-wrap; word-break: break-word;
}
"""

html = html.replace('/* ── Main Layout ── */', css_addition + '\n/* ── Main Layout ── */')

# HTML replace:
main_start = html.find('<main>')
main_end = html.find('</main>')
main_content = html[main_start:main_end+7]

import sys

# Replace the middle-panel HTML
new_main_content = """<main>
<!-- ⚠️ API 配置提醒 -->
<div class="api-warning-banner" id="apiWarningBanner" style="display:none">
  <div class="api-warning-icon">⚠️</div>
  <div class="api-warning-body">
    <div class="api-warning-title">部分 Agent API Key 未配置</div>
    <div class="api-warning-list" id="apiWarningList"></div>
    <div class="api-warning-hint">LLM 调用将使用模拟数据返回占位结果。请编辑 <code>MarketPulse/.env</code> 填入真实 API Key 后重启服务。</div>
  </div>
  <button class="api-warning-close" onclick="document.getElementById('apiWarningBanner').style.display='none'">✕</button>
</div>

<!-- LEFT PANEL -->
<div class="left-panel" id="leftPanel">
  <div class="panel-header">
    <div class="panel-title">
      <div class="panel-title-icon"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="var(--ac)" stroke-width="2.5"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg></div>
      AGENT 论坛辩论区
    </div>
    <div style="display:flex;align-items:center;gap:6px;">
      <div class="status-pill" id="statusPill"><span class="dot"></span> 空闲</div>
    </div>
  </div>
  <div class="agent-rows">
    <div class="agent-row" id="row-CollectAgent"><div class="agent-info"><div class="agent-name">CollectAgent</div><div class="agent-sub">数据采集与清洗</div></div><div class="status-dot"></div></div>
    <div class="agent-row" id="row-SentimentAgent"><div class="agent-info"><div class="agent-name">SentimentAgent</div><div class="agent-sub">情感分析与研判</div></div><div class="status-dot"></div></div>
    <div class="agent-row" id="row-TrendAgent"><div class="agent-info"><div class="agent-name">TrendAgent</div><div class="agent-sub">趋势预测与建模</div></div><div class="status-dot"></div></div>
    <div class="agent-row" id="row-ReportAgent"><div class="agent-info"><div class="agent-name">ReportAgent</div><div class="agent-sub">报告生成与导出</div></div><div class="status-dot"></div></div>
  </div>
  <div class="progress-wrap">
    <div class="progress-info"><span id="progressLabel">就绪</span><span id="progressPct" style="font-family:var(--mono)">0%</span></div>
    <div class="progress-track"><div class="progress-fill" id="progressFill"></div></div>
  </div>
  <div class="panel-header" style="margin-top:16px; border-top:1px solid var(--b); padding-top:16px;">
    <div class="panel-title">
      <div class="panel-title-icon"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg></div>
      历史对话记录
    </div>
  </div>
  <div class="history-container" id="historyContainer">
    <div style="padding:12px; font-size:12px; color:var(--tx3); text-align:center;">暂无历史记录</div>
  </div>
</div>

<!-- GLOBAL RESIZER 1 -->
<div class="global-resizer" id="globalResizer"><div class="global-resizer-handle"></div></div>

<!-- MIDDLE PANEL: CHAT UI -->
<div class="middle-panel chat-panel" id="middlePanel">
  <div class="chat-header">
    <div style="font-weight:600;font-size:14px;color:var(--tx);display:flex;align-items:center;gap:8px;">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--ac)" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>
      红蓝对抗实时推演
    </div>
    <div style="font-size:12px;color:var(--tx3);font-family:var(--mono);" id="logCount">0 条记录</div>
  </div>
  
  <div class="chat-messages" id="logContainer">
    <div class="chat-empty" id="chatEmpty">
      <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="var(--bhi)" stroke-width="1.5"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>
      <p style="margin-top:16px;">在下方输入关键词启动多Agent推演</p>
    </div>
  </div>
  
  <div class="chat-input-area">
      <div class="center-search-area" id="centerSearchArea" style="max-width:100%;margin:0;">
        <div class="center-search-controls" id="centerSearchControls" style="display: none;"></div>
        <div class="center-search-row">
          <div class="search-wrap" style="max-width:100%;">
            <div class="search-input-row" style="width: 100%;">
              <input type="text" id="keyword" autocomplete="off" placeholder="输入品牌、人物或话题，启动推演...">
            </div>
            <div class="search-action-row" style="display: flex; justify-content: space-between; width: 100%; margin-top: 6px; align-items: center;">
              <div style="display:flex; gap:8px; align-items:center;">
                <button class="btn-upload" id="uploadBtn" onclick="document.getElementById('localFileInput').click()" title="上传本地数据文件（CSV/JSON/Excel）">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
                </button>
                <div class="depth-toggle" id="depthToggle" style="display:none; background:var(--s1); border-radius:16px; padding:2px; font-size:12px; font-weight:600; cursor:pointer; align-items:center;">
                  <div class="depth-btn active" data-depth="quick" onclick="setDepth('quick')" style="padding:4px 10px; border-radius:14px; transition:all 0.2s; display:flex; align-items:center; gap:4px; color:var(--tx);">⚡ 快速</div>
                  <div class="depth-btn" data-depth="deep" onclick="setDepth('deep')" style="padding:4px 10px; border-radius:14px; transition:all 0.2s; display:flex; align-items:center; gap:4px; color:var(--tx3);">🧠 深度</div>
                </div>
              </div>
              <button class="btn-analyze disabled" id="analyzeBtn" onclick="handleAnalyzeClick()" disabled title="开始分析">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
              </button>
            </div>
          </div>
        </div>
      </div>
  </div>
</div>

<!-- GLOBAL RESIZER 2 -->
<div class="global-resizer" id="rightResizer"><div class="global-resizer-handle"></div></div>

<!-- RIGHT PANEL: RESULTS -->
<div class="right-panel results-panel expanded" id="rightPanel" style="display:flex;">
  <div class="right-content" id="middleContent">
    <div class="empty-state" id="rightEmptyState" style="padding-top:20vh;">
      <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="var(--bhi)" stroke-width="1.5" style="margin-bottom:24px;"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
      <h3 style="color:var(--tx2);font-weight:500;">推演结果将在此显示</h3>
      <p style="color:var(--tx3);font-size:13px;margin-top:12px;">在左侧输入关键词开始分析</p>
    </div>

    <!-- The original result view -->
    <div class="result-view" id="resultView" style="display:none; padding-bottom:120px;">
      <div class="tab-bar">
        <button class="tab-btn active" onclick="switchTab('overview')"><span class="tab-dot d1"></span>图形概览</button>
        <button class="tab-btn" onclick="switchTab('charts')"><span class="tab-dot d2"></span>数据图表</button>
        <button class="tab-btn" onclick="switchTab('ai')"><span class="tab-dot d4"></span>最终报告</button>
      </div>

      <!-- Tab: Overview -->
      <div class="result-view active" id="tab-overview">
        <div class="card">
          <div class="card-header"><div class="card-title" id="summaryTitle"><span class="dot" style="background:var(--ac)"></span>舆情摘要</div><div class="card-pill">已完成</div></div>
          <div class="summary-text" id="summaryText"></div>
          <div class="tag-row" id="tagRow"></div>
        </div>
        <div class="card">
          <div class="metric-2x2" id="metricsGrid">
            <div class="metric-cell pos"><div class="m-label">正面情感</div><div class="m-value" id="mPositive">--</div><div class="m-sub" id="mPositiveSub"></div><div class="m-bar"><div class="m-bar-fill" style="width:0%"></div></div><div class="m-decor"></div></div>
            <div class="metric-cell neg"><div class="m-label">负面情感</div><div class="m-value" id="mNegative">--</div><div class="m-sub" id="mNegativeSub"></div><div class="m-bar"><div class="m-bar-fill" style="width:0%"></div></div><div class="m-decor"></div></div>
            <div class="metric-cell vol"><div class="m-label">采集量</div><div class="m-value" id="mVolume">--</div><div class="m-sub" id="mVolumeSub"></div><div class="m-bar"><div class="m-bar-fill" style="width:0%"></div></div><div class="m-decor"></div></div>
            <div class="metric-cell sco"><div class="m-label">综合情感分</div><div class="m-value" id="mScore">--</div><div class="m-sub" id="mScoreSub"></div><div class="m-bar"><div class="m-bar-fill" style="width:0%"></div></div><div class="m-decor"></div></div>
          </div>
        </div>
        <div class="card">
          <div class="card-title" style="margin-bottom:10px;"><span class="dot" style="background:var(--ac)"></span>近期情感走势</div>
          <div class="chart-box" style="height:200px;"><canvas id="lineChart"></canvas></div>
        </div>
      </div>

      <!-- Tab: Charts -->
      <div class="result-view" id="tab-charts">
        <div class="card">
          <div class="card-title" style="margin-bottom:10px;"><span class="dot" style="background:var(--gr)"></span>情感分布</div>
          <div class="chart-box" style="height:240px; display:flex; justify-content:center;"><canvas id="doughnutChart"></canvas></div>
        </div>
        <div class="card">
          <div class="card-title" style="margin-bottom:10px;"><span class="dot" style="background:var(--pu)"></span>各平台采集量</div>
          <div style="height:160px;"><canvas id="barChart"></canvas></div>
        </div>
        <div class="card">
          <div class="card-header">
            <div class="card-title"><span class="dot" style="background:var(--ac)"></span>各平台情感分布</div>
            <span style="font-size:10px;color:var(--tx3);">正面 / 中性 / 负面</span>
          </div>
          <div style="height:220px;"><canvas id="platformSentimentChart"></canvas></div>
          <div style="display:flex;gap:16px;justify-content:center;margin-top:8px;font-size:10px;color:var(--tx3);">
            <span>🟢 正面</span><span>🔵 中性</span><span>🔴 负面</span>
          </div>
        </div>
      </div>

      <!-- Tab: Final Report (formerly AI Insights) -->
      <div class="result-view" id="tab-ai">
        <div class="card" style="margin-bottom: 24px;">
          <div class="card-header"><div class="card-title"><span class="dot" style="background:var(--or)"></span>报告结论</div></div>
          <div class="summary-text" id="frConclusion" style="font-weight:600;color:var(--tx);margin-bottom:10px;"></div>
        </div>
        <div class="final-report-grid" id="finalReportGrid">
          <!-- Will be injected by JS -->
        </div>
      </div>
    </div>
  </div>
</div>
</main>"""

html = html.replace(main_content, new_main_content)

# Update appendLog JS function
append_log_start = html.find('function appendLog(line) {')
append_log_end = html.find('}', append_log_start) + 1

new_append_log = """function appendLog(line) {
  logLineCount++;
  var countEl = document.getElementById('logCount');
  if (countEl) countEl.textContent = logLineCount + ' 条记录';
  
  var c = document.getElementById('logContainer');
  if (!c) return;
  
  var ce = document.getElementById('chatEmpty');
  if(ce) ce.style.display = 'none';

  var d = document.createElement('div');
  d.className = 'chat-msg';
  
  var bubble = document.createElement('div');
  bubble.className = 'chat-bubble';
  
  var nameDiv = document.createElement('div');
  nameDiv.className = 'chat-name';
  
  var contentDiv = document.createElement('div');
  contentDiv.className = 'chat-content';
  
  var isLeft = true;
  var agentName = 'Agent';
  
  if (line.indexOf('[CollectAgent]') > -1) {
    agentName = 'CollectAgent (蓝方)';
    bubble.style.borderLeft = '3px solid #3b82f6';
  }
  else if (line.indexOf('[SentimentAgent]') > -1) {
    agentName = 'SentimentAgent (红方)';
    bubble.style.borderRight = '3px solid #ef4444';
    isLeft = false;
  }
  else if (line.indexOf('[TrendAgent]') > -1) {
    agentName = 'TrendAgent (蓝方)';
    bubble.style.borderLeft = '3px solid #10b981';
  }
  else if (line.indexOf('[ReportAgent]') > -1) {
    agentName = 'ReportAgent (红方)';
    bubble.style.borderRight = '3px solid #8b5cf6';
    isLeft = false;
  }
  else if (line.indexOf('[HOST]') > -1) {
    agentName = 'HOST (裁判)';
    bubble.style.background = 'var(--s2)';
    bubble.style.border = '1px solid var(--or)';
    contentDiv.style.fontWeight = 'bold';
    contentDiv.style.color = 'var(--or)';
    d.classList.add('chat-center');
    isLeft = null;
  }
  else if (line.indexOf('[SYSTEM]') > -1) {
    agentName = 'SYSTEM';
    bubble.style.background = 'transparent';
    bubble.style.border = '1px dashed var(--tx3)';
    contentDiv.style.color = 'var(--tx3)';
    d.classList.add('chat-center');
    isLeft = null;
  }
  
  if (isLeft === true) {
    d.classList.add('chat-left');
  } else if (isLeft === false) {
    d.classList.add('chat-right');
  }
  
  nameDiv.textContent = agentName;
  
  var match = line.match(/^\\[.*?\\]\\s*\\[.*?\\]\\s*(.*)/);
  if (match) {
     contentDiv.textContent = match[1];
  } else {
     contentDiv.textContent = line;
  }

  bubble.appendChild(nameDiv);
  bubble.appendChild(contentDiv);
  d.appendChild(bubble);
  c.appendChild(d);
  
  c.scrollTop = c.scrollHeight;
}"""

html = html.replace(html[append_log_start:append_log_end], new_append_log)

# Also fix the JS where it hides/shows centerSearchArea
# Original code has logic to toggle emptyState and runningState. We need to disable that.
# Find "document.getElementById('emptyState').style.display = 'none';"
html = html.replace("document.getElementById('emptyState').style.display = 'none';", "document.getElementById('rightEmptyState').style.display = 'none';")
html = html.replace("document.getElementById('centerSearchArea').style.display = 'none';", "")
html = html.replace("document.getElementById('runningState').style.display = 'block';", "")
html = html.replace("document.getElementById('runningState').style.display = 'none';", "")

# Now we need to define some right-panel specific CSS for the 3 columns
css_addition_3col = """
.middle-panel { width: 40%; flex: none; border-right: 1px solid var(--b); min-width: 300px; }
.right-panel { flex: 1; min-width: 300px; }
"""
html = html.replace('/* ── Main Layout ── */', css_addition_3col + '\n/* ── Main Layout ── */')

with open('MarketPulse/templates/index.html', 'w', encoding='utf-8') as f:
    f.write(html)

print("Rewrite successful")
