/**
 * 明暗主题的唯一事实来源。
 *
 * 颜色全部定义在 index.css 的 CSS 变量里（`:root` 暗色 / `[data-theme='light']`
 * 亮色），tailwind.config.js 的 token 直接指向这些变量。JS 侧只有两个需求：
 * 记住当前是哪一套、以及在切换后让读字面色值的地方（Chart.js 的 canvas）
 * 重新取一遍值。
 */

import { useCallback, useEffect, useMemo, useState } from 'react';

export const THEME_STORAGE_KEY = 'ggb-theme';

const THEMES = ['dark', 'light'];

function readTheme() {
  if (typeof document === 'undefined') return 'dark';
  const attr = document.documentElement.dataset.theme;
  return THEMES.includes(attr) ? attr : 'dark';
}

function applyTheme(theme) {
  const root = document.documentElement;
  if (theme === 'light') root.dataset.theme = 'light';
  else root.removeAttribute('data-theme');
  try {
    localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    // 隐私模式下 localStorage 会抛异常，主题照样要能切
  }
}

/** 在首个客户端渲染前同步执行，避免刷新时闪一下另一套配色。 */
export function initTheme() {
  let saved = null;
  try {
    saved = localStorage.getItem(THEME_STORAGE_KEY);
  } catch {
    saved = null;
  }
  applyTheme(THEMES.includes(saved) ? saved : 'dark');
}

export function useTheme() {
  const [theme, setThemeState] = useState(readTheme);

  // 主题是全局的，任何一处切换都要通知所有订阅者（Chart.js 那几处要靠它重读色值）
  useEffect(() => {
    const sync = () => setThemeState(readTheme());
    window.addEventListener('themechange', sync);
    return () => window.removeEventListener('themechange', sync);
  }, []);

  const setTheme = useCallback((next) => {
    const value = typeof next === 'function' ? next(readTheme()) : next;
    if (!THEMES.includes(value)) return;
    applyTheme(value);
    window.dispatchEvent(new Event('themechange'));
  }, []);

  const toggleTheme = useCallback(() => {
    setTheme(readTheme() === 'dark' ? 'light' : 'dark');
  }, [setTheme]);

  return { theme, setTheme, toggleTheme };
}

// ── 字号 ────────────────────────────────────────────────────────────────────

export const FONT_SCALE_STORAGE_KEY = 'ggb-font-scale';

/**
 * 字号档位，单位是 html 的 font-size（px）。
 *
 * 走根字号而不是给每个组件加一档 class：Tailwind 的 text-*、间距、圆角
 * 全部以 rem 为单位，改根字号就等于整站等比缩放，这正是"字号调节"该有的
 * 效果——长文阅读时要的是正文和留白一起变大，只有字变大、行距还是原来那样
 * 反而更挤。档位上限收到 20px：再往上 4K 以下的窗口里辩论卡片会开始折行。
 *
 * 默认 16px 是浏览器原值，保持现状不引入"打开就变了"的观感落差。
 */
export const FONT_SCALES = [
  { id: 'sm', label: '小', px: 14, hint: '一屏看更多内容' },
  { id: 'md', label: '默认', px: 16, hint: '浏览器默认字号' },
  { id: 'lg', label: '大', px: 18, hint: '长时间阅读更省力' },
  { id: 'xl', label: '特大', px: 20, hint: '投影或远距离观看' },
];

const DEFAULT_SCALE = 'md';

function readScale() {
  if (typeof document === 'undefined') return DEFAULT_SCALE;
  const attr = document.documentElement.dataset.fontScale;
  return FONT_SCALES.some(s => s.id === attr) ? attr : DEFAULT_SCALE;
}

function applyScale(id) {
  const entry = FONT_SCALES.find(s => s.id === id) || FONT_SCALES[1];
  if (typeof document === 'undefined') return;
  document.documentElement.style.fontSize = `${entry.px}px`;
  document.documentElement.dataset.fontScale = entry.id;
  try {
    localStorage.setItem(FONT_SCALE_STORAGE_KEY, entry.id);
  } catch {
    // 隐私模式下 localStorage 会抛异常，字号照样要能切
  }
}

