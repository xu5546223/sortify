import React from 'react';
import { PageHeader } from '../components';
import MobileConnectionCard from '../components/MobileConnectionCard';

interface ConnectionPageProps {
  showPCMessage: (message: string, type?: 'success' | 'error' | 'info') => void;
}

const ConnectionPage: React.FC<ConnectionPageProps> = ({ showPCMessage }) => {
  return (
    <div className="page-container">
      <PageHeader title="裝置連線管理" />

      <div className="content-wrapper">
        <div className="max-w-6xl mx-auto">
          {/* 說明區域 */}
          <div className="card mb-6">
            <div className="flex items-start gap-4">
              <div className="flex-shrink-0">
                <i className="fas fa-info-circle text-3xl text-primary-500"></i>
              </div>
              <div className="flex-1">
                <h3 className="section-title mb-2">關於裝置連線</h3>
                <p className="text-color-secondary text-sm leading-relaxed">
                  透過 QR Code 掃描，您可以快速將手機裝置與此帳號配對。配對後的裝置可以：
                </p>
                <ul className="mt-2 space-y-1 text-sm text-color-secondary">
                  <li className="flex items-center gap-2">
                    <i className="fas fa-check text-success-500 text-xs"></i>
                    拍照並上傳文件進行智能分析
                  </li>
                  <li className="flex items-center gap-2">
                    <i className="fas fa-check text-success-500 text-xs"></i>
                    隨時隨地訪問您的文件和問答記錄
                  </li>
                  <li className="flex items-center gap-2">
                    <i className="fas fa-check text-success-500 text-xs"></i>
                    享受持久化登錄，無需頻繁輸入密碼
                  </li>
                </ul>
              </div>
            </div>
          </div>

          {/* 手機端連線區域 */}
          <MobileConnectionCard showPCMessage={showPCMessage} />
        </div>
      </div>
    </div>
  );
};

export default ConnectionPage;
