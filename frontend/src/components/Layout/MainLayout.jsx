import React from 'react';
import LeftSidebar from '../LeftSidebar/LeftSidebar';
import CenterWorkspace from '../CenterWorkspace/CenterWorkspace';
import RightInsightPanel from '../RightInsightPanel/RightInsightPanel';
import { useAgentSocket } from '../../hooks/useAgentSocket';
import { analyzeKeyword, sendFollowup } from '../../services/api';
import useStore from '../../store/analysisStore';

export default function MainLayout() {
  // Init socket hook (reads taskId from store)
  useAgentSocket();

  const setCurrentTaskId = useStore((s) => s.setCurrentTaskId);
  const setCurrentQuery = useStore((s) => s.setCurrentQuery);
  const currentTaskId = useStore((s) => s.currentTaskId);
  const rightPanelOpen = useStore((s) => s.rightPanelOpen);

  const handleStartAnalysis = async (keyword) => {
    try {
      setCurrentQuery(keyword);
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
      <LeftSidebar />

      <div className="flex-1 min-w-0 flex flex-col bg-app">
        <CenterWorkspace
          onStartAnalysis={handleStartAnalysis}
          onSendFollowup={handleSendFollowup}
        />
      </div>

      <div
        className={`
          flex-shrink-0 bg-panel border-l border-border flex flex-col
          transition-all duration-280 ease-apple
          ${rightPanelOpen ? 'w-[360px] opacity-100' : 'w-0 opacity-0 overflow-hidden border-l-0'}
        `}
      >
        {rightPanelOpen && <RightInsightPanel />}
      </div>
    </div>
  );
}
