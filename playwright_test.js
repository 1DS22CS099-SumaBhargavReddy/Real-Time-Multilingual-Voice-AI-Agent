const { chromium } = require('playwright');
const path = require('path');

async function run() {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  
  // Set viewport for a clean desktop view
  await page.setViewportSize({ width: 1400, height: 900 });
  
  console.log("Navigating to http://localhost:5173/ ...");
  await page.goto('http://localhost:5173/');
  
  // Wait for the dashboard container to load
  await page.waitForSelector('.dashboard-container');
  console.log("Dashboard loaded!");
  
  // Take a screenshot and save it to the artifact directory
  const screenshotPath = 'C:\\Users\\K.Bhargav Reddy\\.gemini\\antigravity\\brain\\270db337-c8ef-4f3b-873c-3222b6323f30\\dashboard_preview.png';
  await page.screenshot({ path: screenshotPath });
  console.log(`Screenshot saved to ${screenshotPath}`);
  
  // Select patient Srinivasan (Tamil preference)
  console.log("Clicking patient Srinivasan (Tamil)...");
  await page.click('text=Srinivasan');
  await page.waitForTimeout(500); // Allow state sync
  
  // Start the call
  console.log("Clicking Start Call...");
  await page.click('text=Start Call');
  await page.waitForTimeout(2000); // Let WebSocket connect and greet
  
  // Take screenshot during active call
  const callScreenshotPath = 'C:\\Users\\K.Bhargav Reddy\\.gemini\\antigravity\\brain\\270db337-c8ef-4f3b-873c-3222b6323f30\\active_call_preview.png';
  await page.screenshot({ path: callScreenshotPath });
  console.log(`Call screenshot saved to ${callScreenshotPath}`);
  
  // Type message to schedule
  console.log("Typing message...");
  await page.fill('input[placeholder="Type message here to simulate speaking..."]', 'naalai doctor karthik raja appointment 11:00 AM');
  await page.press('input[placeholder="Type message here to simulate speaking..."]', 'Enter');
  
  await page.waitForTimeout(3000); // Let reasoning and tool book the appointment
  
  // Take screenshot after booking
  const bookedScreenshotPath = 'C:\\Users\\K.Bhargav Reddy\\.gemini\\antigravity\\brain\\270db337-c8ef-4f3b-873c-3222b6323f30\\booked_appointment_preview.png';
  await page.screenshot({ path: bookedScreenshotPath });
  console.log(`Booked appointment screenshot saved to ${bookedScreenshotPath}`);
  
  // End Call
  console.log("Ending Call...");
  await page.click('text=End Call');
  
  await browser.close();
  console.log("Automation finished successfully!");
}

run().catch(err => {
  console.error("Playwright test failed:", err);
  process.exit(1);
});
