import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import { shouldValidateProductionApi, validateProductionApiUrl } from './src/productionApiConfig';

export default defineConfig(({ command, mode }) => {
  const env = loadEnv(mode, '.', '');
  if (shouldValidateProductionApi(command, mode)) {
    validateProductionApiUrl(env.VITE_API_BASE_URL);
  }
  return {
    plugins: [react()],
    server: { host: 'localhost', port: 5173 },
  };
});
