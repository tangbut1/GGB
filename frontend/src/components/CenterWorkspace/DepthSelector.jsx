import React, { useEffect, useState } from 'react';
import { Zap, ListChecks, Microscope } from 'lucide-react';
import clsx from 'clsx';

/**
 * 分析深度选择。
 *
 * 用户理解的不是"跑多重的模型"，而是"我会拿到什么"。所以这三档描述的是
 * 结果的展开范围，不是算力档位——后端全量流水线（采集 → 红蓝辩论 → 终裁）
 * 每次都完整跑，深度只决定默认展开到哪一层、以及右侧从哪个 Tab 起步。
 *
 * 这一点必须说清楚：写成"快速模式跑得快"是假的，流水线的耗时主要在采集和
 * LLM 往返，与深度无关。诚实的做法是把它叫"查看深度"，并说明全部数据都会
 * 备好，随时可以展开。
 */
const DEPTHS = [
  {
    id: 'quick',
    label: '快速研判',
    Icon: Zap,
    summary: '结论 + 四项核心指标 + 核心证据',
    detail: '只看研判卡：态势、风险等级、三条可验证依据。右侧默认停在核心指标。',
    tab: 'trend',
    expandProcess: false,
    expandQuality: false,
  },
  {
    id: 'standard',
    label: '标准分析',
    Icon: ListChecks,
    summary: '+ 事件脉络 + 趋势拆解 + 风险条件',
    detail: '加上事件如何发展到今天、按天序列与外推研判。推荐默认档。',
    tab: 'trend',
    expandProcess: false,
    expandQuality: false,
  },
  {
    id: 'audit',
    label: '深度审计',
    Icon: Microscope,
    summary: '+ 完整证据 + 分析过程 + 原始来源',
    detail: '展开红蓝双方全部发言、逐条证据与数据口径，用于复核与追责。',
    tab: 'quality',
    expandProcess: true,
    expandQuality: true,
  },
];

const STORAGE_KEY = 'ggb-analysis-depth';

/** 按 id 取档位元信息；未知 id 退回标准档，避免调用方各写一份兜底。 */
export function resolveDepth(id) {
  return DEPTHS.find(d => d.id === id) || DEPTHS[1];
}

function loadStored() {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    return DEPTHS.some(d => d.id === v) ? v : 'standard';
  } catch {
    return 'standard';
  }
}

export function useAnalysisDepth() {
  const [depth, setDepth] = useState(loadStored);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, depth);
    } catch {
      // 隐私模式下 localStorage 会抛异常，不影响功能，忽略即可
    }
  }, [depth]);

  const meta = DEPTHS.find(d => d.id === depth) || DEPTHS[1];
  return { depth, setDepth, meta };
}

export default function DepthSelector({ depth, onChange }) {
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-[10px] text-text-secondary shrink-0 hidden sm:inline">查看深度</span>
      <div className="flex rounded-lg border border-border bg-soft p-0.5">
        {DEPTHS.map(d => (
          <button
            key={d.id}
            onClick={() => onChange(d.id)}
            title={`${d.summary}\n${d.detail}`}
            aria-pressed={depth === d.id}
            className={clsx(
              "flex items-center gap-1 px-2 py-1 rounded-md text-[11px] transition-colors whitespace-nowrap",
              depth === d.id
                ? "bg-card text-text-main font-medium shadow-sm border border-border/60"
                : "text-text-secondary hover:text-text-main border border-transparent"
            )}
          >
            <d.Icon size={11} />
            {d.label}
          </button>
        ))}
      </div>
    </div>
  );
}
