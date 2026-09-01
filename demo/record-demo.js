// Records the demo video of agent-context-ide-real.html with in-page captions.
// Playwright is not a repo dependency — point NODE_PATH at any node_modules
// that has it:  NODE_PATH=/path/to/node_modules node demo/record-demo.js
const { chromium } = require('playwright');
const path = require('path');

const HTML = 'file://' + path.resolve(__dirname, '..', 'agent-context-ide-real.html');
const OUT = path.join(__dirname, 'video');

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    recordVideo: { dir: OUT, size: { width: 1440, height: 900 } },
    colorScheme: 'dark',
  });
  const page = await ctx.newPage();
  await page.goto(HTML, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('.drill-row', { timeout: 60000 });

  // ---- overlay layer: cursor, caption bar, spotlight ring, callout bubble ----
  await page.evaluate(() => {
    const cur = document.createElement('div');
    cur.id = '__cur';
    cur.style.cssText = 'position:fixed;z-index:999999;width:20px;height:20px;border-radius:50%;' +
      'background:rgba(255,190,0,.9);border:2px solid #fff;pointer-events:none;left:0;top:0;' +
      'transition:transform .5s cubic-bezier(.2,.8,.2,1);transform:translate(720px,450px);' +
      'box-shadow:0 0 14px rgba(255,190,0,.9)';
    document.body.appendChild(cur);

    const cap = document.createElement('div');
    cap.id = '__cap';
    cap.style.cssText = 'position:fixed;z-index:999998;left:50%;bottom:34px;transform:translateX(-50%) translateY(20px);' +
      'max-width:880px;padding:14px 26px;border-radius:14px;background:rgba(10,14,20,.92);' +
      'border:1px solid rgba(255,190,0,.45);color:#f2f4f8;font:500 18px/1.45 -apple-system,Segoe UI,sans-serif;' +
      'text-align:center;opacity:0;transition:opacity .4s,transform .4s;pointer-events:none;' +
      'box-shadow:0 8px 30px rgba(0,0,0,.55)';
    document.body.appendChild(cap);

    const ring = document.createElement('div');
    ring.id = '__ring';
    ring.style.cssText = 'position:fixed;z-index:999997;border:3px solid rgba(255,190,0,.9);border-radius:12px;' +
      'pointer-events:none;opacity:0;transition:all .45s cubic-bezier(.2,.8,.2,1);' +
      'box-shadow:0 0 0 6000px rgba(0,0,0,.28),0 0 22px rgba(255,190,0,.7)';
    document.body.appendChild(ring);

    const tip = document.createElement('div');
    tip.id = '__tip';
    tip.style.cssText = 'position:fixed;z-index:999998;max-width:340px;padding:11px 16px;border-radius:10px;' +
      'background:rgba(255,190,0,.96);color:#141414;font:600 14px/1.4 -apple-system,Segoe UI,sans-serif;' +
      'opacity:0;transition:opacity .35s;pointer-events:none;box-shadow:0 6px 22px rgba(0,0,0,.5)';
    document.body.appendChild(tip);

    window.__cap = (t) => {
      if (!t) { cap.style.opacity = '0'; cap.style.transform = 'translateX(-50%) translateY(20px)'; return; }
      cap.textContent = t; cap.style.opacity = '1'; cap.style.transform = 'translateX(-50%) translateY(0)';
    };
    window.__ring = (r) => {
      if (!r) { ring.style.opacity = '0'; return; }
      ring.style.opacity = '1';
      ring.style.left = (r.x - 8) + 'px'; ring.style.top = (r.y - 8) + 'px';
      ring.style.width = (r.width + 16) + 'px'; ring.style.height = (r.height + 16) + 'px';
    };
    window.__tip = (t, x, y) => {
      if (!t) { tip.style.opacity = '0'; return; }
      tip.textContent = t; tip.style.left = x + 'px'; tip.style.top = y + 'px'; tip.style.opacity = '1';
    };
  });

  const sleep = (ms) => page.waitForTimeout(ms);
  const caption = async (t, hold = 0) => { await page.evaluate((t) => window.__cap(t), t); if (hold) await sleep(hold); };
  const ringOff = () => page.evaluate(() => window.__ring(null));
  const tipOff = () => page.evaluate(() => window.__tip(null));

  const spotlight = async (sel, i = 0, hold = 1800) => {
    const el = page.locator(sel).nth(i);
    await el.scrollIntoViewIfNeeded();
    await sleep(350);
    const b = await el.boundingBox();
    if (b) { await page.evaluate((r) => window.__ring(r), b); await sleep(hold); await ringOff(); await sleep(300); }
  };

  const callout = async (sel, i, text, hold = 2600) => {
    const el = page.locator(sel).nth(i);
    await el.scrollIntoViewIfNeeded();
    await sleep(350);
    const b = await el.boundingBox();
    if (!b) return;
    await page.evaluate((r) => window.__ring(r), b);
    const x = Math.min(b.x + b.width + 18, 1080);
    const y = Math.max(b.y - 8, 70);
    await page.evaluate(([t, x, y]) => window.__tip(t, x, y), [text, x, y]);
    await sleep(hold);
    await tipOff(); await ringOff(); await sleep(300);
  };

  const move = async (x, y) => {
    await page.evaluate(([x, y]) => {
      document.getElementById('__cur').style.transform = `translate(${x - 10}px,${y - 10}px)`;
    }, [x, y]);
    await sleep(650);
  };

  const clickSel = async (sel, i = 0, settle = 1600) => {
    const el = page.locator(sel).nth(i);
    await el.scrollIntoViewIfNeeded();
    await sleep(400);
    const b = await el.boundingBox();
    if (!b) return false;
    const x = b.x + Math.min(b.width / 2, 350), y = b.y + b.height / 2;
    await move(x, y);
    await page.mouse.click(x, y);
    await sleep(settle);
    return true;
  };

  const scrollBy = async (px, wait = 1400) => {
    await page.evaluate((px) => window.scrollBy({ top: px, behavior: 'smooth' }), px);
    await sleep(wait);
  };
  const scrollTop = async (wait = 900) => {
    await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'smooth' }));
    await sleep(wait);
  };

  // ---------------- the walkthrough ----------------

  // Title card
  await caption('Agent Context IDE — see what your AI coding assistant actually read, used, and ignored.', 4200);

  // 1. sessions
  await caption('It starts with your recent AI sessions. Pick any conversation to look inside it.', 1200);
  await scrollBy(220, 1300);
  await scrollTop();
  await sleep(1200);
  await clickSel('.drill-row', 0, 1800);

  // 2. turns
  await caption('The session is broken into turns — each thing you asked, and what the assistant did about it.', 1400);
  await scrollBy(320, 1500);
  await caption('Helpers the assistant sent off to work in the background show up right where they happened.', 800);
  await scrollTop();
  const agentRows = await page.locator('.agent-row[data-nav]').count();

  // 3. agent run
  if (agentRows > 0) {
    await clickSel('.agent-row[data-nav]', 0, 1800);
    await caption('Open a helper to see the exact instructions it was given — and what it reported back.', 1600);
    await scrollBy(280, 1800);
    await scrollTop(700);
    await page.keyboard.press('Escape');
    await sleep(1400);
  }

  // 4. into a turn -> files
  await caption('Step into a turn to see everything the assistant had in front of it at that moment.', 1200);
  await clickSel('.drill-row', 0, 1800);
  await caption('These are the instruction files and notes it was carrying. The ones it actually touched are on top.', 2200);
  await scrollBy(300, 1500);
  await scrollTop();

  // 5. into a file -> blocks + verdicts
  await clickSel('.drill-row', 0, 1800);
  await caption('Every section of your instructions gets an honest answer: was it followed, ignored, or never needed?', 1800);
  await callout('.block', 0, 'Click any section to see the proof behind its verdict.', 2400);
  await clickSel('.block', 0, 2000);
  await caption('The right side shows the receipts — the exact moments in the session that earned this verdict.', 1400);
  await scrollBy(380, 1800);
  await scrollTop();

  // 6. timeline
  await clickSel('button[data-view="timeline"]', 0, 1800);
  await caption('The timeline replays the whole session — every step, and where your money went.', 1600);
  await scrollBy(500, 1600);
  await scrollBy(500, 1600);
  await scrollTop(800);

  // 7. file activity
  await clickSel('button[data-view="files"]', 0, 1800);
  await caption('See which files cost you the most — instructions get re-sent with every message, and that adds up.', 1800);
  await scrollBy(450, 1800);
  await scrollTop(800);

  // 8. duplications
  await clickSel('button[data-view="duplications"]', 0, 1800);
  await caption('And it spots instructions you wrote twice — duplicate text you pay for on every single message.', 1800);
  await scrollBy(450, 1800);
  await scrollTop(700);

  // closing
  await clickSel('button[data-view="blocks"]', 0, 1200);
  await caption('One page, no install, works offline. Know what your assistant knows.', 3800);
  await caption(null);
  await sleep(600);

  const video = page.video();
  await ctx.close();
  console.log('VIDEO:', await video.path());
  await browser.close();
})();
