import React from 'react';

interface PageHeaderProps {
  title: string;
  className?: string;
}

const PageHeader: React.FC<PageHeaderProps> = ({ title, className = '' }) => {
  return (
    <h1 className={`text-3xl font-bold text-surface-900 mb-6 ${className}`}>
      {title}
    </h1>
  );
};

export default PageHeader; 