import React, { useState, useEffect, useCallback } from 'react';
import type {
    SettingsData,
    UpdatableSettingsPayload,
    TestDBConnectionRequest,
    TestDBConnectionResponse
} from '../types/apiTypes';
import {
    getSettings,
    updateSettings,
    getGoogleAIModels,
    testDBConnection,
} from '../services/systemService';

interface SettingsPageProps {
  showPCMessage: (message: string, type: 'success' | 'error' | 'info') => void;
}

const SettingsPage: React.FC<SettingsPageProps> = ({ showPCMessage }) => {
  const initialSettings: SettingsData = {
    aiService: {
      model: '',
      temperature: 0.7,
      is_api_key_configured: false,
      provider: 'google',
      ensure_chinese_output: true,
      max_output_tokens: null,
      prompt_input_max_length: 6000,
    },
    database: {
      uri: '',
      dbName: '',
    },
  };

  const [settings, setSettings] = useState<SettingsData>(initialSettings);
  const [availableAIModels, setAvailableAIModels] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isSaving, setIsSaving] = useState<boolean>(false);
  const [isTestingDB, setIsTestingDB] = useState<boolean>(false);
  const [dbTestMessage, setDbTestMessage] = useState<string | null>(null);
  const [isDBVerified, setIsDBVerified] = useState<boolean>(false);
  const [autoTestTimer, setAutoTestTimer] = useState<NodeJS.Timeout | null>(null);

  const fetchInitialData = useCallback(async () => {
    setIsLoading(true);
    try {
      const data = await getSettings();
      setSettings(prev => {
        const newAiServiceSettings = {
          ...prev.aiService,
          ...(data.aiService || {}),
        };

        if (typeof data.aiService?.ensure_chinese_output === 'boolean') {
          newAiServiceSettings.ensure_chinese_output = data.aiService.ensure_chinese_output;
        } else {
          newAiServiceSettings.ensure_chinese_output = prev.aiService?.ensure_chinese_output ?? true;
        }

        if (typeof data.aiService?.max_output_tokens === 'number') {
          newAiServiceSettings.max_output_tokens = data.aiService.max_output_tokens;
        } else {
          newAiServiceSettings.max_output_tokens = prev.aiService?.max_output_tokens ?? null;
        }

        if (typeof data.aiService?.prompt_input_max_length === 'number') {
          newAiServiceSettings.prompt_input_max_length = data.aiService.prompt_input_max_length;
        } else {
          newAiServiceSettings.prompt_input_max_length = prev.aiService?.prompt_input_max_length ?? 6000;
        }
        
        return {
          ...prev,
          ...data,
          aiService: newAiServiceSettings,
          database: { ...prev.database, ...(data.database || {}) },
        };
      });
      const models = await getGoogleAIModels();
      setAvailableAIModels(models);
      showPCMessage('成功獲取目前設定', 'success');
    } catch (error) {
      console.error('Failed to fetch settings:', error);
      showPCMessage('獲取設定失敗', 'error');
    }
    setIsLoading(false);
  }, [showPCMessage]);

  useEffect(() => {
    fetchInitialData();
  }, [fetchInitialData]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value, type } = e.target;
    const inputElement = e.target as HTMLInputElement;
    const newBooleanState = inputElement.checked;

    setSettings(prev => {
      const newSettings = { ...prev };
      const nameParts = name.split('.');
      const section = nameParts[0];
      const field = nameParts[1];

      if (field && (section === 'aiService' || section === 'database')) {
        const currentSectionData = newSettings[section as keyof Pick<SettingsData, 'aiService' | 'database'>] || {};
        let newValue;

        if (section === 'aiService' && field === 'ensure_chinese_output') {
          newValue = newBooleanState;
        } else if (type === 'number' || name === 'aiService.max_output_tokens' || name === 'aiService.prompt_input_max_length') {
          newValue = parseInt(value, 10);
          if ((name === 'aiService.max_output_tokens' || name === 'aiService.prompt_input_max_length') && (isNaN(newValue) || newValue <= 0)) {
            newValue = null;
          }
        } else {
          newValue = value;
        }
        
        newSettings[section as keyof Pick<SettingsData, 'aiService' | 'database'>] = {
          ...(typeof currentSectionData === 'object' && currentSectionData !== null ? currentSectionData : {}),
          [field]: newValue,
        };

        if (section === 'database') {
          setIsDBVerified(false);
          setDbTestMessage(null);
        }
      }
      return newSettings;
    });
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    const dbUri = settings.database?.uri;
    const dbName = settings.database?.dbName;
    const hasDatabaseSettings = settings.database && (dbUri || dbName);

    if (hasDatabaseSettings && !isDBVerified) {
        showPCMessage("請先成功測試資料庫連線", "error");
        return;
    }

    setIsSaving(true);
    const payload: UpdatableSettingsPayload = {
      aiService: {
        provider: settings.aiService?.provider || 'google',
        model: settings.aiService?.model || null,
        temperature: settings.aiService?.temperature ?? 0.7,
        ensure_chinese_output: settings.aiService?.ensure_chinese_output ?? true,
        max_output_tokens: settings.aiService?.max_output_tokens ?? null,
        prompt_input_max_length: settings.aiService?.prompt_input_max_length ?? 6000,
      },
      database: {
        uri: settings.database?.uri || null,
        dbName: settings.database?.dbName || null,
      },
    };

    try {
      await updateSettings(payload);
      showPCMessage('設定已儲存', 'success');
      await fetchInitialData();
    } catch (error) {
      console.error('Failed to save:', error);
      showPCMessage('儲存失敗', 'error');
    }
    setIsSaving(false);
  };

  // 自動測試資料庫連線
  useEffect(() => {
    const dbUri = settings.database?.uri;
    const dbName = settings.database?.dbName;

    if (autoTestTimer) clearTimeout(autoTestTimer);

    if (dbUri && dbName && dbUri.trim() && dbName.trim()) {
      const timer = setTimeout(async () => {
        setIsTestingDB(true);
        setDbTestMessage(null);
        try {
          const payload: TestDBConnectionRequest = { uri: dbUri, db_name: dbName };
          const response = await testDBConnection(payload);
          setDbTestMessage(response.message);
          setIsDBVerified(response.success);
        } catch (error) {
          const message = error instanceof Error ? error.message : "測試失敗";
          setDbTestMessage(message);
          setIsDBVerified(false);
        }
        setIsTestingDB(false);
      }, 1500);

      setAutoTestTimer(timer);
    } else {
      setIsDBVerified(false);
      setDbTestMessage(null);
    }

    return () => {
      if (autoTestTimer) clearTimeout(autoTestTimer);
    };
  }, [settings.database?.uri, settings.database?.dbName]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-neo-bg">
        <div className="text-center">
          <div className="text-4xl font-heading font-black uppercase mb-4">LOADING...</div>
          <div className="w-16 h-16 border-3 border-neo-black border-t-neo-primary animate-spin mx-auto"></div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-neo-bg p-6 md:p-10">
      <div className="mb-8">
        <h1 className="font-heading text-5xl md:text-6xl font-black uppercase mb-2">SYSTEM SETTINGS</h1>
        <p className="font-body font-medium text-gray-600">Configuration for AI models and Database connections.</p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* AI 服務設定 */}
        <div className="bg-white border-3 border-neo-black shadow-neo-lg p-6">
          <div className="flex items-center gap-3 mb-6 border-b-3 border-neo-black pb-4">
            <div className="bg-neo-active p-2 border-2 border-neo-black">
              <svg className="w-6 h-6 text-white" fill="currentColor" viewBox="0 0 20 20">
                <path d="M13 7H7v6h6V7z"></path>
                <path fillRule="evenodd" d="M7 2a1 1 0 012 0v1h2V2a1 1 0 112 0v1h2a2 2 0 012 2v2h1a1 1 0 110 2h-1v2h1a1 1 0 110 2h-1v2a2 2 0 01-2 2h-2v1a1 1 0 11-2 0v-1H9v1a1 1 0 11-2 0v-1H5a2 2 0 01-2-2v-2H2a1 1 0 110-2h1V9H2a1 1 0 010-2h1V5a2 2 0 012-2h2V2zM5 5h10v10H5V5z" clipRule="evenodd"></path>
              </svg>
            </div>
            <h2 className="font-heading text-2xl md:text-3xl font-black uppercase">AI 服務設定</h2>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <label className="block font-heading font-black text-sm uppercase mb-2">AI 模型 (Google)</label>
              <select
                name="aiService.model"
                value={settings.aiService?.model || ''}
                onChange={handleChange}
                disabled={availableAIModels.length === 0}
                className="w-full px-4 py-3 bg-white border-2 border-neo-black shadow-neo-sm font-body font-medium focus:outline-none focus:shadow-[4px_4px_0px_0px_#29bf12] transition-shadow"
              >
                <option value="">選擇模型...</option>
                {availableAIModels.map(model => (
                  <option key={model} value={model}>{model}</option>
                ))}
              </select>
            </div>

            <div>
              <label className="block font-heading font-black text-sm uppercase mb-2">Temperature</label>
              <div className="bg-neo-bg border-2 border-neo-black p-4">
                <input
                  name="aiService.temperature"
                  type="range"
                  min="0"
                  max="1"
                  step="0.1"
                  value={settings.aiService?.temperature ?? 0.7}
                  onChange={handleChange}
                  className="w-full h-3 bg-white border-2 border-neo-black appearance-none cursor-pointer"
                />
                <div className="flex justify-between text-xs font-mono font-bold mt-2">
                  <span>精確</span>
                  <span className="text-lg">{settings.aiService?.temperature ?? 0.7}</span>
                  <span>創意</span>
                </div>
              </div>
            </div>

            <div>
              <label className="block font-heading font-black text-sm uppercase mb-2">最大輸出 Token</label>
              <input
                name="aiService.max_output_tokens"
                type="number"
                value={settings.aiService?.max_output_tokens === null || settings.aiService?.max_output_tokens === undefined ? '' : String(settings.aiService.max_output_tokens)}
                onChange={handleChange}
                placeholder="30000"
                min="0"
                className="w-full px-4 py-3 bg-white border-2 border-neo-black shadow-neo-sm font-mono font-bold focus:outline-none focus:shadow-[4px_4px_0px_0px_#29bf12] transition-shadow"
              />
              <p className="text-xs font-body mt-2 text-gray-600">
                <span className="font-bold">TOKENS</span> — 設定 AI 生成內容的最大 token 數量
              </p>
            </div>

            <div>
              <label className="block font-heading font-black text-sm uppercase mb-2">提示詞最大長度</label>
              <input
                name="aiService.prompt_input_max_length"
                type="number"
                value={settings.aiService?.prompt_input_max_length === null || settings.aiService?.prompt_input_max_length === undefined ? '' : String(settings.aiService.prompt_input_max_length)}
                onChange={handleChange}
                placeholder="20000"
                min="1000"
                max="20000"
                className="w-full px-4 py-3 bg-white border-2 border-neo-black shadow-neo-sm font-mono font-bold focus:outline-none focus:shadow-[4px_4px_0px_0px_#29bf12] transition-shadow"
              />
              <p className="text-xs font-body mt-2 text-gray-600">
                <span className="font-bold">CHARS</span> — 數值越大允許處理更長的文本
              </p>
            </div>

            <div className="md:col-span-2">
              <label className="flex items-center gap-4 bg-neo-bg border-2 border-neo-black p-4 cursor-pointer hover:shadow-neo-sm transition-shadow">
                <input
                  type="checkbox"
                  name="aiService.ensure_chinese_output"
                  checked={settings.aiService?.ensure_chinese_output ?? true}
                  onChange={handleChange}
                  className="w-6 h-6 border-2 border-neo-black bg-white checked:bg-neo-primary appearance-none cursor-pointer"
                  style={{
                    backgroundImage: settings.aiService?.ensure_chinese_output ? 'url("data:image/svg+xml,%3Csvg xmlns=\'http://www.w3.org/2000/svg\' viewBox=\'0 0 24 24\' fill=\'none\' stroke=\'%23000\' stroke-width=\'3\'%3E%3Cpolyline points=\'20 6 9 17 4 12\'/%3E%3C/svg%3E")' : 'none',
                    backgroundSize: '100% 100%'
                  }}
                />
                <div>
                  <div className="font-heading font-black text-sm uppercase">AI 強制中文輸出</div>
                  <div className="text-xs text-gray-600 font-body">當啟用時，AI 回答將強制使用繁體中文</div>
                </div>
              </label>
            </div>
          </div>
        </div>

        {/* 資料庫設定 */}
        <div className="bg-white border-3 border-neo-black shadow-neo-lg p-6">
          <div className="flex items-center gap-3 mb-6 border-b-3 border-neo-black pb-4">
            <div className="bg-neo-primary p-2 border-2 border-neo-black">
              <svg className="w-6 h-6" fill="currentColor" viewBox="0 0 20 20">
                <path d="M3 12v3c0 1.657 3.134 3 7 3s7-1.343 7-3v-3c0 1.657-3.134 3-7 3s-7-1.343-7-3z"></path>
                <path d="M3 7v3c0 1.657 3.134 3 7 3s7-1.343 7-3V7c0 1.657-3.134 3-7 3S3 8.657 3 7z"></path>
                <path d="M17 5c0 1.657-3.134 3-7 3S3 6.657 3 5s3.134-3 7-3 7 1.343 7 3z"></path>
              </svg>
            </div>
            <h2 className="font-heading text-2xl md:text-3xl font-black uppercase">資料庫設定</h2>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
            <div>
              <label className="block font-heading font-black text-sm uppercase mb-2">MongoDB URI</label>
              <input
                name="database.uri"
                type="text"
                value={settings.database?.uri || ''}
                onChange={handleChange}
                placeholder="mongodb://localhost:27017"
                className="w-full px-4 py-3 bg-white border-2 border-neo-black shadow-neo-sm font-mono text-sm focus:outline-none focus:shadow-[4px_4px_0px_0px_#29bf12] transition-shadow"
              />
            </div>

            <div>
              <label className="block font-heading font-black text-sm uppercase mb-2">資料庫名稱</label>
              <input
                name="database.dbName"
                type="text"
                value={settings.database?.dbName || ''}
                onChange={handleChange}
                placeholder="sortify"
                className="w-full px-4 py-3 bg-white border-2 border-neo-black shadow-neo-sm font-mono text-sm focus:outline-none focus:shadow-[4px_4px_0px_0px_#29bf12] transition-shadow"
              />
            </div>
          </div>

          <div className="p-4 bg-neo-bg border-2 border-neo-black mb-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className={`w-3 h-3 border-2 border-neo-black ${isDBVerified ? 'bg-neo-primary' : isTestingDB ? 'bg-neo-warn animate-pulse' : 'bg-gray-300'}`}></div>
                <span className="font-heading font-black text-xs uppercase">CURRENT STATUS</span>
              </div>
              {isDBVerified && <span className="font-mono font-bold text-sm text-neo-primary">● ONLINE</span>}
              {isTestingDB && <span className="font-mono font-bold text-sm text-neo-warn">⟳ 測試中...</span>}
            </div>
            {dbTestMessage && (
              <p className={`text-xs font-body mt-3 pt-3 border-t-2 border-neo-black ${isDBVerified ? 'text-green-700' : 'text-red-700'}`}>
                {dbTestMessage}
              </p>
            )}
          </div>

          <p className="text-xs text-gray-600 font-body">
            💡 <span className="font-bold">自動測試：</span>輸入完成後會自動測試連線（延遲 1.5 秒）
          </p>
        </div>

        {/* 儲存按鈕 */}
        <div className="flex justify-end">
          <button
            type="submit"
            disabled={isSaving || (settings.database?.uri !== '' && settings.database?.dbName !== '' && !isDBVerified)}
            className="px-8 py-4 bg-neo-primary border-3 border-neo-black shadow-neo-lg font-heading font-black text-lg uppercase hover:bg-neo-hover hover:shadow-neo-xl hover:-translate-x-1 hover:-translate-y-1 active:shadow-none active:translate-x-2 active:translate-y-2 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isSaving ? '⟳ 儲存中...' : '💾 儲存設定'}
          </button>
        </div>
      </form>
    </div>
  );
};

export default SettingsPage;
