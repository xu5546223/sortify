import React from 'react';
import MobileConnectionCard from '../components/MobileConnectionCard';

interface ConnectionPageProps {
  showPCMessage: (message: string, type?: 'success' | 'error' | 'info') => void;
}

const ConnectionPage: React.FC<ConnectionPageProps> = ({ showPCMessage }) => {
  return (
    <div className="min-h-screen bg-neo-bg p-4 md:p-8">
      {/* Neo-Brutalism 標題區 */}
      <header className="mb-6 md:mb-8">
        <h1 className="font-display text-3xl md:text-4xl font-bold uppercase tracking-tight text-neo-black">
          裝置同步
        </h1>
        <p className="font-bold text-gray-500 mt-1">
          連接您的手機裝置以即時上傳檔案。
        </p>
      </header>

      <div className="max-w-7xl mx-auto">
        {/* 手機端連線區域 */}
        <MobileConnectionCard showPCMessage={showPCMessage} />
      </div>
    </div>
  );
};

export default ConnectionPage;
