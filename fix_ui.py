import re

with open('MarketPulse/templates/index.html', 'r', encoding='utf-8') as f:
    html = f.read()

css_addition = """
/* ── Chat Panel & 3-Column Layout ── */
main.layout-3col .right-panel {
  width: 45% !important; flex: none !important;
}
main.layout-3col .chat-panel {
  display: flex !important;
}
.chat-panel {
  display: none; /* hidden by default */
  width: 35%; flex: auto; border-right: 1px solid var(--b);
  flex-direction: column; background: var(--s0); position: relative;
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
  flex-shrink: 0;
}
.chat-input-area .center-search-area {
  width: 100% !important; max-width: 100% !important; margin: 0 !important;
}

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
</style>
"""

# Insert CSS before </style>
html = html.replace('</style>', css_addition)

# Remove the original logContainer
original_log_container = '<div class="log-container" id="logContainer" style="border-radius:0 0 12px 12px; margin:0;"></div>'
html = html.replace(original_log_container, '')

# Add the chat-panel right before <div class="right-panel">
chat_panel_html = """
<!-- CHAT PANEL (hidden initially) -->
<div class="chat-panel" id="chatPanel">
  <div class="chat-header">
    <div style="font-weight:600;font-size:14px;color:var(--tx);display:flex;align-items:center;gap:8px;">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--ac)" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>
      红蓝对抗实时推演
    </div>
    <div style="font-size:12px;color:var(--tx3);font-family:var(--mono);" id="logCount">0 条记录</div>
  </div>
  <div class="chat-messages" id="logContainer">
  </div>
  <div class="chat-input-area" id="chatInputArea">
  </div>
</div>
<!-- RIGHT PANEL -->
<div class="right-panel">
"""
html = html.replace('<!-- RIGHT PANEL -->\n<div class="right-panel">', chat_panel_html)

# Modify startAnalysis() function to add 3-col logic
start_analysis_code = """
  document.getElementById('emptyState').style.display='none';
  document.getElementById('runningState').style.display='block';
  document.getElementById('resultView').style.display='none';
"""

start_analysis_new_code = """
  document.getElementById('emptyState').style.display='none';
  document.getElementById('runningState').style.display='block';
  document.getElementById('resultView').style.display='none';
  
  // Enter 3-col mode
  document.querySelector('main').classList.add('layout-3col');
  var searchArea = document.getElementById('centerSearchArea');
  var chatInputArea = document.getElementById('chatInputArea');
  if (searchArea.parentNode !== chatInputArea) {
    chatInputArea.appendChild(searchArea);
  }
"""
html = html.replace(start_analysis_code, start_analysis_new_code)


# Modify appendLog function
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

  if (isLeft !== null) {
      bubble.appendChild(nameDiv);
  }
  bubble.appendChild(contentDiv);
  d.appendChild(bubble);
  c.appendChild(d);
  
  c.scrollTop = c.scrollHeight;
}"""

html = html.replace(html[append_log_start:append_log_end], new_append_log)


with open('MarketPulse/templates/index.html', 'w', encoding='utf-8') as f:
    f.write(html)

print("Rewrite successful")
