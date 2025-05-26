import React from 'react';

interface CheckboxProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  labelPosition?: 'left' | 'right';
  containerClassName?: string;
  labelClassName?: string;
  checkboxClassName?: string;
}

const Checkbox: React.FC<CheckboxProps> = ({
  label,
  id,
  labelPosition = 'right',
  containerClassName = '',
  labelClassName = '',
  checkboxClassName = '',
  className = '', // Kept for direct checkbox styling if needed, but checkboxClassName is preferred
  ...props
}) => {
  const defaultCheckboxClass = 'h-4 w-4 text-indigo-600 border-gray-300 rounded focus:ring-indigo-500';
  const defaultLabelClass = 'ml-2 text-sm text-gray-700';
  const defaultContainerClass = 'flex items-center';

  const checkboxElement = (
    <input
      type="checkbox"
      id={id}
      className={`${defaultCheckboxClass} ${checkboxClassName} ${className}`}
      {...props}
    />
  );

  const labelElement = label ? (
    <label htmlFor={id} className={`${defaultLabelClass} ${labelClassName}`}>
      {label}
    </label>
  ) : null;

  return (
    <div className={`${defaultContainerClass} ${containerClassName}`}>
      {labelPosition === 'left' && labelElement}
      {checkboxElement}
      {labelPosition === 'right' && labelElement}
    </div>
  );
};

export default Checkbox; 