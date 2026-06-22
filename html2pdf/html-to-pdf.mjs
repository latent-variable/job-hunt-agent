import puppeteer from "puppeteer-core";
import { resolve } from "path";
import { existsSync, readFileSync } from "fs";

const PAGE_W = "816px";
const PAGE_H = "1056px";

const CHROME_PATH = process.env.CHROME_PATH || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";

const inputFile = process.argv[2];
if (!inputFile) {
  console.error("Usage: node html-to-pdf.mjs <input.html> [output.pdf]");
  process.exit(1);
}

const inputPath = resolve(inputFile);
if (!existsSync(inputPath)) {
  console.error(`File not found: ${inputPath}`);
  process.exit(1);
}

const outputPath = process.argv[3]
  ? resolve(process.argv[3])
  : inputPath.replace(/\.html$/, ".pdf");

console.log(`Converting: ${inputPath}`);
console.log(`Output:     ${outputPath}`);
console.log(`Chrome:     ${CHROME_PATH}`);

try {
  const browser = await puppeteer.launch({
    executablePath: CHROME_PATH,
    headless: "new",
    args: ["--no-sandbox", "--disable-setuid-sandbox", "--disable-gpu", "--disable-dev-shm-usage", "--disable-software-rasterizer"],
  });

  const page = await browser.newPage();
  await page.goto(`file://${inputPath}`, { waitUntil: "networkidle0" });
  await page.evaluate(() => document.fonts.ready);

  await page.pdf({
    path: outputPath,
    width: PAGE_W,
    height: PAGE_H,
    printBackground: true,
    margin: { top: "0", right: "0", bottom: "0", left: "0" },
    scale: 1.0,
    preferCSSPageSize: true,
  });

  const screenshotPath = outputPath.replace(/\.pdf$/, ".png");
  await page.setViewport({ width: 816, height: 1056, deviceScaleFactor: 2 });
  await page.evaluate(() => {
    document.body.style.margin = "0";
    document.body.style.padding = "0";
    document.body.style.background = "#0a0a0a";
  });
  await page.screenshot({ path: screenshotPath, clip: { x: 0, y: 0, width: 816, height: 1056 } });

  // Check PDF page count by counting page markers in the raw PDF
  const pdfBuffer = readFileSync(outputPath);
  const pdfText = pdfBuffer.toString("latin1");
  const pageCount = (pdfText.match(/\/Type\s*\/Page(?!s)/g) || []).length;

  // Also check content height vs page height
  const contentHeight = await page.evaluate(() => {
    const container = document.querySelector(".resume-container, .cover-container");
    return container ? container.scrollHeight : document.body.scrollHeight;
  });

  await browser.close();

  console.log(`✓ PDF: ${outputPath}`);
  console.log(`✓ Screenshot: ${screenshotPath}`);
  console.log(`✓ PDF pages: ${pageCount}`);
  console.log(`✓ Content height: ${contentHeight}px / 1056px page`);

  if (pageCount > 1) {
    console.error(`\n⚠️  WARNING: PDF is ${pageCount} pages! Content overflows by ~${contentHeight - 1056}px. Trim content to fit one page.`);
    process.exit(2);
  }
} catch (error) {
  console.error("Failed to launch Chrome:", error.message);
  console.log("Try: brew install --cask google-chrome or set CHROME_PATH=/path/to/chrome");
  process.exit(1);
}
