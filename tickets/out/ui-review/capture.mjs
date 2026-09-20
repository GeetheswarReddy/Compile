import { mkdirSync, writeFileSync } from 'node:fs';

const chromeEndpoint = process.env.CHROME_CDP_URL || 'http://127.0.0.1:9222';
const appOrigin = process.env.APP_ORIGIN || 'http://127.0.0.1:4173';
const apiOrigin = process.env.API_ORIGIN || 'http://127.0.0.1:4317/v1';
const outputDirectory = new URL('./', import.meta.url);

const targets = await fetch(`${chromeEndpoint}/json/list`).then((response) => response.json());
const target = targets.find((candidate) => candidate.type === 'page');
if (!target?.webSocketDebuggerUrl) throw new Error('No Chrome page target is available.');

const socket = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve, reject) => {
  socket.addEventListener('open', resolve, { once: true });
  socket.addEventListener('error', reject, { once: true });
});

let sequence = 0;
const pending = new Map();
socket.addEventListener('message', (event) => {
  const message = JSON.parse(event.data);
  if (!message.id || !pending.has(message.id)) return;
  const { resolve, reject, method } = pending.get(message.id);
  pending.delete(message.id);
  if (message.error) reject(new Error(`${method}: ${message.error.message}`));
  else resolve(message.result);
});

function command(method, params = {}) {
  const id = ++sequence;
  socket.send(JSON.stringify({ id, method, params }));
  return new Promise((resolve, reject) => pending.set(id, { resolve, reject, method }));
}

async function evaluate(expression) {
  const result = await command('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true });
  if (result.exceptionDetails) throw new Error(result.exceptionDetails.text);
  return result.result.value;
}

async function waitFor(expression, label) {
  for (let attempt = 0; attempt < 100; attempt += 1) {
    if (await evaluate(`Boolean(${expression})`)) return;
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  throw new Error(`Timed out waiting for ${label}.`);
}

async function navigate(path, readyExpression) {
  await command('Page.navigate', { url: `${appOrigin}${path}` });
  await waitFor(`document.readyState === 'complete' && (${readyExpression})`, path);
}

async function setViewport(width, height) {
  await command('Emulation.setDeviceMetricsOverride', {
    width,
    height,
    deviceScaleFactor: 1,
    mobile: width < 600,
    screenWidth: width,
    screenHeight: height,
  });
}

async function capture(name, width, height) {
  await setViewport(width, height);
  await new Promise((resolve) => setTimeout(resolve, 100));
  const metrics = await evaluate(`({
    innerWidth,
    innerHeight,
    documentScrollWidth: document.documentElement.scrollWidth,
    bodyScrollWidth: document.body.scrollWidth,
    documentScrollHeight: document.documentElement.scrollHeight,
    activeElement: document.activeElement?.getAttribute('aria-label') || document.activeElement?.textContent?.trim().slice(0, 80)
  })`);
  const screenshot = await command('Page.captureScreenshot', {
    format: 'png',
    captureBeyondViewport: false,
    fromSurface: true,
  });
  writeFileSync(new URL(name, outputDirectory), Buffer.from(screenshot.data, 'base64'));
  return { name, ...metrics };
}

async function clickButton(label) {
  const clicked = await evaluate(`(() => {
    const button = [...document.querySelectorAll('button')].find((candidate) => candidate.textContent.trim() === ${JSON.stringify(label)});
    if (!button) return false;
    button.click();
    return true;
  })()`);
  if (!clicked) throw new Error(`Button not found: ${label}`);
}

await command('Page.enable');
await command('Runtime.enable');
await command('Network.enable');
mkdirSync(outputDirectory, { recursive: true });

const review = { browser: 'Google Chrome 153.0.8010.52', captures: [], interaction: {} };
const viewports = [[1440, 900], [1280, 720], [390, 844]];

for (const [width, height] of viewports) {
  await setViewport(width, height);
  await navigate('/', `document.querySelector('.topic-selection')`);
  review.captures.push(await capture(`home-${width}x${height}.png`, width, height));
}

for (const [width, height] of viewports) {
  await setViewport(width, height);
  await navigate('/baseline', `document.querySelector('#baseline-code')`);
  review.captures.push(await capture(`baseline-${width}x${height}.png`, width, height));
}

for (let index = 0; index < 5; index += 1) {
  await fetch(`${apiOrigin}/baseline/submit`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Learner-Id': 't21-local-browser' },
    body: JSON.stringify({ questionId: `baseline-${index}`, code: 'def solve(values):\n    return values[0]' }),
  });
}

await setViewport(1440, 900);
await navigate('/practice/arrays', `document.querySelector('.cm-content') && document.querySelector('.demo-trace__item')`);
await evaluate(`document.querySelector('.cm-content').focus()`);
await command('Input.dispatchKeyEvent', { type: 'keyDown', key: 'a', code: 'KeyA', modifiers: 4, windowsVirtualKeyCode: 65 });
await command('Input.dispatchKeyEvent', { type: 'keyUp', key: 'a', code: 'KeyA', modifiers: 4, windowsVirtualKeyCode: 65 });
await command('Input.insertText', { text: 'def solve(values):\n    return values[0]' });
await waitFor(`document.querySelector('.cm-content')?.textContent.includes('return values[0]')`, 'CodeMirror edit');

await command('Network.setBlockedURLs', { urls: ['*://127.0.0.1:4317/v1/run-check'] });
await clickButton('Run & Check');
await waitFor(`document.querySelector('.practice-error')`, 'injected network error');
review.interaction.networkFailure = await evaluate(`({
  message: document.querySelector('.practice-error').textContent.trim(),
  codePreserved: document.querySelector('.cm-content').textContent.includes('return values[0]')
})`);

await command('Network.setBlockedURLs', { urls: [] });
await clickButton('Run & Check');
await waitFor(`document.querySelector('.practice-verdict.is-pass')`, 'passing retry verdict');
await clickButton('Reveal Nudge');
await waitFor(`document.body.textContent.includes('Read the value at index zero.')`, 'hint');
review.interaction.recovery = await evaluate(`({
  verdict: document.querySelector('.practice-verdict').textContent.trim(),
  trace: document.querySelector('.demo-trace__item').textContent.trim(),
  hint: document.querySelector('.hint-ladder').textContent.includes('Read the value at index zero.'),
  codePreserved: document.querySelector('.cm-content').textContent.includes('return values[0]')
})`);

for (const [width, height] of viewports) {
  review.captures.push(await capture(`practice-${width}x${height}.png`, width, height));
}

await command('Page.reload', { ignoreCache: true });
await waitFor(`document.readyState === 'complete' && document.querySelector('.cm-content')`, 'direct practice reload');
review.interaction.directPracticeReload = await evaluate(`location.pathname === '/practice/arrays'`);

writeFileSync(new URL('browser-review.json', outputDirectory), `${JSON.stringify(review, null, 2)}\n`);
socket.close();
console.log(JSON.stringify(review, null, 2));
