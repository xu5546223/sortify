import React from 'react';
import { cn, cardStyles } from '../../styles/themeConfig';

interface CardProps {
  children: React.ReactNode;
  className?: string;
  hover?: boolean;
  padding?: 'none' | 'sm' | 'md' | 'lg';
  title?: React.ReactNode;
  titleClassName?: string;
  headerActions?: React.ReactNode;
}

export const Card: React.FC<CardProps> = ({
  children,
  className = '',
  hover = true,
  padding = 'md',
  title,
  titleClassName = '',
  headerActions,
}) => {
  const paddingClasses = {
    none: '',
    sm: 'p-4',
    md: 'p-6',
    lg: 'p-8',
  };

  const cardClass = cn(
    cardStyles.base,
    hover ? 'hover:shadow-card-hover' : '',
    paddingClasses[padding],
    className
  );

  return (
    <div className={cardClass}>
      {title && (
        <div className="flex justify-between items-center mb-4">
          {typeof title === 'string' ? (
            <h2 className={cn('text-xl font-semibold text-surface-700', titleClassName)}>
              {title}
            </h2>
          ) : (
            <div className={cn('text-xl font-semibold text-surface-700', titleClassName)}>
              {title}
            </div>
          )}
          {headerActions && <div>{headerActions}</div>}
        </div>
      )}
      <div>{children}</div>
    </div>
  );
}; 