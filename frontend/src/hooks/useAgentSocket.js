import { useEffect, useState, useCallback } from 'react';
import { io } from 'socket.io-client';

export function useAgentSocket(taskId) {
  const [socket, setSocket] = useState(null);
  const [messages, setMessages] = useState([]);
  const [status, setStatus] = useState('idle'); // idle, analyzing, completed, error
  const [systemState, setSystemState] = useState('');
  const [analysisData, setAnalysisData] = useState(null);

  useEffect(() => {
    if (!taskId) return;

    // Connect to Socket.IO backend
    const newSocket = io({
      path: '/socket.io',
      transports: ['websocket', 'polling']
    });

    setSocket(newSocket);
    setStatus('analyzing');
    setMessages([]);
    setAnalysisData(null);
    setSystemState('已开始分析...');

    newSocket.on('connect', () => {
      console.log('Socket connected, joining room:', taskId);
      newSocket.emit('join', { task_id: taskId });
    });

    // Handle agent lifecycle updates (CollectAgent, SentimentAgent, etc)
    newSocket.on('agent_update', (data) => {
      // data: { agent: "CollectAgent", status: "active"|"done"|"err", progress: 5 }
      const statusText = data.status === 'active' ? '运行中' : data.status === 'done' ? '已完成' : '异常';
      setSystemState(`${data.agent} ${statusText} (${data.progress}%)`);
    });

    // Handle debate/forum turns
    newSocket.on('debate_turn', (data) => {
      // data: { author: "TrendAgent", type: "AGENT", content: "..." }
      setMessages(prev => [...prev, {
        id: Date.now() + Math.random(),
        ...data
      }]);
    });

    // Handle host/judge messages
    newSocket.on('forum_message', (data) => {
       // data: { type: "HOST", content: "..." }
       if (data.type === 'HOST') {
         setMessages(prev => [...prev, {
           id: Date.now() + Math.random(),
           author: 'JudgeAgent',
           type: 'HOST',
           content: data.content
         }]);
       }
    });

    // Handle errors
    newSocket.on('error', (data) => {
      setStatus('error');
      setSystemState(`错误: ${data.message || '未知错误'}`);
    });

    // Handle completion
    newSocket.on('task_complete', (data) => {
      // data: { task_id, status: "completed", data: { ... } }
      console.log('Task Complete:', data);
      setStatus(data.status);
      setSystemState(data.status === 'completed' ? '分析完成' : '分析终止');
      if (data.data) {
        setAnalysisData(data.data);
      }
    });

    return () => {
      newSocket.disconnect();
    };
  }, [taskId]);

  return {
    socket,
    messages,
    status,
    systemState,
    analysisData
  };
}
