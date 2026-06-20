import React, { useState } from 'react';
import { Share, Download, Play, MessageSquare, Bot, AlertTriangle, TrendingUp, Send, CheckCircle2, ChevronRight, Plus } from 'lucide-react';
import clsx from 'clsx';

export default function CenterWorkspace({ 
  onSelectAgent, 
  onStartAnalysis, 
  onSendFollowup, 
  messages, 
  status, 
  systemState, 
  currentQuery 
}) {
  const [mode, setMode] = useState('multi-agent');
  const [inputValue, setInputValue] = useState('');

  const handleSend = () => {
    if (!inputValue.trim()) return;
    
    if (status === 'idle') {
      onStartAnalysis(inputValue.trim());
    } else {
      onSendFollowup(inputValue.trim());
    }
    setInputValue('');
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden relative">
      <div className="h-14 border-b border-border/50 flex items-center justify-between px-6 shrink-0 bg-app/80 backdrop-blur-sm z-10">
        <div className="flex items-center gap-4">
          <h1 className="font-semibold text-text-main truncate max-w-sm">
            {currentQuery || '新的分析会话'}
          </h1>
          <span className="text-[11px] text-text-secondary bg-white/5 px-2 py-1 rounded-full border border-border">微博 + 小红书 + 抖音</span>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex bg-sidebar rounded-md border border-border p-1">
            {['快速思考', '深度思考', '多 Agent 辩论'].map(m => (
              <button 
                key={m}
                onClick={() => setMode(m === '多 Agent 辩论' ? 'multi-agent' : 'fast')}
                className={clsx(
                  "px-3 py-1 text-xs rounded-sm transition-colors",
                  (mode === 'multi-agent' && m === '多 Agent 辩论') || (mode !== 'multi-agent' && m !== '多 Agent 辩论') && m === '快速思考'
                    ? "bg-card text-text-main shadow-sm" 
                    : "text-text-secondary hover:text-text-main"
                )}
              >
                {m}
              </button>
            ))}
          </div>
          <div className="w-px h-4 bg-border mx-2" />
          <button className="p-1.5 text-text-secondary hover:text-text-main hover:bg-white/5 rounded-md"><Share size={16} /></button>
          <button className="p-1.5 text-text-secondary hover:text-text-main hover:bg-white/5 rounded-md"><Download size={16} /></button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-6 space-y-6 pb-32 custom-scrollbar">
        
        {currentQuery && (
          <div className="flex justify-end">
            <div className="bg-card border border-border rounded-2xl rounded-tr-sm p-4 max-w-2xl shadow-sm">
              <p className="text-sm">{currentQuery}</p>
              <div className="flex gap-2 mt-3">
                <span className="text-[10px] text-text-secondary bg-sidebar px-2 py-0.5 rounded-full">近 48 小时</span>
                <span className="text-[10px] text-text-secondary bg-sidebar px-2 py-0.5 rounded-full">多 Agent 辩论</span>
              </div>
            </div>
          </div>
        )}

        {systemState && (
          <div className="flex items-center justify-center">
            <div className="flex items-center gap-2 text-xs text-text-secondary bg-sidebar/50 px-4 py-1.5 rounded-full border border-border/50">
              {status === 'completed' ? <CheckCircle2 size={14} className="text-success" /> : <div className="w-3 h-3 border-2 border-accent border-t-transparent rounded-full animate-spin" />}
              <span>{systemState}</span>
            </div>
          </div>
        )}

        <div className="space-y-4 max-w-3xl">
          {messages.map((msg, index) => {
            if (msg.type === 'HOST' || msg.author === 'JudgeAgent') {
              return (
                <div key={index} className="bg-panel border border-border shadow-md rounded-2xl p-6 relative overflow-hidden mt-8">
                  <div className="absolute top-0 left-0 w-1 h-full bg-accent" />
                  <div className="flex items-center gap-2 mb-4">
                    <Bot className="text-accent" size={20} />
                    <h3 className="font-semibold text-base">法官总结 (Judge Agent)</h3>
                  </div>
                  <div className="space-y-4 text-sm text-text-main leading-relaxed whitespace-pre-wrap">
                    {msg.content}
                  </div>
                </div>
              );
            }

            // Map author to Agent style
            const styleMap = {
              'TrendAgent': { name: '趋势分析 Agent', icon: <TrendingUp size={16} />, color: 'text-agent-trend', bg: 'bg-agent-trend/10', border: 'border-agent-trend/20' },
              'SentimentAgent': { name: '情感分析 Agent', icon: <MessageSquare size={16} />, color: 'text-agent-sentiment', bg: 'bg-agent-sentiment/10', border: 'border-agent-sentiment/20' },
              'CollectAgent': { name: '采集 Agent', icon: <Share size={16} />, color: 'text-agent-spread', bg: 'bg-agent-spread/10', border: 'border-agent-spread/20' },
              'default': { name: msg.author || '分析 Agent', icon: <AlertTriangle size={16} />, color: 'text-agent-skeptic', bg: 'bg-agent-skeptic/10', border: 'border-agent-skeptic/20' }
            };

            const style = styleMap[msg.author] || styleMap['default'];

            return (
              <AgentCard 
                key={index}
                type={msg.author} 
                name={style.name} 
                icon={style.icon} 
                color={style.color}
                bg={style.bg}
                border={style.border}
                conclusion={msg.content}
                evidenceCount={Math.floor(Math.random() * 20)}
                onClick={() => onSelectAgent('evidence')}
              />
            );
          })}
        </div>

      </div>

      <div className="absolute bottom-0 left-0 w-full p-6 bg-gradient-to-t from-app via-app to-transparent pt-12 pointer-events-none">
        <div className="max-w-4xl mx-auto pointer-events-auto">
          <div className="flex gap-2 mb-2 px-2">
            {['@引用上一轮结论', '@针对反方质疑', '切换至深度模式'].map(tag => (
              <span key={tag} onClick={() => setInputValue(prev => prev + tag + ' ')} className="text-[11px] text-text-secondary hover:text-text-main cursor-pointer bg-black/20 px-2 py-1 rounded-md border border-white/5">{tag}</span>
            ))}
          </div>
          
          <div className="bg-sidebar border border-border rounded-input shadow-lg flex flex-col p-2 focus-within:border-border/80 focus-within:ring-1 focus-within:ring-border/50 transition-all relative">
            <textarea 
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={handleKeyDown}
              className="w-full bg-transparent border-none resize-none text-sm p-2 outline-none text-text-main placeholder-text-secondary/50 min-h-[60px]"
              placeholder={status === 'analyzing' ? '正在分析中，请稍候...' : "输入你的分析目标或追问..."}
              disabled={status === 'analyzing'}
            />
            <div className="flex justify-between items-center px-2 pb-1">
              <div className="flex items-center gap-2">
                <button className="p-1.5 rounded-md hover:bg-white/5 text-text-secondary"><Plus size={16} /></button>
                <div className="h-4 w-px bg-border mx-1" />
                <span className="text-xs text-text-secondary bg-white/5 px-2 py-0.5 rounded-md">基于当前上下文</span>
              </div>
              <button 
                onClick={handleSend}
                disabled={status === 'analyzing' || !inputValue.trim()}
                className="bg-accent hover:bg-accent/90 disabled:bg-accent/50 disabled:cursor-not-allowed text-white p-2 rounded-xl transition-colors shadow-sm"
              >
                <Send size={16} className="ml-0.5" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function AgentCard({ type, name, icon, color, bg, border, conclusion, evidenceCount, onClick }) {
  return (
    <div className={clsx("p-4 rounded-card border transition-all hover:shadow-md", bg, border)}>
      <div className="flex justify-between items-start mb-2">
        <div className="flex items-center gap-2">
          <div className={clsx("p-1.5 rounded-md bg-white/10", color)}>
            {icon}
          </div>
          <span className="font-medium text-sm text-text-main">{name}</span>
        </div>
        <span className="text-[10px] text-text-secondary bg-black/20 px-2 py-0.5 rounded-full border border-white/5">完成</span>
      </div>
      <p className="text-sm text-text-main/90 leading-relaxed mb-3 whitespace-pre-wrap">
        {conclusion}
      </p>
      <div className="flex items-center gap-3">
        <button className="text-xs text-text-secondary hover:text-text-main flex items-center gap-1 transition-colors">
          查看引用 ({evidenceCount}) <ChevronRight size={12} />
        </button>
        <button 
          onClick={onClick}
          className="text-xs text-accent hover:text-accent/80 transition-colors"
        >
          发送到右栏查看
        </button>
      </div>
    </div>
  );
}
