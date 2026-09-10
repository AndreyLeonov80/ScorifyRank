import { readFile } from 'node:fs/promises';
import path from 'node:path';

const root = process.cwd();
const pkg = JSON.parse(await readFile(path.join(root, 'package.json'), 'utf8'));
const dockerfile = await readFile(path.join(root, 'Dockerfile'), 'utf8');
const indexHtml = await readFile(path.join(root, 'index.html'), 'utf8');
const tsconfig = await readFile(path.join(root, 'tsconfig.json'), 'utf8');
const viteConfig = await readFile(path.join(root, 'vite.config.ts'), 'utf8');
const mainTsx = await readFile(path.join(root, 'src', 'main.tsx'), 'utf8');
const errors = [];

if (!pkg.scripts?.dev?.includes('vite')) errors.push('package.json: dev script must run vite');
if (!pkg.scripts?.preview?.includes('vite preview')) errors.push('package.json: preview script must run vite preview');
if (!pkg.devDependencies?.vite) errors.push('package.json: vite devDependency is required');
if (!pkg.devDependencies?.typescript) errors.push('package.json: typescript devDependency is required');
if (!dockerfile.includes('npm run preview') && !dockerfile.includes('"npm", "run", "preview"')) {
  errors.push('Dockerfile runtime must start npm/Vite preview server');
}
if (dockerfile.includes('nginx:')) errors.push('Dockerfile should not use nginx runtime for React frontend');
if (!indexHtml.includes('/src/main.tsx')) errors.push('index.html must load the TSX Vite entrypoint');
if (!tsconfig.includes('"jsx"')) errors.push('tsconfig.json must configure TSX/JSX support');
if (!viteConfig.includes('defineConfig')) errors.push('vite.config.ts must use defineConfig');
if (!mainTsx.includes('loadClassicScript')) errors.push('src/main.tsx must bootstrap the classic app entrypoint');

if (errors.length) {
  console.error(JSON.stringify({ ok: false, errors }, null, 2));
  process.exit(1);
}

console.log(JSON.stringify({ ok: true }, null, 2));
