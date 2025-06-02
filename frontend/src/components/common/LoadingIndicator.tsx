import React from 'react';

const loadingStyles: React.CSSProperties = {
  display: 'flex',
  justifyContent: 'center',
  alignItems: 'center',
  height: '100vh',
  fontSize: '20px',
  fontFamily: 'Arial, sans-serif',
};

const LoadingIndicator: React.FC = () => <div style={loadingStyles}>載入中...</div>;

export default LoadingIndicator; 