/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: { 950: '#101412', 900: '#18201c', 700: '#33423a', 500: '#607267' },
        paper: { 50: '#faf9f5', 100: '#f3f1e9', 200: '#e6e1d5' },
        trail: { 50: '#effaf5', 100: '#d7f1e4', 500: '#268a5a', 600: '#1e7049', 700: '#185c3d' },
        amber: { 50: '#fff8e8', 200: '#f6dfad', 700: '#8a5a14' },
        evidence: {
          support: '#268a5a',
          contradict: '#b54a44',
          uncertain: '#a66d1f',
          context: '#4776a5',
        },
      },
      fontFamily: {
        sans: ['ui-sans-serif', 'system-ui', '-apple-system', 'BlinkMacSystemFont', 'sans-serif'],
        serif: ['Iowan Old Style', 'Palatino Linotype', 'Georgia', 'serif'],
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'Monaco', 'Consolas', 'monospace'],
      },
      boxShadow: { panel: '0 1px 2px rgba(16,20,18,.04), 0 14px 40px rgba(16,20,18,.05)' },
    },
  },
  plugins: [],
};
