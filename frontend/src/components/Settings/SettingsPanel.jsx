import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  X, Sun, Moon, Type, History, Cpu, Trash2, Plus, Check, Pencil,
  AlertTriangle, Loader2, KeyRound, Link2, Save,
} from 'lucide-react';
import clsx from 'clsx';
import { useTheme, useFontScale, FONT_SCALES } from '../../theme';
import { modelLabel } from '../../hooks/useModels';

const SECTIONS = [
  { id: 'appearance', label: '外观', Icon: Sun },
  { id: 'history', label: '历史记录', Icon: History },
  { id: 'models', label: '模型与 API', Icon: Cpu },
];

/**
 * 设置面板。
 *
 * 三块内容共用一个浮层而不是三个分散的入口：主题、字号、历史管理、模型配置
 * 都是"偶尔来改一次"的东西，散落在界面各处只会让主工作区变乱。
 *
 * 面板本身不做持久化之外的活儿——所有保存都立刻打到后端或 localStorage，
 * 没有"取消"按钮：用户看到的每一个开关都是即时生效的，再给一个取消只会
 * 让人以为刚才的改动没保存。
 */
export default function SettingsPanel({
  open,
  onClose,
  initialSection = 'appearance',
  groups,
  onDeleteSession,
  onClearAll,
  models,
  activeId,
  modelsLoading,
  modelsError,
  onActivateModel,
  onSaveModel,
  onDeleteModel,
}) {
  const [section, setSection] = useState(initialSection);

  useEffect(() => {
    if (open) setSection(initialSection);
  }, [open, initialSection]);

  // Esc 关闭。浮层是模态的，键盘用户必须有关门的路
  useEffect(() => {
    if (!open) return;
    const onKey = (e) => { if (e.key === 'Escape') onClose?.(); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6">
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-label="设置"
        className="relative w-full max-w-3xl max-h-[86vh] bg-panel border border-border rounded-panel shadow-panel flex flex-col overflow-hidden"
      >
        <header className="h-14 shrink-0 flex items-center justify-between px-5 border-b border-border">
          <h2 className="font-semibold text-sm text-text-main">设置</h2>
          <button
            onClick={onClose}
            title="关闭设置"
            className="p-1.5 rounded-md text-text-secondary hover:text-text-main hover:bg-hover transition-colors"
          >
            <X size={16} />
          </button>
        </header>

        <div className="flex-1 min-h-0 flex">
          <nav className="w-44 shrink-0 border-r border-border p-2 space-y-0.5 overflow-y-auto custom-scrollbar">
            {SECTIONS.map(s => (
              <button
                key={s.id}
                onClick={() => setSection(s.id)}
                className={clsx(
                  "w-full flex items-center gap-2 px-3 py-2 rounded-lg text-[12px] transition-colors text-left",
                  section === s.id
                    ? "bg-accent/10 text-accent font-medium"
                    : "text-text-secondary hover:text-text-main hover:bg-hover"
                )}
              >
                <s.Icon size={13} />
                {s.label}
              </button>
            ))}
          </nav>

          <div className="flex-1 min-w-0 overflow-y-auto custom-scrollbar p-5">
            {section === 'appearance' && <AppearanceSection />}
            {section === 'history' && (
              <HistorySection
                groups={groups}
                onDeleteSession={onDeleteSession}
                onClearAll={onClearAll}
              />
            )}
            {section === 'models' && (
              <ModelsSection
                models={models}
                activeId={activeId}
                loading={modelsLoading}
                error={modelsError}
                onActivateModel={onActivateModel}
                onSaveModel={onSaveModel}
                onDeleteModel={onDeleteModel}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ── 外观 ────────────────────────────────────────────────────────────────────

function AppearanceSection() {
  const { theme, setTheme } = useTheme();
  const { scale, setScale, meta } = useFontScale();

  return (
    <div className="space-y-7">
      <section>
        <h3 className="text-[12px] font-semibold text-text-main mb-1">主题</h3>
        <p className="text-[11px] text-text-secondary mb-3 leading-relaxed">
          两套配色都是 Slate 灰阶基底 + Teal 点缀，区别只在明暗。图表颜色跟着主题走，
          切换后无需刷新。
        </p>
        <div className="grid grid-cols-2 gap-3">
          <ThemeCard
            active={theme === 'dark'}
            onClick={() => setTheme('dark')}
            Icon={Moon}
            title="暗色"
            desc="深灰底、低对比，长时间阅读不刺眼"
            swatch={['#0B0F17', '#111827', '#14B8A6']}
          />
          <ThemeCard
            active={theme === 'light'}
            onClick={() => setTheme('light')}
            Icon={Sun}
            title="亮色"
            desc="白底、边界分明，适合明亮环境与投影"
            swatch={['#F8FAFC', '#FFFFFF', '#0D9488']}
          />
        </div>
      </section>

      <section>
        <h3 className="text-[12px] font-semibold text-text-main mb-1">字体大小</h3>
        <p className="text-[11px] text-text-secondary mb-3 leading-relaxed">
          整站等比缩放（正文、间距、圆角一起变）。当前：{meta.label} · {meta.px}px
        </p>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          {FONT_SCALES.map(s => (
            <button
              key={s.id}
              onClick={() => setScale(s.id)}
              title={s.hint}
              className={clsx(
                "flex flex-col items-start gap-1 px-3 py-2.5 rounded-card border transition-colors text-left",
                scale === s.id
                  ? "border-accent/40 bg-accent/10"
                  : "border-border bg-soft hover:border-border/80 hover:bg-hover"
              )}
            >
              <span className="flex items-center gap-1.5 w-full">
                <Type size={12} className={scale === s.id ? "text-accent" : "text-text-secondary"} />
                <span className={clsx(
                  "text-[12px]",
                  scale === s.id ? "text-accent font-medium" : "text-text-main"
                )}>
                  {s.label}
                </span>
                {scale === s.id && <Check size={11} className="text-accent ml-auto" />}
              </span>
              <span className="text-[10px] text-text-secondary tabular-nums">{s.px}px</span>
            </button>
          ))}
        </div>
      </section>
    </div>
  );
}

function ThemeCard({ active, onClick, Icon, title, desc, swatch }) {
  return (
    <button
      onClick={onClick}
      className={clsx(
        "flex flex-col gap-2 p-3 rounded-card border transition-colors text-left",
        active ? "border-accent/40 bg-accent/10" : "border-border bg-soft hover:border-border/80 hover:bg-hover"
      )}
    >
      <div className="flex items-center gap-2">
        <Icon size={14} className={active ? "text-accent" : "text-text-secondary"} />
        <span className={clsx("text-[12px]", active ? "text-accent font-medium" : "text-text-main")}>
          {title}
        </span>
        {active && <Check size={12} className="text-accent ml-auto" />}
      </div>
      {/* 三块色票让"这套配色长什么样"在点击前就可见，不用靠文字想象 */}
      <div className="flex gap-1.5">
        {swatch.map(c => (
          <span
            key={c}
            className="w-6 h-6 rounded-md border border-border/60"
            style={{ background: c }}
          />
        ))}
      </div>
      <span className="text-[10px] text-text-secondary leading-snug">{desc}</span>
    </button>
  );
}

// ── 历史记录批量管理 ────────────────────────────────────────────────────────

function HistorySection({ groups, onDeleteSession, onClearAll }) {
  const all = useMemo(() => {
    const list = Array.isArray(groups) ? groups : [];
    return list.flatMap(g =>
      (g.conversations || []).map(c => ({ ...c, groupName: g.name }))
    );
  }, [groups]);

  const [selected, setSelected] = useState(() => new Set());
  const [confirmClear, setConfirmClear] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');

  // 面板每次打开都是全新的一份勾选，不要把上一轮的残留带进来
  useEffect(() => {
    setSelected(new Set());
    setConfirmClear(false);
    setNotice('');
  }, [groups]);

  const toggle = (id) => {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const allChecked = all.length > 0 && selected.size === all.length;
  const toggleAll = () => {
    setSelected(prev => (prev.size === all.length ? new Set() : new Set(all.map(c => c.taskId))));
  };

  const runDelete = async (ids) => {
    if (ids.length === 0) return;
    setBusy(true);
    setNotice('');
    try {
      for (const id of ids) await onDeleteSession(id);
      setSelected(new Set());
      setNotice(`已删除 ${ids.length} 条对话记录。`);
    } catch (err) {
      setNotice(err.message || '删除失败');
    } finally {
      setBusy(false);
      setConfirmClear(false);
    }
  };

  const runClearAll = async () => {
    setBusy(true);
    setNotice('');
    try {
      const res = await onClearAll();
      const skipped = res?.skipped?.length || 0;
      setNotice(
        skipped > 0
          ? `已清空 ${res?.deleted ?? 0} 条，${skipped} 条正在分析中的任务被跳过。`
          : `已清空全部 ${res?.deleted ?? 0} 条对话记录。`
      );
      setSelected(new Set());
    } catch (err) {
      setNotice(err.message || '清空失败');
    } finally {
      setBusy(false);
      setConfirmClear(false);
    }
  };

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-[12px] font-semibold text-text-main mb-1">历史记录批量管理</h3>
        <p className="text-[11px] text-text-secondary leading-relaxed">
          {all.length > 0 ? (
            <>
              共 {all.length} 条记录。删除会同时清掉任务记录、完整分析结果和
              项目记忆里的会话原文，<span className="text-danger">不可恢复</span>。
              正在分析中的任务无法删除。
            </>
          ) : (
            <>暂无历史记录。完成一次分析后，这里会出现可批量管理的对话记录。</>
          )}
        </p>
      </div>

      <div className="flex items-center gap-2 flex-wrap">
        <button
          onClick={toggleAll}
          disabled={all.length === 0}
          className="text-[11px] px-2.5 py-1 rounded-lg border border-border bg-soft text-text-secondary hover:text-text-main disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          {allChecked ? '取消全选' : '全选'}
        </button>
        <button
          onClick={() => runDelete([...selected])}
          disabled={selected.size === 0 || busy}
          className="text-[11px] px-2.5 py-1 rounded-lg border border-danger/30 bg-danger/10 text-danger hover:bg-danger/15 disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex items-center gap-1"
        >
          {busy ? <Loader2 size={11} className="animate-spin" /> : <Trash2 size={11} />}
          删除所选 {selected.size > 0 && `(${selected.size})`}
        </button>
        <button
          onClick={() => setConfirmClear(true)}
          disabled={all.length === 0 || busy}
          className="text-[11px] px-2.5 py-1 rounded-lg border border-danger/30 bg-danger/10 text-danger hover:bg-danger/15 disabled:opacity-40 disabled:cursor-not-allowed transition-colors ml-auto"
        >
          清空全部
        </button>
      </div>

      {notice && (
        <p className="text-[11px] text-accent bg-accent/10 border border-accent/25 rounded-lg px-3 py-2 leading-relaxed">
          {notice}
        </p>
      )}

      {confirmClear && (
        <div className="rounded-card border border-danger/30 bg-danger/10 p-3 space-y-2">
          <p className="text-[12px] text-danger font-medium flex items-center gap-1.5">
            <AlertTriangle size={13} />
            确认清空全部历史记录？
          </p>
          <p className="text-[11px] text-text-secondary leading-relaxed">
            这会删除磁盘上所有任务记录与分析结果。正在分析中的任务会被跳过并保留。
          </p>
          <div className="flex gap-2">
            <button
              onClick={runClearAll}
              disabled={busy}
              className="text-[11px] px-3 py-1 rounded-lg bg-danger text-white hover:bg-danger/90 disabled:opacity-50 transition-colors"
            >
              {busy ? '处理中...' : '确认清空'}
            </button>
            <button
              onClick={() => setConfirmClear(false)}
              className="text-[11px] px-3 py-1 rounded-lg border border-border text-text-secondary hover:text-text-main transition-colors"
            >
              取消
            </button>
          </div>
        </div>
      )}

      <div className="rounded-card border border-border overflow-hidden">
        {all.length === 0 ? (
          <p className="text-[11px] text-text-secondary px-3 py-6 text-center">暂无历史记录</p>
        ) : (
          <ul className="divide-y divide-border max-h-72 overflow-y-auto custom-scrollbar">
            {all.map(c => (
              <li key={c.taskId}>
                <label className="flex items-center gap-2.5 px-3 py-2 hover:bg-hover cursor-pointer transition-colors">
                  <input
                    type="checkbox"
                    checked={selected.has(c.taskId)}
                    onChange={() => toggle(c.taskId)}
                    className="w-3.5 h-3.5 rounded accent-[rgb(var(--c-accent))] shrink-0"
                  />
                  <span className="min-w-0 flex-1">
                    <span className="block text-[12px] text-text-main truncate">{c.title || '未命名分析'}</span>
                    <span className="block text-[10px] text-text-secondary truncate">
                      {c.groupName}{c.time ? ` · ${c.time}` : ''}{c.date ? ` ${c.date}` : ''}
                    </span>
                  </span>
                </label>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

// ── 模型与 API ──────────────────────────────────────────────────────────────

const EMPTY_FORM = {
  id: '',
  name: '',
  base_url: '',
  api_key: '',
  model: '',
  temperature: '0.7',
  timeout: '120',
  max_retries: '2',
  note: '',
};

function ModelsSection({ models, activeId, loading, error, onActivateModel, onSaveModel, onDeleteModel }) {
  const [form, setForm] = useState(EMPTY_FORM);
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState('');
  const [formError, setFormError] = useState('');
  const [confirmDelete, setConfirmDelete] = useState(null);
  const formRef = useRef(null);

  const set = (key) => (e) => setForm(prev => ({ ...prev, [key]: e.target.value }));

  const startCreate = () => {
    setForm(EMPTY_FORM);
    setEditing(true);
    setFormError('');
    setNotice('');
    formRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  const startEdit = (m) => {
    setForm({
      id: m.id,
      name: m.name || '',
      base_url: m.base_url || '',
      api_key: '', // 不回显 Key：留空表示不换，遮罩值只作为 placeholder 提示
      model: m.model || '',
      temperature: String(m.temperature ?? 0.7),
      timeout: String(m.timeout ?? 120),
      max_retries: String(m.max_retries ?? 2),
      note: m.note || '',
    });
    setEditing(true);
    setFormError('');
    setNotice('');
    formRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  const submit = async (e) => {
    e.preventDefault();
    setFormError('');
    setNotice('');

    const payload = {
      id: form.id || undefined,
      name: form.name.trim(),
      base_url: form.base_url.trim(),
      model: form.model.trim(),
      note: form.note.trim(),
      temperature: Number(form.temperature),
      timeout: Number(form.timeout),
      max_retries: Number(form.max_retries),
    };
    // 新增必须给 Key；编辑时留空表示沿用旧 Key。把遮罩串原样提交上去会被
    // 后端当成"用户没改"，但用户真输入了一串星号的情况无法区分，所以这里
    // 直接不传这个键，语义更干净。
    if (form.api_key.trim()) payload.api_key = form.api_key.trim();

    if (!payload.name || !payload.base_url || !payload.model) {
      setFormError('名称、Base URL 和模型名是必填项。');
      return;
    }
    if (!Number.isFinite(payload.temperature) || payload.temperature < 0 || payload.temperature > 2) {
      setFormError('温度需在 0 ~ 2 之间。');
      return;
    }

    setSaving(true);
    try {
      await onSaveModel(payload);
      setNotice(payload.id ? '模型已更新。' : '模型已添加。');
      setEditing(false);
      setForm(EMPTY_FORM);
    } catch (err) {
      setFormError(err.message || '保存失败');
    } finally {
      setSaving(false);
    }
  };

  const doDelete = async (id) => {
    setNotice('');
    try {
      await onDeleteModel(id);
      setNotice('模型已删除。');
      if (form.id === id) { setEditing(false); setForm(EMPTY_FORM); }
    } catch (err) {
      setNotice(err.message || '删除失败');
    } finally {
      setConfirmDelete(null);
    }
  };

  return (
    <div className="space-y-5">
      <div>
        <h3 className="text-[12px] font-semibold text-text-main mb-1">模型与 API 设置</h3>
        <p className="text-[11px] text-text-secondary leading-relaxed">
          这里配置的模型会覆盖 config.yaml 的默认配置，红蓝双方与裁判都用它。
          接口需兼容 OpenAI Chat Completions 格式。Key 只存在本机，接口只回显后 4 位。
        </p>
      </div>

      {error && (
        <p className="text-[11px] text-danger bg-danger/10 border border-danger/25 rounded-lg px-3 py-2 leading-relaxed">
          {error}
        </p>
      )}
      {notice && !formError && (
        <p className="text-[11px] text-accent bg-accent/10 border border-accent/25 rounded-lg px-3 py-2 leading-relaxed">
          {notice}
        </p>
      )}

      {/* 当前选用 */}
      <div className="rounded-card border border-border bg-soft p-3 space-y-2">
        <div className="flex items-center justify-between gap-2">
          <span className="text-[11px] text-text-secondary">当前选用</span>
          <span className="text-[12px] text-text-main font-medium">
            {modelLabel(models.find(m => m.id === activeId))}
          </span>
        </div>
        <button
          onClick={() => onActivateModel(null)}
          disabled={!activeId}
          className="text-[11px] text-accent hover:text-accent-strong disabled:text-text-secondary/50 disabled:cursor-not-allowed transition-colors"
        >
          恢复使用 config.yaml 默认配置
        </button>
      </div>

      <div className="flex items-center justify-between">
        <h4 className="text-[11px] font-semibold text-text-secondary uppercase tracking-wider">
          已配置的模型 {models.length > 0 && `(${models.length})`}
        </h4>
        <button
          onClick={startCreate}
          className="text-[11px] px-2.5 py-1 rounded-lg bg-accent hover:bg-accent-strong text-on-accent flex items-center gap-1 transition-colors"
        >
          <Plus size={11} /> 添加模型
        </button>
      </div>

      {loading ? (
        <p className="text-[11px] text-text-secondary flex items-center gap-1.5">
          <Loader2 size={11} className="animate-spin" /> 加载中...
        </p>
      ) : models.length === 0 ? (
        <p className="text-[11px] text-text-secondary leading-relaxed rounded-card border border-border px-3 py-4">
          还没有自配模型。当前使用 config.yaml 的默认配置。点「添加模型」接入其它服务商。
        </p>
      ) : (
        <ul className="space-y-1.5">
          {models.map(m => (
            <li
              key={m.id}
              className={clsx(
                "rounded-card border p-3 transition-colors",
                m.id === activeId ? "border-accent/40 bg-accent/10" : "border-border bg-soft"
              )}
            >
              <div className="flex items-start gap-2">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span className="text-[12px] text-text-main font-medium truncate">{m.name || '未命名模型'}</span>
                    {m.id === activeId && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-accent/15 text-accent border border-accent/25 shrink-0">
                        使用中
                      </span>
                    )}
                    {!m.has_api_key && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-warning/15 text-warning border border-warning/25 shrink-0">
                        无 Key
                      </span>
                    )}
                  </div>
                  <p className="text-[10px] text-text-secondary font-mono truncate mt-0.5">{m.model || '未指定模型'}</p>
                  <p className="text-[10px] text-text-secondary truncate">{m.base_url}</p>
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  <button
                    onClick={() => onActivateModel(m.id)}
                    disabled={m.id === activeId}
                    title={m.id === activeId ? '正在使用' : '切换到这个模型'}
                    className="text-[11px] px-2 py-1 rounded-md border border-border text-text-secondary hover:text-text-main hover:border-border/80 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                  >
                    选用
                  </button>
                  <button
                    onClick={() => startEdit(m)}
                    title="编辑"
                    className="p-1.5 rounded-md text-text-secondary hover:text-text-main hover:bg-hover transition-colors"
                  >
                    <Pencil size={12} />
                  </button>
                  <button
                    onClick={() => setConfirmDelete(m.id)}
                    title="删除"
                    className="p-1.5 rounded-md text-text-secondary hover:text-danger hover:bg-danger/10 transition-colors"
                  >
                    <Trash2 size={12} />
                  </button>
                </div>
              </div>

              {confirmDelete === m.id && (
                <div className="mt-2 pt-2 border-t border-border flex items-center gap-2 flex-wrap">
                  <span className="text-[11px] text-danger">确认删除「{m.name}」？</span>
                  <button
                    onClick={() => doDelete(m.id)}
                    className="text-[11px] px-2 py-0.5 rounded-md bg-danger text-white hover:bg-danger/90 transition-colors"
                  >
                    确认
                  </button>
                  <button
                    onClick={() => setConfirmDelete(null)}
                    className="text-[11px] px-2 py-0.5 rounded-md border border-border text-text-secondary hover:text-text-main transition-colors"
                  >
                    取消
                  </button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}

      {editing && (
        <form ref={formRef} onSubmit={submit} className="rounded-card border border-border bg-soft p-4 space-y-3">
          <h4 className="text-[12px] font-semibold text-text-main">
            {form.id ? '编辑模型' : '添加模型'}
          </h4>

          <Field label="名称" hint="面板和选择器里显示的名字" required>
            <input
              value={form.name}
              onChange={set('name')}
              placeholder="例如：DeepSeek 官方"
              className={inputCls}
            />
          </Field>

          <Field label="Base URL" hint="OpenAI 兼容接口地址，需公网可达" required>
            <div className="relative">
              <Link2 size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-text-secondary pointer-events-none" />
              <input
                value={form.base_url}
                onChange={set('base_url')}
                placeholder="https://api.deepseek.com/v1"
                className={clsx(inputCls, "pl-7 font-mono")}
              />
            </div>
          </Field>

          <Field
            label="API Key"
            hint={form.id
              ? '留空表示不更换当前 Key'
              : '调用接口用的密钥，只保存在本机'}
            required={!form.id}
          >
            <div className="relative">
              <KeyRound size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-text-secondary pointer-events-none" />
              <input
                type="password"
                value={form.api_key}
                onChange={set('api_key')}
                placeholder={form.id ? '••••••••••••（未更改）' : 'sk-...'}
                autoComplete="new-password"
                className={clsx(inputCls, "pl-7 font-mono")}
              />
            </div>
          </Field>

          <Field label="模型名" hint="接口里的 model 字段值" required>
            <input
              value={form.model}
              onChange={set('model')}
              placeholder="例如：deepseek-chat"
              className={clsx(inputCls, "font-mono")}
            />
          </Field>

          <div className="grid grid-cols-3 gap-3">
            <Field label="温度" hint="0 ~ 2">
              <input
                value={form.temperature}
                onChange={set('temperature')}
                inputMode="decimal"
                className={clsx(inputCls, "font-mono")}
              />
            </Field>
            <Field label="超时（秒）" hint="10 ~ 600">
              <input
                value={form.timeout}
                onChange={set('timeout')}
                inputMode="numeric"
                className={clsx(inputCls, "font-mono")}
              />
            </Field>
            <Field label="重试次数" hint="1 ~ 5">
              <input
                value={form.max_retries}
                onChange={set('max_retries')}
                inputMode="numeric"
                className={clsx(inputCls, "font-mono")}
              />
            </Field>
          </div>

          <Field label="备注" hint="可选，给自己看的说明">
            <input
              value={form.note}
              onChange={set('note')}
              placeholder="例如：便宜快，适合红蓝互驳"
              className={inputCls}
            />
          </Field>

          {formError && (
            <p className="text-[11px] text-danger leading-relaxed">{formError}</p>
          )}

          <div className="flex items-center gap-2 pt-1">
            <button
              type="submit"
              disabled={saving}
              className="text-[12px] px-3 py-1.5 rounded-lg bg-accent hover:bg-accent-strong text-on-accent flex items-center gap-1.5 disabled:opacity-50 transition-colors"
            >
              {saving ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
              保存
            </button>
            <button
              type="button"
              onClick={() => { setEditing(false); setForm(EMPTY_FORM); setFormError(''); }}
              className="text-[12px] px-3 py-1.5 rounded-lg border border-border text-text-secondary hover:text-text-main transition-colors"
            >
              取消
            </button>
          </div>
        </form>
      )}
    </div>
  );
}

const inputCls = "w-full bg-panel border border-border rounded-lg px-2.5 py-1.5 text-[12px] text-text-main placeholder-text-secondary/50 outline-none focus:border-accent/50 transition-colors";

function Field({ label, hint, required, children }) {
  return (
    <label className="block space-y-1">
      <span className="flex items-baseline gap-1.5">
        <span className="text-[11px] text-text-main">{label}</span>
        {required && <span className="text-[10px] text-danger">必填</span>}
        {hint && <span className="text-[10px] text-text-secondary/80 truncate">{hint}</span>}
      </span>
      {children}
    </label>
  );
}
