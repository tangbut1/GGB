import React, { useState } from 'react';
import LeftSidebar from '../LeftSidebar/LeftSidebar';
import CenterWorkspace from '../CenterWorkspace/CenterWorkspace';
import RightInsightPanel from '../RightInsightPanel/RightInsightPanel';
import { useAgentSocket } from '../../hooks/useAgentSocket';
import { analyzeKeyword, sendFollowup } from '../../services/api';

export default function MainLayout() {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [activeTab, setActiveTab] = useState('trend');
  
  // App state
  const [currentTaskId, setCurrentTaskId] = useState(null);
  const [currentQuery, setCurrentQuery] = useState('');
  
  // Socket hook
  const { messages, status, systemState, analysisData } = useAgentSocket(currentTaskId);

  const handleStartAnalysis = async (keyword) => {
    try {
      setCurrentQuery(keyword);
      setMessages([]);
      const res = await analyzeKeyword(keyword);
      setCurrentTaskId(res.task_id);
    } catch (err) {
      console.error(err);
      alert(err.message || '分析失败');
    }
  };

  const handleSendFollowup = async (message) => {
    if (!currentTaskId) return;
    try {
      await sendFollowup(currentTaskId, message);
    } catch (err) {
      console.error(err);
      alert(err.message || '追问失败');
    }
  };

  return (
    <div className="flex h-screen w-full bg-app overflow-hidden text-text-main">
      <LeftSidebar 
        collapsed={sidebarCollapsed} 
        onToggle={() => setSidebarCollapsed(!sidebarCollapsed)} 
      />

      <div className="flex-1 min-w-[720px] flex flex-col border-r border-border bg-app">
        <CenterWorkspace 
          onSelectAgent={(type) => setActiveTab(type)}
          onStartAnalysis={handleStartAnalysis}
          onSendFollowup={handleSendFollowup}
          messages={messages}
          status={status}
          systemState={systemState}
          currentQuery={currentQuery}
        />
      </div>

      <div className="w-[360px] flex-shrink-0 bg-panel border-l border-border hidden lg:flex flex-col">
        <RightInsightPanel 
          activeTab={activeTab} 
          onTabChange={setActiveTab} 
          analysisData={analysisData}
        />
      </div>
    </div>
  );
}
