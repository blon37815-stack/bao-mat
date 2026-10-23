const {defineConfig} = require('@playwright/test');
const path = require('node:path');
const root = path.resolve(__dirname, '../..');
const python = process.env.BAO_TEST_PYTHON || path.join(root, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
module.exports = defineConfig({
  testDir: __dirname,
  testMatch: '*.spec.cjs',
  workers: 1,
  // Hosted Windows Chromium can spend over 20s in page/context startup even
  // when loopback assets return within milliseconds. Assertions keep their
  // own short bounds; this only gives setup and teardown enough total time.
  timeout: process.platform === 'win32' ? 60000 : 20000,
  use: {
    baseURL: 'http://127.0.0.1:8989',
    headless: true,
    launchOptions: {executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH || undefined},
    trace: 'retain-on-failure'
  },
  webServer: {
    command: '"' + python + '" tests/ui/server.py',
    cwd: root,
    env: {PORT: '8989'},
    url: 'http://127.0.0.1:8989/api/session',
    reuseExistingServer: false,
    timeout: 20000
  }
});
