/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/**/*.{js,jsx,ts,tsx}",
  ],
  theme: {
    extend: {
      // ✅ Neo-Brutalism 色彩系統
      colors: {
        'neo-primary': '#29bf12',      // Bright Fern
        'neo-bg': '#f3f4f6',           // Engine Gray
        'neo-black': '#000000',         // Ink Black
        'neo-white': '#ffffff',         // Paper White
        'neo-active': '#08bdbd',        // Tropical Teal
        'neo-hover': '#abff4f',         // Green Yellow
        'neo-warning': '#ff9914',       // Deep Saffron
        'neo-critical': '#f21b3f',      // Lipstick Red
        'neo-warn': '#ff9914',           // Deep Saffron
        'neo-black': '#000000',          // Ink Black
        'neo-white': '#ffffff',          // Paper White
        'neo-bg': '#f3f4f6',             // Engine Gray
        
        // Legacy support (CSS variables)
        primary: 'var(--color-primary)',
        active: 'var(--color-active)',
        hover: 'var(--color-hover)',
        error: 'var(--color-error)',
        warn: 'var(--color-warn)',
        black: 'var(--color-black)',
        white: 'var(--color-white)',
        bg: 'var(--color-bg)',
      },
      fontFamily: {
        heading: 'var(--font-heading)',
        body: 'var(--font-body)',
        mono: 'var(--font-mono)',
        display: ['Space Grotesk', 'sans-serif'],
      },
      spacing: {
        section: 'var(--spacing-section)',
        card: 'var(--spacing-card)',
        component: 'var(--spacing-component)',
      },
      borderWidth: {
        '3': '3px',
        pc: 'var(--border-width-pc)',
        m: 'var(--border-width-m)',
      },
      borderRadius: {
        card: 'var(--radius-card)',
        button: 'var(--radius-button)',
        input: 'var(--radius-input)',
        modal: 'var(--radius-modal)',
      },
      boxShadow: {
        'neo-sm': '2px 2px 0px 0px #000000',
        'neo-md': '4px 4px 0px 0px #000000',
        'neo-lg': '6px 6px 0px 0px #000000',
        'neo-xl': '8px 8px 0px 0px #000000',
        'neo-hover': '7px 7px 0px 0px #000000',
        sm: 'var(--shadow-sm)',
        md: 'var(--shadow-md)',
        lg: 'var(--shadow-lg)',
        xl: 'var(--shadow-xl)',
      },
      transitionTimingFunction: {
        bounce: 'var(--trans-bounce)',
      },
      keyframes: {
        slideIn: {
          '0%': { transform: 'translateX(100%)', opacity: '0' },
          '100%': { transform: 'translateX(0)', opacity: '1' },
        },
      },
      animation: {
        slideIn: 'slideIn 0.3s ease-out',
      },
    },
  },
  plugins: [],
  darkMode: ['class', '[data-theme="dark"]'],
}