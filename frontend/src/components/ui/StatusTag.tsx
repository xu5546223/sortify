import React from 'react';
import { cn, statusTagStyles, type StatusType } from '../../styles/themeConfig';

interface StatusTagProps {
  status: StatusType;
  children: React.ReactNode;
  className?: string;
  icon?: React.ReactNode;
}

export const StatusTag: React.FC<StatusTagProps> = ({
  status,
  children,
  className = '',
  icon,
}) => {
  const tagClass = cn(
    statusTagStyles.base,
    statusTagStyles.variants[status],
    className
  );

  return (
    <span className={tagClass}>
      {icon && <span className="mr-1">{icon}</span>}
      {children}
    </span>
  );
}; 