/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Industrial / control-room palette.
        panel: {
          DEFAULT: '#111827',
          light: '#1f2937',
          border: '#374151',
        },
        brand: {
          DEFAULT: '#38bdf8',
          dark: '#0284c7',
        },
      },
      fontFamily: {
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
    },
  },
  plugins: [],
}
