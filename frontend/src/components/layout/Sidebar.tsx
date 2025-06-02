import React from 'react';
import { NavLink } from 'react-router-dom';
import { navItems } from '../../config/navConfig'; // 導入 navItems

// Icon helper function (specific to Sidebar)
const icon = (className: string): JSX.Element => <i className={`fas ${className} fa-fw mr-2`}></i>;

const Sidebar = React.memo(() => {
  return (
    <div className="sidebar fixed top-0 left-0 h-full overflow-y-auto bg-surface-900 text-surface-100 w-64">
      <div className="logo p-5 text-center text-xl font-semibold border-b border-surface-700">
        {icon("fa-cogs")}AI 文件助理
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