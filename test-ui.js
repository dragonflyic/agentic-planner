const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();

  console.log('=== Testing Frontend UI ===\n');

  // Test Dashboard
  console.log('1. Testing Dashboard (http://localhost:3000)...');
  try {
    await page.goto('http://localhost:3000', { waitUntil: 'networkidle', timeout: 10000 });
    const title = await page.title();
    console.log(`   Title: ${title}`);

    // Check for errors in console
    page.on('console', msg => {
      if (msg.type() === 'error') {
        console.log(`   Console Error: ${msg.text()}`);
      }
    });

    // Wait a bit for any JS errors
    await page.waitForTimeout(2000);

    // Take screenshot
    await page.screenshot({ path: '/tmp/dashboard.png', fullPage: true });
    console.log('   Screenshot saved to /tmp/dashboard.png');

    // Check page content
    const bodyText = await page.textContent('body');
    if (bodyText.includes('Loading')) {
      console.log('   WARNING: Page shows "Loading..." - may be stuck');
    }
    if (bodyText.includes('Error') || bodyText.includes('error')) {
      console.log('   WARNING: Page contains error text');
    }
  } catch (e) {
    console.log(`   ERROR: ${e.message}`);
  }

  // Test Signals page
  console.log('\n2. Testing Signals page (http://localhost:3000/signals)...');
  try {
    await page.goto('http://localhost:3000/signals', { waitUntil: 'networkidle', timeout: 10000 });
    await page.waitForTimeout(2000);
    await page.screenshot({ path: '/tmp/signals.png', fullPage: true });
    console.log('   Screenshot saved to /tmp/signals.png');

    const bodyText = await page.textContent('body');
    if (bodyText.includes('Loading')) {
      console.log('   WARNING: Page shows "Loading..."');
    }
    if (bodyText.includes('Error')) {
      console.log('   WARNING: Page contains "Error"');
      // Try to get error details
      const errorEl = await page.$('.text-red-700, .text-red-400, [class*="error"]');
      if (errorEl) {
        const errorText = await errorEl.textContent();
        console.log(`   Error content: ${errorText}`);
      }
    }
  } catch (e) {
    console.log(`   ERROR: ${e.message}`);
  }

  // Test Attempts page
  console.log('\n3. Testing Attempts page (http://localhost:3000/attempts)...');
  try {
    await page.goto('http://localhost:3000/attempts', { waitUntil: 'networkidle', timeout: 10000 });
    await page.waitForTimeout(2000);
    await page.screenshot({ path: '/tmp/attempts.png', fullPage: true });
    console.log('   Screenshot saved to /tmp/attempts.png');

    const bodyText = await page.textContent('body');
    if (bodyText.includes('Loading')) {
      console.log('   WARNING: Page shows "Loading..."');
    }
    if (bodyText.includes('Error')) {
      console.log('   WARNING: Page contains "Error"');
    }
  } catch (e) {
    console.log(`   ERROR: ${e.message}`);
  }

  // Test API directly from browser
  console.log('\n4. Testing API proxy (http://localhost:3000/api/signals/)...');
  try {
    const response = await page.goto('http://localhost:3000/api/signals/', { waitUntil: 'networkidle', timeout: 10000 });
    const status = response.status();
    console.log(`   API Response status: ${status}`);
    if (status !== 200) {
      const body = await page.textContent('body');
      console.log(`   Response body: ${body.substring(0, 200)}`);
    }
  } catch (e) {
    console.log(`   ERROR: ${e.message}`);
  }

  await browser.close();
  console.log('\n=== Test Complete ===');
})();
