import React from 'react';

interface MessageBoxPCProps {
  message: string;
  type: string;
  visible: boolean;
}

const MessageBoxPC = React.memo<MessageBoxPCProps>(({ message, type, visible }) => {
  if (!visible) return null;

  // Neo-Brutalism 樣式配置
  let bgColor = 'bg-neo-hover'; // info 預設
  let textColor = 'text-neo-black';
  let icon = 'ℹ️';
  
  if (type === 'error') {
    bgColor = 'bg-neo-error';
    textColor = 'text-neo-white';
    icon = '❌';
  } else if (type === 'success') {
    bgColor = 'bg-neo-primary';
    textColor = 'text-neo-black';
    icon = '✅';
  }

  return (
    <div 
      className={`message-box-pc fixed bottom-8 right-8 ${bgColor} ${textColor} border-3 border-neo-black py-4 px-6 shadow-[8px_8px_0px_0px_#000] z-[9999] animate-slideIn font-display font-bold text-base flex items-center gap-3 min-w-[300px] max-w-[500px]`}
      role="alert"
    >
      <span className="text-2xl flex-shrink-0">{icon}</span>
      <span className="flex-1 break-words">{message}</span>
    </div>
  );
});

export default MessageBoxPC;