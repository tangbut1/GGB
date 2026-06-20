import { create } from 'zustand';

const useStore = create((set) => ({
  // ── App state ──────────────────────────────────────────────────
  currentTaskId: null,
  currentQuery: '',
  messages: [],
  status: 'idle',      // idle | analyzing | completed | error
  systemState: '',
  analysisData: null,
  activeTab: 'trend',  // trend | sentiment | keywords | evidence

  // ── UI state ───────────────────────────────────────────────────
  sidebarCollapsed: false,
  rightPanelOpen: true,
  theme: 'dark',

  // ── App actions ────────────────────────────────────────────────
  setCurrentTaskId: (id) => set({ currentTaskId: id }),
  setCurrentQuery: (q) => set({ currentQuery: q }),
  setMessages: (msgs) => set({ messages: msgs }),
  resetMessages: () => set({ messages: [], analysisData: null }),
  addMessage: (msg) => set((s) => ({ messages: [...s.messages, msg] })),
  setStatus: (status) => set({ status }),
  setSystemState: (text) => set({ systemState: text }),
  setAnalysisData: (data) => set({ analysisData: data }),

  // ── UI actions ─────────────────────────────────────────────────
  setActiveTab: (tab) => set({ activeTab: tab }),
  toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
  toggleRightPanel: () => set((s) => ({ rightPanelOpen: !s.rightPanelOpen })),
  setTheme: (theme) => set({ theme }),
  toggleTheme: () => set((s) => ({ theme: s.theme === 'dark' ? 'light' : 'dark' })),
}));

export default useStore;
