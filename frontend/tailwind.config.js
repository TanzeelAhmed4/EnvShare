import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = dirname(fileURLToPath(import.meta.url));

/** @type {import('tailwindcss').Config} */
export default {
  content: [resolve(root, 'index.html'), resolve(root, 'src/**/*.{js,ts,jsx,tsx}')],
  theme: { extend: {} },
  plugins: [],
};
