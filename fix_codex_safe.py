import re

with open('MarketPulse/templates/index.html', 'r', encoding='utf-8') as f:
    html = f.read()

# 1. Add CSS
css_addition = """
/* ── Codex Layout CSS ── */
.middle-panel {
  flex: 1; min-width: 0; display: flex; flex-direction: column; 
  background: var(--bg); position: relative;
  transition: all 0.4s cubic-bezier(0.2, 0.8, 0.2, 1);
}
.middle-panel.initial-mode {
  justify-content: center; align-items: center;
}
.middle-panel.initial-mode .chat-header,
.middle-panel.initial-mode .chat-messages {
  display: none;
}
.middle-panel.initial-mode .chat-input-area {
  width: 100%; border-top: none; background: transparent; padding: 0 24px 12vh 24px;
  display: flex; flex-direction: column; align-items: center;
}
.middle-panel.initial-mode .search-wrap {
  transform: scale(1.05); transition: transform 0.4s ease;
}

.initial-title {
  font-size: 38px; font-weight: 800; margin-bottom: 40px; letter-spacing: 2px;
  color: var(--tx); text-align: center; display: none;
}
.middle-panel.initial-mode .initial-title {
  display: block;
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
.chat-input-area {
  padding: 16px 20px; background: var(--bg); border-top: 1px solid var(--b);
  flex-shrink: 0; width: 100%; transition: all 0.4s ease; box-sizing: border-box;
}
.chat-input-area .center-search-area {
  width: 100% !important; max-width: 800px !important; margin: 0 auto !important;
}

.right-panel {
  width: 45%; max-width: 600px; min-width: 320px;
  display: flex; flex-direction: column; overflow: hidden;
  border-left: 1px solid var(--b); background: var(--s0);
  transition: width 0.4s cubic-bezier(0.2, 0.8, 0.2, 1), opacity 0.3s ease, min-width 0.4s;
  opacity: 1; position: relative;
}
.right-panel.drawer-collapsed {
  width: 0 !important; min-width: 0 !important; opacity: 0; border-left: none; padding: 0;
}
.right-resizer {
  transition: opacity 0.3s ease;
}
.right-resizer.drawer-collapsed {
  opacity: 0; pointer-events: none; width: 0;
}
.expand-right-floating {
  position: absolute; right: 16px; top: 16px; z-index: 10;
  background: var(--s1); border: 1px solid var(--b); border-radius: 8px;
  padding: 8px; cursor: pointer; display: none;
  box-shadow: 0 2px 8px rgba(0,0,0,0.05); color: var(--tx2);
}
.middle-panel:not(.initial-mode) .expand-right-floating.show {
  display: block;
}
.expand-right-floating:hover { color: var(--ac); border-color: var(--bhi); }

.chat-msg { display: flex; flex-direction: column; width: 100%; }
.chat-left { align-items: flex-start; }
.chat-right { align-items: flex-end; }
.chat-center { align-items: center; }
.chat-bubble {
  max-width: 85%; background: var(--s1); padding: 12px 16px; border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.04); border: 1px solid var(--b);
}
.chat-left .chat-bubble { border-bottom-left-radius: 4px; }
.chat-right .chat-bubble { border-bottom-right-radius: 4px; background: #fff8f8; }
[data-theme="dark"] .chat-right .chat-bubble { background: rgba(224,108,117,0.05); }
.chat-name { font-size: 11px; font-weight: 600; color: var(--tx2); margin-bottom: 6px; }
.chat-content { font-size: 13px; line-height: 1.6; color: var(--tx); white-space: pre-wrap; word-break: break-word; }
"""
html = html.replace('</style>', css_addition + '\n</style>', 1)

# Remove the original logContainer
original_log_container = '<div class="log-container" id="logContainer" style="border-radius:0 0 12px 12px; margin:0;"></div>'
html = html.replace(original_log_container, '')


# Extract centerSearchArea exactly
search_start = html.find('<div class="center-search-area" id="centerSearchArea">')
search_end = html.find('</div>\n    </div>', search_start) + 6
center_search_html = html[search_start:search_end]

# Delete original emptyState
empty_state_start = html.find('<div class="empty-state" id="emptyState">')
empty_state_end = search_end + len('    </div>\n')
html = html[:empty_state_start] + '<div class="empty-state" id="emptyState" style="display:none;"></div>\n' + html[empty_state_end:]

