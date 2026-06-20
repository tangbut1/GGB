import React from 'react';
import MainLayout from './components/Layout/MainLayout';

function App() {
  return (
    <div className="h-screen w-screen overflow-hidden text-text-main bg-app antialiased selection:bg-accent/30">
      <MainLayout />
    </div>
  );
}

export default App;
