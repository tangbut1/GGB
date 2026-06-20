import React from 'react';
import { TrendingUp, PieChart, FileText, FileSearch, ExternalLink } from 'lucide-react';
import clsx from 'clsx';

export default function RightInsightPanel({ activeTab, onTabChange, analysisData }) {
  const tabs = [
    { id: 'trend', label: '趋势', icon: <TrendingUp size={14} /> },
    { id: 'sentiment', label: '情感', icon: <PieChart size={14} /> },
    { id: 'keywords', label: '热词', icon: <FileText size={14} /> },
    { id: 'evidence', label: '证据', icon: <FileSearch size={14} /> },
  ];

  return (
    <div className="h-full flex flex-col">
      <div className="h-14 border-b border-border/50 flex items-center px-4 shrink-0 gap-1 bg-app/50 backdrop-blur-sm">
        {tabs.map(tab => (
          <button
            key={tab.id}
            onClick={() => onTabChange(tab.id)}
            className={clsx(
              "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm transition-colors",
              activeTab === tab.id 
                ? "bg-white/10 text-text-main font-medium shadow-sm" 
                : "text-text-secondary hover:text-text-main hover:bg-white/5"
            )}
          >
            {tab.icon}
            {tab.label}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto p-4 custom-scrollbar">
        {activeTab === 'trend' && <TrendContent data={analysisData} />}
        {activeTab === 'sentiment' && <SentimentContent data={analysisData} />}
        {activeTab === 'keywords' && <KeywordContent data={analysisData} />}
        {activeTab === 'evidence' && <EvidenceContent data={analysisData} />}
      </div>
    </div>
  );
}

function TrendContent({ data }) {
  const trendDir = data?.trend_direction || 'neutral';
  
  return (
    <div className="space-y-4">
      <h3 className="text-sm font-semibold text-text-main mb-2">热度折线图与平台分布</h3>
      <div className="bg-card border border-border rounded-xl p-4 h-64 flex flex-col items-center justify-center text-text-secondary relative overflow-hidden">
        <div className="absolute inset-0 opacity-10 bg-[radial-gradient(ellipse_at_center,_var(--tw-gradient-stops))] from-agent-trend to-transparent"></div>
        <TrendingUp size={32} className="mb-2 text-agent-trend opacity-50" />
        <span className="text-xs">{data ? '已加载数据，图表渲染中...' : '[接入 Chart.js 线形图]'}</span>
        <div className="mt-4 text-[10px] text-center w-full max-w-[200px]">
          {data ? `总体趋势: ${trendDir} (可信度: ${data.confidence || 0}%)` : '暂无数据，请先开始分析'}
        </div>
      </div>
    </div>
  );
}

function SentimentContent({ data }) {
  const pos = data?.positive_pct || 0;
  const neg = data?.negative_pct || 0;
  const neu = data?.neutral_pct || 0;

  return (
    <div className="space-y-4">
      <h3 className="text-sm font-semibold text-text-main mb-2">全网情绪分布</h3>
      <div className="bg-card border border-border rounded-xl p-4 h-64 flex flex-col items-center justify-center text-text-secondary relative overflow-hidden">
        <div className="absolute inset-0 opacity-10 bg-[radial-gradient(ellipse_at_center,_var(--tw-gradient-stops))] from-agent-sentiment to-transparent"></div>
        <PieChart size={32} className="mb-2 text-agent-sentiment opacity-50" />
        <div className="mt-4 w-full px-8 space-y-2">
          {data ? (
            <div className="flex justify-between items-center text-[10px]">
              <span className="flex items-center gap-1"><div className="w-2 h-2 rounded-full bg-danger"></div>负面 {neg}%</span>
              <span className="flex items-center gap-1"><div className="w-2 h-2 rounded-full bg-success"></div>正面 {pos}%</span>
              <span className="flex items-center gap-1"><div className="w-2 h-2 rounded-full bg-text-secondary"></div>中性 {neu}%</span>
            </div>
          ) : (
            <div className="text-xs text-center">暂无数据</div>
          )}
        </div>
      </div>
    </div>
  );
}

function KeywordContent({ data }) {
  return (
    <div className="space-y-4">
      <h3 className="text-sm font-semibold text-text-main mb-2">高频词与争议点</h3>
      <div className="bg-card border border-border rounded-xl p-4 h-64 flex flex-col items-center justify-center text-text-secondary relative">
        <FileText size={32} className="mb-2 opacity-20" />
        <span className="text-xs">{data ? '生成词云中...' : '[暂无数据]'}</span>
      </div>
    </div>
  );
}

function EvidenceContent({ data }) {
  const posts = data?.analyzed_news || [];

  return (
    <div className="space-y-3">
      <div className="flex justify-between items-center mb-2">
        <h3 className="text-sm font-semibold text-text-main">原帖证据流 ({posts.length})</h3>
      </div>
      
      {posts.length === 0 && <div className="text-xs text-text-secondary text-center py-4">暂无证据记录</div>}

      {posts.map((post, i) => (
        <div key={i} className="bg-card border border-border rounded-xl p-3 hover:border-border/80 transition-colors cursor-pointer group">
          <div className="flex items-center gap-2 mb-2">
            <div className="w-5 h-5 rounded-full bg-accent/20 flex items-center justify-center text-[10px] text-accent">源</div>
            <span className="text-xs font-medium text-text-main truncate max-w-[120px]">{post.title || '无标题'}</span>
            <span className="text-[10px] text-text-secondary ml-auto">{post.time || '未知时间'}</span>
          </div>
          <p className="text-xs text-text-secondary leading-relaxed mb-2 line-clamp-3 group-hover:line-clamp-none">
            {post.content || post.snippet}
          </p>
          <div className="flex items-center justify-between mt-2 pt-2 border-t border-border/50">
            <div className="flex gap-3 text-[10px] text-text-secondary">
               <span>情感分: {post.sentiment_score?.toFixed(2) || 'N/A'}</span>
            </div>
            <button className="text-[10px] text-accent flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
               <ExternalLink size={10} /> 引用此条
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
