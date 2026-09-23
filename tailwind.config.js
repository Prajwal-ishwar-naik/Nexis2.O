/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./app.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        nexis: {
          bg: '#0d0d0d',
          sidebar: '#171717',
          canvas: '#212121',
          deck: '#2f2f2f',
          hover: '#262626',
          border: '#383838',
          accent: '#10a37f',
          muted: '#8e8e8e',
          bubble: '#2f2f2f',
        }
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'sans-serif'],
      }
    },
  },
  plugins: [],
}
