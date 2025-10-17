import React from 'react';
import { NavLink } from 'react-router-dom';
import { navItems } from '../../config/navConfig'; // 導入 navItems

// Icon helper function (specific to Sidebar)
const icon = (className: string): JSX.Element => <i className={`fas ${className} fa-fw mr-2`}></i>;

const Sidebar = React.memo(() => {
  return (
    <div className="sidebar fixed top-0 left-0 h-full overflow-y-auto bg-surface-900 text-surface-100 w-64">
      <div className="logo p-5 text-center border-b border-surface-700 flex flex-col items-center justify-center">
        <img 
          src="/images/logo.png" 
          alt="Sortify Logo" 
          className="w-12 h-auto mb-3 object-contain"
        />
        <span className="text-lg font-semibold text-white">Sortify</span>
      </div>
      <nav>
        {navItems.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            className={({ isActive }) =>
              `block py-3 px-5 text-surface-300 hover:bg-surface-800 hover:text-white transition-colors duration-200 border-l-4 border-transparent ${
                isActive ? "bg-surface-800 text-white border-primary-500" : ""
              }`
            }
          >
            {icon(item.icon)}{item.name}
          </NavLink>
        ))}
      </nav>
    </div>
  );
});

export default Sidebar; 