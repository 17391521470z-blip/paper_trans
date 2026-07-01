import type { Config } from 'tailwindcss';

const config: Config = {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#eef7f6',
          100: '#d3ebe8',
          200: '#a6d6d0',
          300: '#73bbb3',
          400: '#4a9d95',
          500: '#2f8079',
          600: '#236762',
          700: '#1b5250',
          800: '#143f3e',
          900: '#0d2b2a',
          950: '#061615',
        },
        accent: {
          50: '#eef5fb',
          100: '#d9e8f5',
          200: '#b3d1eb',
          300: '#82b2dc',
          400: '#4d8cc8',
          500: '#2c6cb0',
          600: '#205590',
          700: '#1a4473',
          800: '#15355a',
          900: '#0f2643',
          950: '#081628',
        },
        ink: {
          50: '#f6f7f9',
          100: '#eceff3',
          200: '#d5dbe3',
          300: '#b1bcc9',
          400: '#8795a8',
          500: '#6a7a8e',
          600: '#556275',
          700: '#454e5e',
          800: '#3a424f',
          900: '#1f242c',
          950: '#13171d',
        },
      },
      fontFamily: {
        sans: [
          'Inter',
          '"Noto Sans SC"',
          '"PingFang SC"',
          '"Microsoft YaHei"',
          'system-ui',
          'sans-serif',
        ],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      boxShadow: {
        card: '0 1px 2px 0 rgb(15 38 67 / 0.04), 0 4px 12px -2px rgb(15 38 67 / 0.06)',
        focus: '0 0 0 3px rgb(47 128 121 / 0.25)',
      },
      borderRadius: {
        xl: '0.875rem',
        '2xl': '1.125rem',
      },
    },
  },
  plugins: [],
};

export default config;