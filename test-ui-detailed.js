const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();

  // Capture all console messages
  const consoleMessages = [];
  page.on('console', msg => {
    consoleMessages.push({ type: msg.type(), text: msg.text() });
  });

  // Capture network errors
  const networkErrors = [];
  page.on('requestfailed', request => {
    networkErrors.push({ url: request.url(), error: request.failure().errorText });
  });

  console.log('=== Detailed UI Test ===\n');

  // Test Signals page
  console.log('Testing Signals page...');
  await page.goto('http://localhost:3000/signals', { waitUntil: 'networkidle', timeout: 15000 });
  await page.waitForTimeout(3000);

  // Get page content
  const bodyText = await page.textContent('body');
  console.log('\nPage text (first 500 chars):');
  console.log(bodyText.substring(0, 500));

  // Check for error elements
  const errorElements = await page.$$('text=/Error/i');
  console.log(`\nFound ${errorElements.length} elements with "Error" text`);

  for (const el of errorElements) {
    const text = await el.textContent();
    console.log(`  - "${text.substring(0, 100)}"`);
  }

  // Show console errors
  const errors = consoleMessages.filter(m => m.type === 'error');
  if (errors.length > 0) {
    console.log('\nConsole errors:');
    errors.forEach(e => console.log(`  - ${e.text}`));
  }

  // Show network errors
  if (networkErrors.length > 0) {
    console.log('\nNetwork errors:');
    networkErrors.forEach(e => console.log(`  - ${e.url}: ${e.error}`));
  }

  await page.screenshot({ path: '/tmp/signals-detailed.png', fullPage: true });
  console.log('\nScreenshot saved to /tmp/signals-detailed.png');

  await browser.close();
})();
