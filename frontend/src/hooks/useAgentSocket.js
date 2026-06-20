import { useEffect, useRef } from 'react';
import { io } from 'socket.io-client';
import useStore from '../store/analysisStore';

export function useAgentSocket() {
  const taskId = useStore((s) => s.currentTaskId);
  const setMessages = useStore((s) => s.setMessages);
  const setStatus = useStore((s) => s.setStatus);
  const setSystemState = useStore((s) => s.setSystemState);
  const setAnalysisData = useStore((s) => s.setAnalysisData);
  const resetMessages = useStore((s) => s.resetMessages);

  const socketRef = useRef(null);

  useEffect(() => {
    if (!taskId) return;

    // Reset state for new task
    resetMessages();
    setStatus('analyzing');
    setSystemState('已开始分析...');

    // Connect to Socket.IO backend
    const newSocket = io({
      path: '/socket.io',
      transports: ['websocket', 'polling']
    });

    socketRef.current = newSocket;

    newSocket.on('connect', () => {
      console.log('Socket connected, joining room:', taskId);
      newSocket.emit('join', { task_id: taskId });
    });

    newSocket.on('agent_update', (data) => {
      const statusText = data.status === 'active' ? '运行中' : data.status === 'done' ? '已完成' : '异常';
      setSystemState(`${data.agent} ${statusText} (${data.progress}%)`);
    });

    newSocket.on('debate_turn', (data) => {
      useStore.getState().addMessage({
        id: Date.now() + Math.random(),
        ...data
      });
    });

    newSocket.on('forum_message', (data) => {
      if (data.type === 'HOST') {
        useStore.getState().addMessage({
          id: Date.now() + Math.random(),
          author: 'JudgeAgent',
          type: 'HOST',
          content: data.content
        });
      }
    });

    newSocket.on('error', (data) => {
      setStatus('error');
      setSystemState(`错误: ${data.message || '未知错误'}`);
      try {
        window.dispatchEvent(new CustomEvent('app:toast', {
          detail: { type: 'error', message: data.message || '未知错误' }
        }));
      } catch (_) { /* ignore */ }
    });

    newSocket.on('task_complete', (data) => {
      console.log('Task Complete:', data);
      setStatus(data.status);
      setSystemState(data.status === 'completed' ? '分析完成' : '分析终止');
      if (data.data) {
        setAnalysisData(data.data);
      }
    });

    return () => {
      newSocket.removeAllListeners();
      newSocket.disconnect();
      socketRef.current = null;
    };
  }, [taskId]);
}
