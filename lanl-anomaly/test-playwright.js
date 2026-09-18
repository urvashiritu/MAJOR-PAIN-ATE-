const { chromium } = require('playwright');

(async () => {
    const browser = await chromium.launch();
    const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 } });
    const page = await ctx.newPage();

    // Collect console errors
    const errors = [];
    page.on('console', msg => { if (msg.type() === 'error') errors.push(msg.text()); });

    console.log('1. Hitting / — should auto-login as soc_admin');
    await page.goto('http://localhost:5000/', { waitUntil: 'networkidle' });
    console.log('   URL:', page.url());
    await page.screenshot({ path: '/tmp/ss-01-dashboard.png' });
    console.log('   screenshot: /tmp/ss-01-dashboard.png');

    // Wait for dashboard to populate
    await page.waitForTimeout(3000);
    await page.screenshot({ path: '/tmp/ss-02-dashboard-loaded.png' });
    console.log('2. Dashboard loaded');
    console.log('   screenshot: /tmp/ss-02-dashboard-loaded.png');

    // Navigate to Alerts
    console.log('3. Navigate to Alerts');
    await page.click('[data-page="alerts"]');
    await page.waitForTimeout(1500);
    await page.screenshot({ path: '/tmp/ss-03-alerts.png' });
    console.log('   screenshot: /tmp/ss-03-alerts.png');

    // Navigate to Users
    console.log('4. Navigate to Users');
    await page.click('[data-page="users"]');
    await page.waitForTimeout(1500);
    await page.screenshot({ path: '/tmp/ss-04-users.png' });
    console.log('   screenshot: /tmp/ss-04-users.png');

    // Navigate to Settings
    console.log('5. Navigate to Settings');
    await page.click('[data-page="settings"]');
    await page.waitForTimeout(1500);
    await page.screenshot({ path: '/tmp/ss-05-settings.png' });
    console.log('   screenshot: /tmp/ss-05-settings.png');

    // Theme toggle
    console.log('6. Toggle to light theme');
    await page.click('#theme-toggle');
    await page.waitForTimeout(500);
    await page.click('[data-page="dashboard"]');
    await page.waitForTimeout(1500);
    await page.screenshot({ path: '/tmp/ss-06-light-theme.png' });
    console.log('   screenshot: /tmp/ss-06-light-theme.png');

    // Dataset page
    console.log('7. Navigate to Dataset Analysis');
    await page.goto('http://localhost:5000/analyst/dataset', { waitUntil: 'networkidle' });
    await page.waitForTimeout(3000);
    await page.screenshot({ path: '/tmp/ss-07-dataset.png' });
    console.log('   screenshot: /tmp/ss-07-dataset.png');

    // Dev login as employee
    console.log('8. Dev login as U2899@DOM1');
    await page.goto('http://localhost:5000/employee', { waitUntil: 'networkidle' });
    await page.waitForTimeout(2000);
    await page.screenshot({ path: '/tmp/ss-08-employee.png' });
    console.log('   screenshot: /tmp/ss-08-employee.png');

    // Report errors
    if (errors.length > 0) {
        console.log('\n--- CONSOLE ERRORS ---');
        errors.forEach(e => console.log('  ', e));
    } else {
        console.log('\nNo console errors.');
    }

    await browser.close();
    console.log('\nDone.');
})();