chat_panel_html = f"""
<!-- MIDDLE PANEL (Main Chat) -->
<div class="middle-panel initial-mode" id="middlePanel">
  <div class="chat-header">
    <div style="font-weight:600;font-size:14px;color:var(--tx);display:flex;align-items:center;gap:8px;">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--ac)" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>
      红蓝对抗实时推演
    </div>
    <div style="font-size:12px;color:var(--tx3);font-family:var(--mono);" id="logCount">0 条记录</div>
  </div>
  <div class="chat-messages" id="logContainer"></div>
  
  <button class="expand-right-floating show" id="expandRightBtn" onclick="toggleRightPanel()" title="展开推演结果">
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"></polyline></svg>
  </button>
  
  <div class="chat-input-area" id="chatInputArea">
    <h2 class="initial-title">开始你的第一次分析</h2>
    {center_search_html}
  </div>
</div>

<!-- GLOBAL RESIZER RIGHT -->
<div class="global-resizer right-resizer drawer-collapsed" id="rightResizer"><div class="global-resizer-handle"></div></div>

<!-- RIGHT PANEL (Results Drawer) -->
<div class="right-panel drawer-collapsed" id="rightPanel">
  <div class="panel-header" style="border-bottom:1px solid var(--b); background:var(--bg);">
    <div class="panel-title" style="flex:1;">推演结果</div>
    <button class="expand-btn show" style="position:static; margin-right:8px;" id="collapseRightBtn" onclick="toggleRightPanel()" title="收起面板">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"></polyline></svg>
    </button>
  </div>
"""

# Replace the original <div class="right-panel"> tag only
html = html.replace('<!-- RIGHT PANEL -->\n<div class="right-panel">', chat_panel_html, 1)

# JS modifications
start_analysis_code = """  document.getElementById('emptyState').style.display='none';
  document.getElementById('resultView').style.display='none';"""

start_analysis_new = """  document.getElementById('emptyState').style.display='none';
  document.getElementById('resultView').style.display='none';
  
  // Codex style transition
  document.getElementById('middlePanel').classList.remove('initial-mode');
  document.getElementById('rightPanel').classList.remove('drawer-collapsed');
  document.getElementById('rightResizer').classList.remove('drawer-collapsed');
  var expandRight = document.getElementById('expandRightBtn');
  if (expandRight) expandRight.classList.remove('show');
"""
html = html.replace(start_analysis_code, start_analysis_new, 1)

js_addition = """
var rightPanelCollapsed = false;
function toggleRightPanel() {
  var panel = document.getElementById('rightPanel');
  var resizer = document.getElementById('rightResizer');
  var expandBtn = document.getElementById('expandRightBtn');
  rightPanelCollapsed = !rightPanelCollapsed;
  if (rightPanelCollapsed) {
    if (panel) panel.classList.add('drawer-collapsed');
    if (resizer) resizer.classList.add('drawer-collapsed');
    if (expandBtn) expandBtn.classList.add('show');
  } else {
    if (panel) panel.classList.remove('drawer-collapsed');
    if (resizer) resizer.classList.remove('drawer-collapsed');
    if (expandBtn) expandBtn.classList.remove('show');
  }
}
"""
html = html.replace('function toggleLeftPanel() {', js_addition + '\nfunction toggleLeftPanel() {', 1)

append_log_start = html.find('function appendLog(line) {')
append_log_end = html.find('}', append_log_start) + 1

new_append_log = """function appendLog(line) {
  logLineCount++;
  var countEl = document.getElementById('logCount');
  if (countEl) countEl.textContent = logLineCount + ' 条记录';
  
  var c = document.getElementById('logContainer');
  if (!c) return;
  
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
  
  if (isLeft === true) d.classList.add('chat-left');
  else if (isLeft === false) d.classList.add('chat-right');
  
  nameDiv.textContent = agentName;
  var match = line.match(/^\\[.*?\\]\\s*\\[.*?\\]\\s*(.*)/);
  contentDiv.textContent = match ? match[1] : line;

  if (isLeft !== null) bubble.appendChild(nameDiv);
  bubble.appendChild(contentDiv);
  d.appendChild(bubble);
  c.appendChild(d);
  
  c.scrollTop = c.scrollHeight;
}"""
html = html.replace(html[append_log_start:append_log_end], new_append_log, 1)

with open('MarketPulse/templates/index.html', 'w', encoding='utf-8') as f:
    f.write(html)

print("Safe string replace completed")