/** 在首个客户端渲染前同步执行，避免刷新时先按默认字号布局再跳。 */
export function initFontScale() {
  let saved = null;
  try {
    saved = localStorage.getItem(FONT_SCALE_STORAGE_KEY);
  } catch {
    saved = null;
  }
  applyScale(FONT_SCALES.some(s => s.id === saved) ? saved : DEFAULT_SCALE);
}

export function useFontScale() {
  const [scale, setScaleState] = useState(readScale);

  useEffect(() => {
    const sync = () => setScaleState(readScale());
    window.addEventListener('fontscalechange', sync);
    return () => window.removeEventListener('fontscalechange', sync);
  }, []);

  const setScale = useCallback((next) => {
    if (!FONT_SCALES.some(s => s.id === next)) return;
    applyScale(next);
    window.dispatchEvent(new Event('fontscalechange'));
  }, []);

  const meta = FONT_SCALES.find(s => s.id === scale) || FONT_SCALES[1];
  return { scale, setScale, meta };
}

// JS 侧沿用驼峰键（C.tooltipBg），CSS 变量是 kebab-case（--c-tooltip-bg）。
// 两张名字必须显式对上：CSS 自定义属性大小写敏感，拼错不报错，只会
// getPropertyValue 拿到空字符串，图表颜色静默失效。
const CHART_VARS = [
  ['axis', 'axis'],
  ['grid', 'grid'],
  ['tooltipBg', 'tooltip-bg'],
  ['tooltipBorder', 'tooltip-border'],
  ['tooltipTitle', 'tooltip-title'],
  ['tooltipBody', 'tooltip-body'],
  ['accent', 'accent'],
  ['accentSoft', 'accent-soft'],
  ['accentLine', 'accent-line'],
  ['success', 'success'],
  ['warning', 'warning'],
  ['danger', 'danger'],
  ['neutral', 'neutral'],
  ['red', 'red'],
  ['blue', 'blue'],
  ['judge', 'judge'],
  ['card', 'card'],
  ['panel', 'panel'],
  ['text', 'text'],
];

/**
 * CSS 变量 → 具体色值。
 *
 * 实色在 index.css 里写成 "R G B" 三通道（为了让 Tailwind 能施加不透明度），
 * 这里补成 Chart.js 认的十六进制；本身就是 rgba() 的叠加色原样返回。
 * 所以两种格式都要认，写死一种会在另一种主题下静默拿到非法颜色。
 */
function toCssColor(raw) {
  if (/^[0-9\s.]+$/.test(raw)) {
    const parts = raw.split(/\s+/).map(Number);
    if (parts.length === 3 && parts.every(n => Number.isFinite(n))) {
      return '#' + parts.map(n => Math.round(n).toString(16).padStart(2, '0')).join('');
    }
  }
  return raw;
}

/**
 * 读一份当前主题的字面色值。canvas 里的颜色必须是具体色值，Tailwind class
 * 在 <canvas> 中不生效，所以这里从 CSS 变量取，而不是在 JS 里另抄一套。
 * theme 变化时 useMemo 重新求值，图表跟着换色。
 */
export function useChartColors(theme) {
  return useMemo(() => {
    const out = {};
    if (typeof window === 'undefined') return out;
    const style = getComputedStyle(document.documentElement);
    for (const [key, cssName] of CHART_VARS) {
      const raw = style.getPropertyValue(`--c-${cssName}`).trim();
      if (!raw) {
        // 变量名对不上时这里是最早知道的地方，别让空颜色一路带进 canvas
        console.warn(`[theme] CSS 变量 --c-${cssName} 未定义，图表该项将失色`);
      }
      out[key] = toCssColor(raw);
    }
    return out;
    // theme 是触发重算的开关：CSS 变量本身不会通知 React
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [theme]);
}
