import React, { useEffect, useRef, useState } from 'react';
import { ChevronDown, Check, Cpu, Settings2 } from 'lucide-react';
import clsx from 'clsx';
import { modelLabel } from '../../hooks/useModels';

/**
 * 对话框里的模型选择器。
 *
 * 只做"切换当前选用哪个模型"，新增和编辑在设置面板里做——对话框是干活的
 * 地方，塞一个表单进来会把它撑成设置页。切换立即生效（后端下一次 LLM 调用
 * 会读到新配置），不需要重启。
 */
export default function ModelSelector({ models, activeId, onActivate, onManage }) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef(null);
  const active = models.find(m => m.id === activeId) || null;

  // 点外面收起。用 pointerdown 而不是 click：click 会在按钮自身的
  // mousedown→mouseup 之间触发，导致菜单刚开就被判为"点外面"。
  useEffect(() => {
    if (!open) return;
    const onDown = (e) => {
      if (!rootRef.current?.contains(e.target)) setOpen(false);
    };
    const onKey = (e) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('pointerdown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('pointerdown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const choose = (id) => {
    setOpen(false);
    if (id === (activeId || '')) return;
    onActivate?.(id || null);
  };

  return (
    <div ref={rootRef} className="relative shrink-0">
      <button
        type="button"
        onClick={() => setOpen(v => !v)}
        title={`当前模型：${modelLabel(active)}${active?.model ? `（${active.model}）` : ''}\n点击切换`}
        aria-haspopup="listbox"
        aria-expanded={open}
        className={clsx(
          "flex items-center gap-1.5 max-w-[13rem] px-2 py-1 rounded-lg border transition-colors",
          open
            ? "border-accent/40 bg-accent/10 text-text-main"
            : "border-border bg-soft text-text-secondary hover:text-text-main hover:border-border/80"
        )}
      >
        <Cpu size={12} className="shrink-0" />
        <span className="text-[11px] truncate">{modelLabel(active)}</span>
        <ChevronDown size={11} className={clsx("shrink-0 transition-transform", open && "rotate-180")} />
      </button>

      {open && (
        <div
          role="listbox"
          className="absolute bottom-full left-0 mb-2 w-64 bg-panel border border-border rounded-card shadow-panel py-1 z-30"
        >
          <div className="px-3 py-1.5 text-[10px] text-text-secondary uppercase tracking-wider">
            选择本次分析使用的模型
          </div>

          <button
            type="button"
            onClick={() => choose('')}
            className={clsx(
              "w-full flex items-start gap-2 px-3 py-2 text-left transition-colors",
              !activeId ? "bg-accent/10" : "hover:bg-hover"
            )}
          >
            <span className="w-3.5 pt-0.5 shrink-0">
              {!activeId && <Check size={12} className="text-accent" />}
            </span>
            <span className="min-w-0">
              <span className="block text-[12px] text-text-main">默认配置</span>
              <span className="block text-[10px] text-text-secondary leading-snug">
                使用 config.yaml 中为各 Agent 配置的模型
              </span>
            </span>
          </button>

          {models.length === 0 ? (
            <p className="px-3 py-3 text-[11px] text-text-secondary leading-relaxed">
              还没有自配模型。在设置面板里添加后即可在这里切换。
            </p>
          ) : (
            models.map(m => (
              <button
                key={m.id}
                type="button"
                onClick={() => choose(m.id)}
                className={clsx(
                  "w-full flex items-start gap-2 px-3 py-2 text-left transition-colors",
                  m.id === activeId ? "bg-accent/10" : "hover:bg-hover"
                )}
              >
                <span className="w-3.5 pt-0.5 shrink-0">
                  {m.id === activeId && <Check size={12} className="text-accent" />}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-[12px] text-text-main truncate">{m.name || '未命名模型'}</span>
                  <span className="block text-[10px] text-text-secondary truncate font-mono">
                    {m.model || '未指定模型'}
                  </span>
                </span>
                {!m.has_api_key && (
                  <span className="text-[10px] text-warning shrink-0 pt-0.5" title="该模型没有填写 API Key，将无法调用">
                    无 Key
                  </span>
                )}
              </button>
            ))
          )}

          <div className="border-t border-border mt-1 pt-1">
            <button
              type="button"
              onClick={() => { setOpen(false); onManage?.('models'); }}
              className="w-full flex items-center gap-2 px-3 py-2 text-left text-[12px] text-accent hover:bg-accent/10 transition-colors"
            >
              <Settings2 size={12} />
              管理模型与 API 设置
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
