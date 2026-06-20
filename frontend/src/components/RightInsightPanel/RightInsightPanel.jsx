import React, { useState, useEffect } from 'react';
import { TrendingUp, PieChart, FileText, FileSearch, ExternalLink } from 'lucide-react';
import clsx from 'clsx';
import useStore from '../../store/analysisStore';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  ArcElement,
  Title,
  Tooltip,
  Legend,
  Filler
} from 'chart.js';
import { Line, Doughnut } from 'react-chartjs-2';

// Register Chart.js components
ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  ArcElement,
  Title,
  Tooltip,
  Legend,
  Filler
);

// ── Dark theme chart defaults ──────────────────────────────────────
const darkThemeColors = {
  text: '#98A2B3',
  grid: '#2A303A',
  bg: '#1C2129',
  accent: '#3B82F6',
};

ChartJS.defaults.color = darkThemeColors.text;
ChartJS.defaults.borderColor = darkThemeColors.grid;
ChartJS.defaults.font.family = `'Inter', system-ui, -apple-system, sans-serif`;
ChartJS.defaults.font.size = 11;

export default function RightInsightPanel() {
  const activeTab = useStore((s) => s.activeTab);
  const setActiveTab = useStore((s) => s.setActiveTab);
  const analysisData = useStore((s) => s.analysisData);
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
        <div key={activeTab} className="animate-fadeIn">
          {activeTab === 'trend' && <TrendContent data={analysisData} />}
          {activeTab === 'sentiment' && <SentimentContent data={analysisData} />}
          {activeTab === 'keywords' && <KeywordContent data={analysisData} />}
          {activeTab === 'evidence' && <EvidenceContent data={analysisData} />}
        </div>
      </div>
    </div>
  );
}

// ── Skeleton helpers ───────────────────────────────────────────────
function SkeletonBox({ className = '' }) {
  return <div className={clsx('skeleton', className)} />;
}

// ── TrendContent (Line chart) ──────────────────────────────────────
function TrendContent({ data }) {
  const trendDir = data?.trend_direction || 'neutral';
  const trendData = data?.trend_data || [];

  if (!data || trendData.length === 0) {
    return (
      <div className="space-y-4">
        <h3 className="text-sm font-semibold text-text-main mb-2">热度折线图与平台分布</h3>
        <div className="bg-card border border-border rounded-xl p-4 space-y-3">
          <SkeletonBox className="h-4 w-3/4" />
          <SkeletonBox className="h-40 w-full" />
          <SkeletonBox className="h-3 w-1/2" />
        </div>
      </div>
    );
  }

  const labels = trendData.map(d => d.time || '');
  const values = trendData.map(d => d.value || 0);

  const chartData = {
    labels,
    datasets: [
      {
        label: '热度趋势',
        data: values,
        borderColor: '#3B82F6',
        backgroundColor: 'rgba(59, 130, 246, 0.08)',
        borderWidth: 2,
        pointRadius: 2,
        pointHoverRadius: 5,
        pointBackgroundColor: '#3B82F6',
        tension: 0.35,
        fill: true,
      },
    ],
  };

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: '#171A20',
        titleColor: '#E8ECF2',
        bodyColor: '#98A2B3',
        borderColor: '#2A303A',
        borderWidth: 1,
        cornerRadius: 8,
        padding: 10,
      },
    },
    scales: {
      x: {
        grid: { color: darkThemeColors.grid, drawBorder: false },
        ticks: { maxTicksLimit: 8, color: darkThemeColors.text },
      },
      y: {
        grid: { color: darkThemeColors.grid, drawBorder: false },
        ticks: { color: darkThemeColors.text, callback: (v) => v >= 1000 ? `${(v / 1000).toFixed(1)}k` : v },
      },
    },
  };

  return (
    <div className="space-y-4">
      <h3 className="text-sm font-semibold text-text-main mb-2">热度折线图与平台分布</h3>
      <div className="bg-card border border-border rounded-xl p-4">
        <div className="h-56">
          <Line data={chartData} options={options} />
        </div>
        <div className="mt-3 text-[10px] text-text-secondary text-center">
          总体趋势: <span className={clsx(
            trendDir === 'up' && 'text-success',
            trendDir === 'down' && 'text-danger',
            trendDir === 'neutral' && 'text-text-secondary'
          )}>{trendDir === 'up' ? '📈 上升' : trendDir === 'down' ? '📉 下降' : '➡️ 平稳'}</span>
          {data.confidence ? ` (可信度: ${data.confidence}%)` : ''}
        </div>
      </div>
    </div>
  );
}

// ── SentimentContent (Doughnut chart) ──────────────────────────────
function SentimentContent({ data }) {
  const pos = data?.positive_pct ?? 0;
  const neg = data?.negative_pct ?? 0;
  const neu = data?.neutral_pct ?? 0;
  const hasData = data && (pos > 0 || neg > 0 || neu > 0);

  if (!data) {
    return (
      <div className="space-y-4">
        <h3 className="text-sm font-semibold text-text-main mb-2">全网情绪分布</h3>
        <div className="bg-card border border-border rounded-xl p-4 space-y-3">
          <SkeletonBox className="h-4 w-2/3" />
          <div className="flex items-center justify-center py-4">
            <SkeletonBox className="h-40 w-40 rounded-full" />
          </div>
          <SkeletonBox className="h-3 w-full" />
        </div>
      </div>
    );
  }

  const chartData = {
    labels: ['正面', '负面', '中性'],
    datasets: [
      {
        data: [pos, neg, neu],
        backgroundColor: ['#22C55E', '#EF4444', '#98A2B3'],
        borderColor: ['#22C55E', '#EF4444', '#98A2B3'],
        borderWidth: 0,
        hoverBorderWidth: 2,
        hoverBorderColor: '#1C2129',
      },
    ],
  };

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    cutout: '65%',
    plugins: {
      legend: {
        position: 'bottom',
        labels: {
          color: darkThemeColors.text,
          padding: 16,
          usePointStyle: true,
          pointStyleWidth: 8,
          font: { size: 11 },
        },
      },
      tooltip: {
        backgroundColor: '#171A20',
        titleColor: '#E8ECF2',
        bodyColor: '#98A2B3',
        borderColor: '#2A303A',
        borderWidth: 1,
        cornerRadius: 8,
        padding: 10,
        callbacks: {
          label: (ctx) => `${ctx.label}: ${ctx.raw}%`,
        },
      },
    },
  };

  return (
    <div className="space-y-4">
      <h3 className="text-sm font-semibold text-text-main mb-2">全网情绪分布</h3>
      <div className="bg-card border border-border rounded-xl p-4">
        <div className="h-48 flex items-center justify-center">
          <Doughnut data={chartData} options={options} />
        </div>
        {!hasData && (
          <div className="text-xs text-text-secondary text-center mt-2">暂无情感数据</div>
        )}
      </div>
    </div>
  );
}

// ── KeywordContent (placeholder for future word cloud) ────────────
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

// ── EvidenceContent ─────────────────────────────────────────────────
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
