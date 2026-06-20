import type { Config } from 'tailwindcss';

const config: Config = {
  darkMode: 'class',
  content: [
    './app/**/*.{ts,tsx}',
    './components/**/*.{ts,tsx}',
    './lib/**/*.{ts,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        // PUG brand palette
        pug: {
          navy: {
            50: '#eef1f9',
            100: '#d6dcef',
            200: '#aab5d8',
            300: '#7e8ec1',
            400: '#5267aa',
            500: '#2a3669',
            600: '#1a234a',
            700: '#121a33',
            800: '#0b1020',
            900: '#070a16',
          },
          gold: {
            50: '#fbf6e8',
            100: '#f4e8c0',
            200: '#ead493',
            300: '#dfbf65',
            400: '#d4aa3a',
            500: '#c9a14a',
            600: '#a8842f',
            700: '#8a6b22',
            800: '#6b5219',
            900: '#4a3811',
          },
        },
      },
      fontFamily: {
        sans: ['Inter', 'Segoe UI', 'Roboto', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Consolas', 'monospace'],
      },
      boxShadow: {
        soft: '0 6px 24px rgba(15, 23, 42, 0.08)',
        gold: '0 0 0 4px rgba(201, 161, 74, 0.25)',
      },
      keyframes: {
        shake: {
          '0%, 100%': { transform: 'translateX(0)' },
          '10%, 30%, 50%, 70%, 90%': { transform: 'translateX(-5px)' },
          '20%, 40%, 60%, 80%': { transform: 'translateX(5px)' },
        },
        'fade-in': {
          from: { opacity: '0', transform: 'translateY(10px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
      },
      animation: {
        shake: 'shake 0.5s ease-in-out',
        'fade-in': 'fade-in 0.3s ease-out',
      },
    },
  },
  plugins: [],
};

export default config;
