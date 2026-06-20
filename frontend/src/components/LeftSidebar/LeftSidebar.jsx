import React from 'react';
import { Search, Plus, MessageSquare, Clock, Star, LayoutTemplate, ChevronLeft, ChevronRight, Hash, Filter } from 'lucide-react';
import clsx from 'clsx';

export default function LeftSidebar({ collapsed, onToggle }) {
  return (
    <div className={clsx(
      "h-full bg-sidebar border-r border-border flex flex-col transition-all duration-180 ease-in-out shrink-0",
      collapsed ? "w-[72px]" : "w-[280px]"
    )}>
      {/* Brand & Search */}
      <div className="h-14 flex items-center justify-between px-4 shrink-0 border-b border-border/50">
        {!collapsed && <span className="font-bold text-lg tracking-wider text-text-main">GGB</span>}
        <button className="p-2 rounded-md hover:bg-white/5 text-text-secondary hover:text-text-main transition-colors mx-auto">
          <Search size={18} />
        </button>
      </div>

      {/* New Analysis Button */}
      <div className="p-4 shrink-0">
        <button className={clsx(
          "w-full flex items-center justify-center gap-2 bg-accent hover:bg-accent/90 text-white rounded-md transition-colors",
          collapsed ? "p-3" : "px-4 py-3"
        )}>
          <Plus size={18} />
          {!collapsed && <span className="font-medium">新建分析</span>}
        </button>
        {!collapsed && (
          <p className="text-[11px] text-text-secondary mt-2 text-center">输入事件、人物、品牌或话题</p>
        )}
      </div>

      <div className="flex-1 overflow-y-auto overflow-x-hidden p-3 space-y-6">
        
        {/* Sessions */}
        <section>
          {!collapsed && <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-3 px-2">今天</h3>}
          <div className="space-y-1">
            <SessionItem 
              collapsed={collapsed}
              title="小红书平台对某品牌争议舆情分析" 
              platform="小红书" 
              status="running" 
              time="12:31" 
              active
            />
            <SessionItem 
              collapsed={collapsed}
              title="华为Mate新品发布全网情绪监测" 
              platform="微博" 
              status="completed" 
              time="09:15" 
            />
          </div>
        </section>

        {/* Filters */}
        <section>
          {!collapsed && (
            <div className="flex items-center gap-2 text-xs font-semibold text-text-secondary uppercase tracking-wider mb-3 px-2">
              <Filter size={14} /> 筛选器
            </div>
          )}
          {!collapsed ? (
            <div className="px-2 flex flex-wrap gap-2">
              <span className="px-2 py-1 text-[11px] bg-white/5 border border-border rounded-full cursor-pointer hover:bg-white/10">多平台对比</span>
              <span className="px-2 py-1 text-[11px] bg-white/5 border border-border rounded-full cursor-pointer hover:bg-white/10">仅爆款帖</span>
            </div>
          ) : (
            <div className="flex justify-center">
              <button className="p-2 rounded-md hover:bg-white/5 text-text-secondary"><Filter size={18} /></button>
            </div>
          )}
        </section>

        {/* Prompt Templates */}
        <section>
          {!collapsed && (
            <div className="flex items-center gap-2 text-xs font-semibold text-text-secondary uppercase tracking-wider mb-3 px-2">
              <LayoutTemplate size={14} /> Prompt 模板
            </div>
          )}
          {!collapsed ? (
            <div className="space-y-1">
              {['舆情总览', '传播路径分析', '争议点提取', '风险预警'].map(tpl => (
                <div key={tpl} className="px-3 py-2 rounded-md text-sm text-text-secondary hover:text-text-main hover:bg-white/5 cursor-pointer flex items-center gap-2">
                  <Hash size={14} /> {tpl}
                </div>
              ))}
            </div>
          ) : (
             <div className="flex justify-center">
              <button className="p-2 rounded-md hover:bg-white/5 text-text-secondary"><LayoutTemplate size={18} /></button>
            </div>
          )}
        </section>

      </div>

      {/* Collapse Toggle */}
      <div className="p-3 border-t border-border/50 shrink-0 flex justify-end">
        <button 
          onClick={onToggle}
          className="p-2 rounded-md hover:bg-white/5 text-text-secondary hover:text-text-main transition-colors"
        >
          {collapsed ? <ChevronRight size={18} /> : <ChevronLeft size={18} />}
        </button>
      </div>
    </div>
  );
}

function SessionItem({ collapsed, title, platform, status, time, active }) {
  const statusColors = {
    running: 'bg-accent',
    completed: 'bg-success',
    waiting: 'bg-warning'
  };

  if (collapsed) {
    return (
      <div className={clsx(
        "w-10 h-10 mx-auto rounded-xl flex items-center justify-center relative cursor-pointer group",
        active ? "bg-white/10" : "hover:bg-white/5"
      )}>
        <MessageSquare size={16} className={active ? "text-accent" : "text-text-secondary group-hover:text-text-main"} />
        <div className={clsx("absolute top-0 right-0 w-2.5 h-2.5 border-2 border-sidebar rounded-full", statusColors[status])} />
      </div>
    );
  }

  return (
    <div className={clsx(
      "relative p-3 rounded-card cursor-pointer transition-colors group",
      active ? "bg-card border border-border shadow-sm" : "hover:bg-white/5 border border-transparent"
    )}>
      {active && <div className="absolute left-0 top-3 bottom-3 w-1 bg-accent rounded-r-md" />}
      <div className="flex justify-between items-start gap-2 mb-1">
        <div className="font-medium text-sm text-text-main truncate">{title}</div>
        <div className={clsx("w-2 h-2 rounded-full shrink-0 mt-1.5", statusColors[status])} />
      </div>
      <div className="flex justify-between items-center text-[11px] text-text-secondary">
        <span className="px-1.5 py-0.5 bg-white/5 rounded-full border border-white/5">{platform}</span>
        <span className="flex items-center gap-1"><Clock size={10} /> {time}</span>
      </div>
    </div>
  );
}
