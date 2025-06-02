import React from 'react';

interface MessageBoxPCProps {
  message: string;
  type: string;
  visible: boolean;
}

const MessageBoxPC = React.memo<MessageBoxPCProps>(({ message, type, visible }) => {
  if (!visible) return null;

  let bgColor = 'bg-surface-800'; // Default for info
  if (type === 'error') bgColor = 'bg-red-600';
  else if (type === 'success') bgColor = 'bg-green-600';

  return (
    <div className={`message-box-pc fixed bottom-5 right-5 text-white py-3 px-6 rounded-md shadow-lg z-50 ${bgColor}`}>
      {message}
    </div>
  );
});

export default MessageBoxPC; 