import { useCallback, useEffect, useState } from 'react';
import { fetchModels, saveModel, deleteModel, setActiveModel } from '../services/api';

/**
 * 用户自配模型的共享状态。
 *
 * 两处要用同一份数据：对话框里的模型选择器（切换"这次用哪个"）和设置面板
 * （增删改）。两边各自 fetch 会出现"设置里刚加的模型，选择器里没有"——
 * 所以这里用自定义事件做跨组件同步，任何一处改动后广播一次，两边一起重拉。
 */
export function useModels() {
  const [models, setModels] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const reload = useCallback(async () => {
    try {
      const data = await fetchModels();
      setModels(Array.isArray(data.models) ? data.models : []);
      setActiveId(data.active_id || null);
      setError('');
    } catch (err) {
      setError(err.message || '模型列表加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  useEffect(() => {
    const sync = () => reload();
    window.addEventListener('modelschange', sync);
    return () => window.removeEventListener('modelschange', sync);
  }, [reload]);

  /** 当前选中的条目；没选任何自配模型时为 null（走 config.yaml 默认配置）。 */
  const active = models.find(m => m.id === activeId) || null;

  const activate = useCallback(async (id) => {
    await setActiveModel(id || null);
    window.dispatchEvent(new Event('modelschange'));
  }, []);

  const save = useCallback(async (payload) => {
    const saved = await saveModel(payload);
    window.dispatchEvent(new Event('modelschange'));
    return saved;
  }, []);

  const remove = useCallback(async (id) => {
    await deleteModel(id);
    window.dispatchEvent(new Event('modelschange'));
  }, []);

  return {
    models, activeId, active, loading, error,
    reload, activate, save, remove,
  };
}

/** 设置面板与选择器共用的"模型名"展示：没选自配模型时说明走的是默认配置。 */
export function modelLabel(active) {
  if (!active) return '默认配置';
  return active.name || active.model || '未命名模型';
}
