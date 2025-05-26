import React from 'react';

interface SelectOption {
  value: string | number;
  label: string;
  disabled?: boolean;
}

interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  options: SelectOption[];
  labelClassName?: string;
  selectClassName?: string;
  containerClassName?: string;
}

const Select: React.FC<SelectProps> = ({
  label,
  id,
  options,
  className = '', // Main container class
  labelClassName = '',
  selectClassName = '',
  containerClassName = '',
  ...props
}) => {
  const defaultSelectClass = 'mt-1 block w-full pl-3 pr-10 py-2 text-base border-gray-300 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm rounded-md shadow-sm disabled:bg-surface-100 disabled:cursor-not-allowed';
  const defaultLabelClass = 'block text-sm font-medium text-gray-700';
  const defaultContainerClass = 'mb-4';

  return (
    <div className={`${defaultContainerClass} ${containerClassName} ${className}`}>
      {label && (
        <label htmlFor={id} className={`${defaultLabelClass} ${labelClassName}`}>
          {label}
        </label>
      )}
      <select
        id={id}
        className={`${defaultSelectClass} ${selectClassName}`}
        {...props}
      >
        {options.map((option) => (
          <option key={option.value} value={option.value} disabled={option.disabled}>
            {option.label}
          </option>
        ))}
      </select>
    </div>
  );
};

export default Select; 