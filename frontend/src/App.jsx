import React from 'react';
import MainLayout from './components/Layout/MainLayout';
import { initTheme, initFontScale } from './theme';

// 在 React 挂载前同步决定明暗，否则刷新时会先闪一下另一套配色
initTheme();
// 同理：根字号要在首帧布局前定下来，否则会看到一次从默认字号跳到所选字号的跳动
initFontScale();

function App() {
  return (
    <div className="h-screen w-screen overflow-hidden text-text-main bg-app antialiased">
      <MainLayout />
    </div>
  );
}

export default App;
