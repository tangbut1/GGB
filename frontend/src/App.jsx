import React from 'react';
import MainLayout from './components/Layout/MainLayout';
import { initTheme } from './theme';

// 在 React 挂载前同步决定明暗，否则刷新时会先闪一下另一套配色
initTheme();

function App() {
  return (
    <div className="h-screen w-screen overflow-hidden text-text-main bg-app antialiased">
      <MainLayout />
    </div>
  );
}

export default App;
