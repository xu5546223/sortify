import React from 'react';
import { Link } from 'react-router-dom';

const NotFoundPage: React.FC = () => {
  return (
    <div className="flex flex-col items-center justify-center h-full text-center">
      <i className="fas fa-exclamation-triangle text-6xl text-yellow-500 mb-4"></i>
      <h1 className="text-4xl font-bold text-gray-700 mb-2">404 - 頁面未找到</h1>
      <p className="text-gray-600 mb-6">抱歉，您要找的頁面不存在。</p>
      <Link to="/" className="btn btn-primary">
        返回儀表板
      </Link>
    </div>
  );
};

export default NotFoundPage; 