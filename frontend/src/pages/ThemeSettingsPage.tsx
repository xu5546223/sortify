import React from 'react';
import { useTheme } from '../contexts/ThemeContext';

const ThemeSettingsPage: React.FC = () => {
  const { theme, setTheme, actualTheme } = useTheme();

  return (
    <div className="min-h-screen bg-bg p-6 md:p-10 transition-colors duration-300">
      {/* Header */}
      <header className="mb-10">
        <h2 className="font-heading text-4xl font-black mb-2 uppercase">
          THEME SETTINGS
        </h2>
        <p className="text-[var(--color-text-sub)] font-medium">
          選擇您的工作台外觀模式
        </p>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        
        {/* 1. Appearance Mode */}
        <div className="lg:col-span-2 neo-card">
          <h3 className="font-heading text-xl font-black border-b-[2px] border-[var(--color-border)] pb-2 mb-6 uppercase">
            Appearance Mode
          </h3>
          
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {/* Light Mode */}
            <div
              onClick={() => setTheme('light')}
              className={`neo-card p-4 cursor-pointer transition-all border-[3px] ${
                theme === 'light'
                  ? 'border-primary relative'
                  : 'border-transparent hover:border-hover'
              }`}
            >
              {theme === 'light' && (
                <div className="absolute -top-2 -right-2 w-6 h-6 bg-primary border-2 border-black rounded-full flex items-center justify-center font-black text-xs">
                  ✓
                </div>
              )}
              <div className="h-24 bg-bg border-2 border-black mb-3 flex items-center justify-center relative overflow-hidden">
                {/* Light UI Mockup */}
                <div className="absolute top-2 left-2 w-16 h-full bg-white border-r-2 border-black"></div>
                <div className="absolute top-4 right-2 w-12 h-4 bg-white border-2 border-black"></div>
                <div className="absolute top-10 right-2 w-8 h-8 bg-primary rounded-full border-2 border-black"></div>
              </div>
              <div className="text-center font-bold">Light (Default)</div>
            </div>

            {/* Dark Mode */}
            <div
              onClick={() => setTheme('dark')}
              className={`neo-card p-4 cursor-pointer transition-all border-[3px] ${
                theme === 'dark'
                  ? 'border-primary relative'
                  : 'border-transparent hover:border-hover'
              }`}
            >
              {theme === 'dark' && (
                <div className="absolute -top-2 -right-2 w-6 h-6 bg-primary border-2 border-black rounded-full flex items-center justify-center font-black text-xs">
                  ✓
                </div>
              )}
              <div className="h-24 bg-[#121212] border-2 border-white mb-3 flex items-center justify-center relative overflow-hidden">
                {/* Dark UI Mockup */}
                <div className="absolute top-2 left-2 w-16 h-full bg-black border-r-2 border-white"></div>
                <div className="absolute top-4 right-2 w-12 h-4 bg-black border-2 border-white"></div>
                <div className="absolute top-10 right-2 w-8 h-8 bg-primary rounded-full border-2 border-white"></div>
              </div>
              <div className="text-center font-bold">Dark (Cyberpunk)</div>
            </div>

            {/* System Sync */}
            <div
              onClick={() => setTheme('system')}
              className={`neo-card p-4 cursor-pointer transition-all border-[3px] ${
                theme === 'system'
                  ? 'border-primary relative'
                  : 'border-transparent hover:border-hover'
              }`}
            >
              {theme === 'system' && (
                <div className="absolute -top-2 -right-2 w-6 h-6 bg-primary border-2 border-black rounded-full flex items-center justify-center font-black text-xs">
                  ✓
                </div>
              )}
              <div className="h-24 bg-gradient-to-r from-bg to-[#121212] border-2 border-[var(--color-border)] mb-3 flex items-center justify-center">
                <i className="fas fa-desktop text-3xl"></i>
              </div>
              <div className="text-center font-bold">System Sync</div>
            </div>
          </div>
        </div>

        {/* 2. Current Theme Info */}
        <div className="neo-card">
          <h3 className="font-heading text-xl font-black border-b-[2px] border-[var(--color-border)] pb-2 mb-6 uppercase">
            Theme Status
          </h3>
          
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-black mb-2 text-[var(--color-text-sub)]">
                USER SELECTION
              </label>
              <div className="p-3 border-2 border-[var(--color-border)] bg-bg font-mono text-lg">
                {theme.toUpperCase()}
              </div>
            </div>

            <div>
              <label className="block text-sm font-black mb-2 text-[var(--color-text-sub)]">
                ACTUAL THEME
              </label>
              <div className="p-3 border-2 border-[var(--color-border)] bg-bg font-mono text-lg">
                {actualTheme.toUpperCase()}
              </div>
            </div>

            <div>
              <label className="block text-sm font-black mb-2 text-[var(--color-text-sub)]">
                SYSTEM PREFERENCE
              </label>
              <div className="p-3 border-2 border-[var(--color-border)] bg-bg font-mono text-lg">
                {window.matchMedia('(prefers-color-scheme: dark)').matches ? 'DARK' : 'LIGHT'}
              </div>
            </div>
          </div>
        </div>

        {/* 4. Live Preview */}
        <div className="lg:col-span-3">
          <h3 className="font-heading text-xl font-black mb-4 uppercase flex items-center gap-2">
            <i className="fas fa-eye"></i> Live Component Preview
          </h3>
          
          <div className="neo-card p-0 overflow-hidden">
            <table className="w-full text-left font-bold text-sm">
              <thead className="bg-bg border-b-[3px] border-[var(--color-border)] uppercase">
                <tr>
                  <th className="p-4">File Name</th>
                  <th className="p-4">Status</th>
                  <th className="p-4 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y-2 divide-[var(--color-border)]">
                <tr>
                  <td className="p-4 flex items-center gap-3">
                    <i className="fas fa-file-pdf text-2xl text-error"></i>
                    <span>Annual_Report_2024.pdf</span>
                  </td>
                  <td className="p-4">
                    <span className="bg-active text-white px-2 py-1 border-2 border-[var(--color-border)] text-xs shadow-[2px_2px_0px_0px_var(--shadow-color)]">
                      ANALYZED
                    </span>
                  </td>
                  <td className="p-4 text-right">
                    <button className="w-8 h-8 border-2 border-[var(--color-border)] flex items-center justify-center hover:bg-hover transition-colors">
                      <i className="fas fa-download"></i>
                    </button>
                  </td>
                </tr>
                <tr>
                  <td className="p-4 flex items-center gap-3">
                    <i className="fas fa-image text-2xl text-hover"></i>
                    <span>banner_design_v2.png</span>
                  </td>
                  <td className="p-4">
                    <span className="bg-hover text-black px-2 py-1 border-2 border-[var(--color-border)] text-xs shadow-[2px_2px_0px_0px_var(--shadow-color)]">
                      PENDING
                    </span>
                  </td>
                  <td className="p-4 text-right">
                    <button className="w-8 h-8 border-2 border-[var(--color-border)] flex items-center justify-center hover:bg-hover transition-colors">
                      <i className="fas fa-download"></i>
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

      </div>
    </div>
  );
};

export default ThemeSettingsPage;
