import { existsSync, readdirSync, statSync, readFileSync } from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const required = [
  ['scss/_tokens.scss'],
  ['scss/_mixins.scss'],
  ['scss/_layout.scss'],
  ['scss/pages/index.scss', 'css/pages/index.css'],
  ['scss/pages/import.scss', 'css/pages/import.css'],
  ['scss/pages/grid.scss', 'css/pages/grid.css'],
];

const errors = [];
for (const pair of required) {
  const [source, output] = pair;
  const sourcePath = path.join(root, source);
  try {
    statSync(sourcePath);
  } catch {
    errors.push(`${source} missing`);
    continue;
  }
  if (output) {
    const outputPath = path.join(root, output);
    try {
      const sourceInfo = statSync(sourcePath);
      const outputInfo = statSync(outputPath);
      if (outputInfo.mtimeMs + 1000 < sourceInfo.mtimeMs) {
        errors.push(`${output} is older than ${source}; run npm run scss:build`);
      }
    } catch {
      errors.push(`${output} missing`);
    }
  }
}

const pkg = readFileSync(path.join(root, 'package.json'), 'utf8');
for (const marker of ['"sass"', '"scss:build"', '"scss:watch"', '"audit:scss"']) {
  if (!pkg.includes(marker)) errors.push(`package.json missing ${marker}`);
}

const gridScss = readFileSync(path.join(root, 'scss/pages/grid.scss'), 'utf8');
for (const marker of ['grid-template-rows: auto auto auto 1fr', 'align-content: start', 'align-self: start']) {
  if (!gridScss.includes(marker)) errors.push(`grid.scss missing ${marker}`);
}

const indexMainScss = readFileSync(path.join(root, 'scss/pages/index.scss'), 'utf8');
const indexPartialsDir = path.join(root, 'scss/pages/index');
const indexPartialScss = existsSync(indexPartialsDir)
  ? readdirSync(indexPartialsDir)
    .filter((file) => file.endsWith('.scss'))
    .sort()
    .map((file) => readFileSync(path.join(indexPartialsDir, file), 'utf8'))
    .join('\n')
  : '';
const indexScss = `${indexMainScss}\n${indexPartialScss}`;
for (const marker of ['@use "index/chat"', '@use "index/messages"', '@use "index/analysis"', '@use "index/forms"', '@use "index/popups"']) {
  if (!indexMainScss.includes(marker)) errors.push(`index.scss missing partial import ${marker}`);
}
for (const marker of ['#chatBox{ scroll-behavior:auto', '.repeat-request-card', '.repeat-request-textarea', 'min-height:360px']) {
  if (!indexScss.includes(marker)) errors.push(`index.scss missing ${marker}`);
}

if (errors.length) {
  console.error(JSON.stringify({ ok: false, errors }, null, 2));
  process.exit(1);
}

console.log(JSON.stringify({ ok: true }, null, 2));
