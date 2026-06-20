import React, { useEffect } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import MainLayout from './components/Layout/MainLayout';
import Alert from './components/UI/Alert';
import HistoryPage from './pages/HistoryPage';
import SettingsPage from './pages/SettingsPage';
import useStore from './store/analysisStore';

function App() {
  const theme = useStore((s) => s.theme);
  const setTheme = useStore((s) => s.setTheme);

  // Sync theme to document and respect system preference on first load
  useEffect(() => {
    const stored = localStorage.getItem('ggb-theme');
    if (stored === 'dark' || stored === 'light') {
      setTheme(stored);
    } else {
      const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
      setTheme(prefersDark ? 'dark' : 'light');
    }
  }, []);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('ggb-theme', theme);
  }, [theme]);

  return (
    <BrowserRouter>
      <div className="h-screen w-screen overflow-hidden text-text-main bg-app antialiased selection:bg-accent/30">
        <Routes>
          <Route path="/" element={<MainLayout />} />
          <Route path="/history" element={<HistoryPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Routes>
        <Alert />
      </div>
    </BrowserRouter>
  );
}

export default App;
