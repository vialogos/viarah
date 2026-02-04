#!/usr/bin/env node
'use strict';

const fs = require('node:fs');
const path = require('node:path');

function usage(exitCode) {
  const out = exitCode === 0 ? process.stdout : process.stderr;
  out.write(
    [
      'Render deterministic HTML to PDF via system Chromium + Puppeteer.',
      '',
      'Usage:',
      '  render.js --html <in.html> --out-pdf <out.pdf> --out-report-json <out.json> --assets-dir <dir> --chrome <exe>',
      '',
      'Offline policy:',
      '  Blocks ALL non-local requests (e.g. http/https). Any blocked request => render fails.',
      '',
    ].join('\n') + '\n',
  );
  process.exit(exitCode);
}

function parseArgs(argv) {
  const args = {};
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--help' || a === '-h') usage(0);
    if (!a.startsWith('--')) throw new Error(`unknown arg: ${a}`);
    const k = a.slice(2);
    const v = argv[i + 1];
    if (!v || v.startsWith('--')) throw new Error(`missing value for --${k}`);
    args[k] = v;
    i++;
  }
  return args;
}

function truthyEnv(name) {
  return ['1', 'true', 'yes', 'on'].includes(String(process.env[name] || '').toLowerCase());
}

function sanitizeUrlForLogs(raw) {
  const s = String(raw || '').trim();
  if (!s) return '';
  try {
    const u = new URL(s);
    u.search = '';
    u.hash = '';
    return u.toString().slice(0, 2000);
  } catch (_) {
    return s.split('#')[0].split('?')[0].slice(0, 2000);
  }
}

function loadPuppeteer() {
  try {
    // eslint-disable-next-line import/no-dynamic-require, global-require
    return require('puppeteer-core');
  } catch (_) {
    try {
      // eslint-disable-next-line import/no-dynamic-require, global-require
      return require('puppeteer');
    } catch (e) {
      process.stderr.write(
        [
          'ERROR: missing puppeteer dependency (recommended: puppeteer-core).',
          'Expected to resolve `puppeteer-core` from reports/pdf_renderer/node_modules.',
        ].join('\n') + '\n',
      );
      process.exit(2);
    }
  }
}

function safeWriteJson(pathname, obj) {
  fs.mkdirSync(path.dirname(path.resolve(pathname)), { recursive: true });
  fs.writeFileSync(pathname, JSON.stringify(obj, null, 2) + '\n', 'utf8');
}

async function main() {
  let args;
  try {
    args = parseArgs(process.argv.slice(2));
  } catch (e) {
    process.stderr.write(`ERROR: ${e.message}\n`);
    usage(2);
  }

  const htmlPath = args.html;
  const outPdf = args['out-pdf'];
  const outReportJson = args['out-report-json'];
  const assetsDir = args['assets-dir'] || '';
  const chrome = args.chrome;

  if (!htmlPath || !outPdf || !outReportJson || !assetsDir || !chrome) usage(2);

  const report = {
    tool: 'viarah_pdf_renderer',
    version: 1,
    ok: false,
    blocked_requests: [],
    missing_images: [],
    error_code: '',
    error_message: '',
  };

  const puppeteer = loadPuppeteer();
  const html = fs.readFileSync(htmlPath, 'utf8');

  const wantNoSandbox = truthyEnv('VIA_RAH_PDF_NO_SANDBOX') || truthyEnv('VL_MD2PDF_NO_SANDBOX');
  const launchArgs = ['--disable-dev-shm-usage'];
  if (wantNoSandbox) launchArgs.unshift('--no-sandbox', '--disable-setuid-sandbox');

  let browser;
  try {
    browser = await puppeteer.launch({
      executablePath: chrome,
      headless: true,
      args: launchArgs,
    });
  } catch (e) {
    report.error_code = 'launch_failed';
    report.error_message = String(e && e.message ? e.message : e);
    safeWriteJson(outReportJson, report);
    process.exit(2);
  }

  const blocked = new Set();

  try {
    const page = await browser.newPage();
    await page.setJavaScriptEnabled(false);

    await page.setRequestInterception(true);
    page.on('request', (req) => {
      const url = req.url();
      if (/^(file:|data:|about:|blob:|chrome:|chrome-error:)/i.test(url)) req.continue();
      else {
        blocked.add(sanitizeUrlForLogs(url));
        req.abort();
      }
    });

    await page.setContent(html, { waitUntil: 'load' });
    await page.emulateMediaType('print');

    report.blocked_requests = Array.from(blocked).filter(Boolean).slice(0, 200);

    report.missing_images = await page.evaluate(() => {
      const imgs = Array.from(document.images);
      return imgs
        .filter((img) => !(img.complete && img.naturalWidth > 0))
        .map((img) => String(img.currentSrc || img.src || '').trim())
        .filter(Boolean)
        .slice(0, 200);
    });
    report.missing_images = report.missing_images.map(sanitizeUrlForLogs);

    if (report.blocked_requests.length > 0) {
      report.error_code = 'blocked_remote_requests';
      report.error_message = 'blocked remote requests during render';
    } else if (report.missing_images.length > 0) {
      report.error_code = 'missing_images';
      report.error_message = 'one or more images failed to load';
    } else {
      fs.mkdirSync(path.dirname(path.resolve(outPdf)), { recursive: true });
      await page.pdf({
        path: outPdf,
        format: 'A4',
        printBackground: true,
        preferCSSPageSize: true,
      });
      report.ok = true;
    }
  } catch (e) {
    report.error_code = 'render_failed';
    report.error_message = String(e && e.message ? e.message : e);
  } finally {
    await browser.close();
  }

  safeWriteJson(outReportJson, report);
  process.exit(report.ok ? 0 : 2);
}

main().catch((e) => {
  process.stderr.write(`ERROR: render failed: ${e && e.stack ? e.stack : String(e)}\n`);
  process.exit(2);
});

