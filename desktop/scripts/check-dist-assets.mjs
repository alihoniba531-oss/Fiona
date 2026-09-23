import { readFileSync, readdirSync, statSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { isAbsolute, join, relative, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const desktopDir = fileURLToPath(new URL('..', import.meta.url));
const distDir = join(desktopDir, 'dist');
const indexPath = join(distDir, 'index.html');

let html;
try {
  html = readFileSync(indexPath, 'utf8');
} catch (error) {
  console.error(`FAIL dist/index.html: ${error.message}`);
  process.exit(1);
}

// Match tags without treating a > inside a quoted attribute as the tag's end.
const tagPattern = /<([A-Za-z][A-Za-z0-9:-]*)\b((?:"[^"]*"|'[^']*'|[^'">])*)>/g;
const attributePattern = /([^\s=/>]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+)))?/g;

function attributesOf(source) {
  const attributes = new Map();
  for (const match of source.matchAll(attributePattern)) {
    attributes.set(match[1].toLowerCase(), match[2] ?? match[3] ?? match[4]);
  }
  return attributes;
}

function isLocalRelative(value) {
  return value !== '' && !/^(?:\/\/|#|\?|[a-z][a-z\d+.-]*:)/i.test(value);
}

const failures = [];
const references = [];
const uncommentedHtml = html.replace(/<!--[\s\S]*?-->/g, '');

for (const tag of uncommentedHtml.matchAll(tagPattern)) {
  const attributes = attributesOf(tag[2]);
  for (const [name, value] of attributes) {
    if (/^on[a-z]+$/.test(name)) {
      failures.push(`inline event attribute ${name} is blocked by CSP`);
    }
    if (name === 'style') {
      failures.push('inline style attribute is blocked by CSP');
    }
    if (name === 'src' || name === 'href') {
      const address = value?.trim();
      if (!address) {
        failures.push(`<${tag[1]}> has a missing or empty ${name} attribute`);
      } else if (isLocalRelative(address)) {
        references.push(address);
      }
    }
  }
}

const scriptPattern = /<script\b((?:"[^"]*"|'[^']*'|[^'">])*)>([\s\S]*?)<\/script\s*>/gi;
for (const script of uncommentedHtml.matchAll(scriptPattern)) {
  if (!attributesOf(script[1]).has('src') && script[2].trim() !== '') {
    failures.push('inline script is blocked by CSP');
  }
}
if (/<style\b/i.test(uncommentedHtml)) {
  failures.push('<style> block is blocked by CSP');
}

const gitRootResult = spawnSync('git', ['rev-parse', '--show-toplevel'], {
  cwd: desktopDir,
  encoding: 'utf8',
});
const gitRoot = gitRootResult.status === 0 ? gitRootResult.stdout.trim() : null;
if (!gitRoot) {
  console.log('NOTE: Git unavailable or outside a repository; skipping ignore checks.');
}

for (const address of references) {
  const pathPart = address.split(/[?#]/, 1)[0];
  let assetPath;
  try {
    const localPath = pathPart.startsWith('/') ? pathPart.slice(1) : pathPart;
    assetPath = resolve(distDir, decodeURIComponent(localPath));
  } catch (error) {
    failures.push(`${address}: invalid URL path (${error.message})`);
    continue;
  }

  const relativeToDist = relative(distDir, assetPath);
  if (relativeToDist === '..' || relativeToDist.startsWith(`..${sep}`) || isAbsolute(relativeToDist)) {
    failures.push(`${address}: resolves outside desktop/dist`);
    continue;
  }

  // Check every path component: statSync alone accepts wrong case on some systems.
  let parentDir = distDir;
  let caseMismatch = false;
  for (const expectedName of relativeToDist.split(sep).filter(Boolean)) {
    let actualNames;
    try {
      actualNames = readdirSync(parentDir);
    } catch {
      break; // The existence check below reports missing paths and non-directories.
    }
    if (!actualNames.includes(expectedName)) {
      const actualName = actualNames.find((name) => name.toLowerCase() === expectedName.toLowerCase());
      if (actualName) {
        failures.push(`${address}: filename case mismatch (expected "${expectedName}", actual "${actualName}")`);
        caseMismatch = true;
      }
      break;
    }
    parentDir = join(parentDir, expectedName);
  }
  if (caseMismatch) {
    continue;
  }

  try {
    if (!statSync(assetPath).isFile()) {
      failures.push(`${address}: not a file`);
      continue;
    }
  } catch (error) {
    failures.push(`${address}: file does not exist (${error.code ?? error.message})`);
    continue;
  }

  if (gitRoot) {
    const repoPath = relative(gitRoot, assetPath).split(sep).join('/');
    const check = spawnSync('git', ['check-ignore', '-q', '--', repoPath], {
      cwd: gitRoot,
      encoding: 'utf8',
    });
    if (check.status === 0) {
      failures.push(`${address}: ignored by Git (${repoPath})`);
      continue;
    }
    if (check.status !== 1) {
      failures.push(`${address}: Git ignore check failed (${check.error?.message ?? check.stderr.trim()})`);
      continue;
    }

    const tracked = spawnSync('git', ['ls-files', '--error-unmatch', '--', repoPath], {
      cwd: gitRoot,
      encoding: 'utf8',
    });
    if (tracked.status === 1) {
      console.warn(`WARN ${address}: not tracked by Git (commit it before pushing)`);
    } else if (tracked.status !== 0) {
      failures.push(`${address}: Git tracking check failed (${tracked.error?.message ?? tracked.stderr.trim()})`);
      continue;
    }
  }

  console.log(`PASS ${address}: exists${gitRoot ? ', not ignored by Git' : ''}`);
}

for (const failure of failures) {
  console.error(`FAIL ${failure}`);
}
if (failures.length > 0) {
  process.exitCode = 1;
} else {
  console.log('Desktop dist assets check passed.');
}
