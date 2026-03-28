import express from 'express';
import { realpathSync } from 'fs';
import { resolve } from 'path';
import { fileURLToPath } from 'url';
import { randomBytes } from 'crypto';
import { isLoopbackAddress } from './utils/network.js';
import { envConfig } from './config.js';
import { getObservatoryData } from './controllers/observatory.js';
import { getAnatomyData } from './controllers/anatomy.js';
import { getTimelineData } from './controllers/timeline.js';

const __dirname = fileURLToPath(new URL('.', import.meta.url));
const VIEWS_DIR = resolve(__dirname, '../views');

const app = express();

// ---- View engine ----------------------------------------------------------
app.set('views', VIEWS_DIR);
app.set('view engine', 'ejs');

// ---- Security headers -----------------------------------------------------
app.use((_req, res, next) => {
  const nonce = randomBytes(16).toString('base64');
  res.locals['cspNonce'] = nonce;
  res.setHeader(
    'Content-Security-Policy',
    [
      `default-src 'self'`,
      `script-src 'self' 'nonce-${nonce}' https://cdn.jsdelivr.net`,
      `style-src 'self' 'unsafe-inline'`,
      `img-src 'self' data:`,
      `connect-src 'none'`,
    ].join('; ')
  );
  res.setHeader('X-Content-Type-Options', 'nosniff');
  res.setHeader('X-Frame-Options', 'DENY');
  res.setHeader('Referrer-Policy', 'no-referrer');
  next();
});

// ---- Routes ---------------------------------------------------------------

app.get('/', (_req, res) => {
  res.render('index', { title: 'Leitstand' });
});

app.get('/observatory', async (_req, res) => {
  try {
    const data = await getObservatoryData();
    res.render('observatory', data);
  } catch (error) {
    if (!res.headersSent) {
      console.error('[Observatory] Error:', error);
      res.status(500).send('Error loading observatory data');
    }
  }
});

// Anatomy View – Phase 1: Structural overview of the Heimgewebe organism
app.get('/anatomy', async (_req, res) => {
  try {
    const data = await getAnatomyData();
    res.render('anatomy', data);
  } catch (error) {
    if (!res.headersSent) {
      console.error('[Anatomy] Error:', error);
      const msg = error instanceof Error ? error.message : String(error);
      if (msg.includes('Strict')) {
        res.status(503).send('Service Unavailable');
      } else {
        res.status(500).send('Error loading anatomy data');
      }
    }
  }
});

// Timeline View – Phase 3: Temporal event chronology
app.get('/timeline', async (_req, res) => {
  try {
    const rawHours = Number(_req.query['hours']);
    const hoursBack = Number.isFinite(rawHours) && rawHours > 0
      ? Math.min(rawHours, 168) // cap at 7 days
      : 48;
    const data = await getTimelineData(hoursBack);
    res.render('timeline', data);
  } catch (error) {
    if (!res.headersSent) {
      console.error('[Timeline] Error:', error);
      res.status(500).send('Error loading timeline data');
    }
  }
});

app.get('/ops', (_req, res) => {
  res.render('ops', { title: 'Ops' });
});

app.get('/intent', (_req, res) => {
  res.render('intent', { title: 'Intent' });
});

// ---- Health ---------------------------------------------------------------
app.get('/health', (_req, res) => {
  res.json({ ok: true });
});

// ---- 404 ------------------------------------------------------------------
app.use((_req, res) => {
  res.status(404).send('Not found');
});

// ---- Start ----------------------------------------------------------------
let isDirectRun = false;
try {
  const mainPath    = realpathSync(fileURLToPath(import.meta.url));
  const argv1Path   = realpathSync(process.argv[1] ?? '');
  isDirectRun = mainPath === argv1Path;
} catch {
  isDirectRun = false;
}

if (isDirectRun) {
  const { port, host } = envConfig;
  app.listen(port, host, () => {
    console.log(`Leitstand listening on http://${host}:${port}`);
    if (!isLoopbackAddress(host)) {
      console.warn('[Leitstand] WARNING: Not bound to loopback — use a reverse proxy or firewall rules.');
    }
  });
}

export { app };
