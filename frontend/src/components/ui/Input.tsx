import React from 'react';
import { cn, inputStyles } from '../../styles/themeConfig';

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  hint?: string;
  leftIcon?: React.ReactNode;
  rightIcon?: React.ReactNode;
  fullWidth?: boolean;
}

export const Input: React.FC<InputProps> = ({
  label,
  error,
  hint,
  leftIcon,
  rightIcon,
  fullWidth = true,
  className = '',
  id,
  ...props
}) => {
  const inputId = id || `input-${Math.random().toString(36).substr(2, 9)}`;
  const hasError = !!error;

  const inputClass = cn(
    inputStyles.base,
    hasError ? inputStyles.error : '',
    leftIcon ? 'pl-10' : '',
    rightIcon ? 'pr-10' : '',
    !fullWidth ? 'w-auto' : '',
    className
  );

  return (
    <div className={cn('flex flex-col', !fullWidth && 'inline-flex')}>
      {label && (
        <label
          htmlFor={inputId}
          className="mb-2 text-sm font-medium text-surface-700"
        >
          {label}
        </label>
      )}
      
      <div className="relative">
        {leftIcon && (
          <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
            <div className="text-surface-400 w-5 h-5">
              {leftIcon}
            </div>
          </div>
        )}
        
        <input
          id={inputId}
          className={inputClass}
          {...props}
        />
        
        {rightIcon && (
          <div className="absolute inset-y-0 right-0 pr-3 flex items-center pointer-events-none">
            <div className="text-surface-400 w-5 h-5">
              {rightIcon}
            </div>
          </div>
        )}
      </div>
      
      {(error || hint) && (
        <div className="mt-1">
          {error && (
            <p className="text-sm text-error-600">
              {error}
            </p>
          )}
          {hint && !error && (
            <p className="text-sm text-surface-500">
              {hint}
            </p>
          )}
        </div>
      )}
    </div>
  );
}; 