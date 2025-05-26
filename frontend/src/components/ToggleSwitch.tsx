import React from 'react';

interface ToggleSwitchProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'type'> {
  label?: string;
  labelPosition?: 'left' | 'right';
  containerClassName?: string;
  labelClassName?: string;
  switchClassName?: string; // For the div that acts as the switch background
  knobClassName?: string; // For the div that acts as the switch knob
}

const ToggleSwitch: React.FC<ToggleSwitchProps> = ({
  id,
  name,
  checked,
  onChange,
  disabled,
  label,
  labelPosition = 'right',
  containerClassName = '',
  labelClassName = '',
  switchClassName = '',
  knobClassName = '',
}) => {
  const defaultContainerClass = 'flex items-center';
  const defaultLabelClass = 'text-sm font-medium text-surface-700';
  const defaultSwitchClass = 'w-11 h-6 bg-gray-600 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-teal-800 rounded-full peer peer-checked:bg-teal-600';
  const defaultKnobClass = "after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-surface-50 after:border-surface-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:after:translate-x-full peer-checked:after:border-surface-50";

  const switchId = id || name;

  const switchElement = (
    <label htmlFor={switchId} className="relative inline-flex items-center cursor-pointer">
      <input 
        type="checkbox" 
        id={switchId} 
        name={name} 
        checked={checked} 
        onChange={onChange} 
        disabled={disabled}
        className="sr-only peer" 
      />
      <div className={`${defaultSwitchClass} ${switchClassName} ${defaultKnobClass} ${knobClassName}`}></div>
    </label>
  );

  const labelTextElement = label ? (
    <span className={`${defaultLabelClass} ${labelPosition === 'right' ? 'ml-3' : 'mr-3'} ${labelClassName}`}>
      {label}
    </span>
  ) : null;

  return (
    <div className={`${defaultContainerClass} ${containerClassName}`}>
      {labelPosition === 'left' && labelTextElement}
      {switchElement}
      {labelPosition === 'right' && labelTextElement}
    </div>
  );
};

export default ToggleSwitch; 