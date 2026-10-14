const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

const URL_FILE = path.join(__dirname, 'active-tunnel.txt');
const PORT = process.env.PORT || 3000;

console.log(`[Cloudflare] Starting tunnel for http://localhost:${PORT}...`);

const child = spawn('cloudflared', ['tunnel', '--url', `http://localhost:${PORT}`], {
  shell: true,
  stdio: ['ignore', 'pipe', 'pipe']
});

let tunnelUrlFound = false;

function handleOutput(data) {
  const text = data.toString();
  // Cloudflare prints progress to stderr
  const match = text.match(/https:\/\/[a-zA-Z0-9-]+\.trycloudflare\.com/);
  if (match && !tunnelUrlFound) {
    tunnelUrlFound = true;
    const url = match[0];
    fs.writeFileSync(URL_FILE, url, 'utf-8');

    console.log('\n======================================================');
    console.log('CLOUDFLARE PUBLIC TUNNEL ONLINE');
    console.log('PUBLIC URL:          ', url);
    console.log('WEBHOOK CALLBACK URL:', `${url}/api/whatsapp/webhook`);
    console.log('======================================================\n');
  }
}

child.stdout.on('data', handleOutput);
child.stderr.on('data', handleOutput);

child.on('error', (err) => {
  console.error('[Cloudflare] Failed to start cloudflared:', err);
});

child.on('close', (code) => {
  console.log(`[Cloudflare] Tunnel exited with code ${code}`);
});

process.on('SIGINT', () => {
  child.kill();
  process.exit(0);
});

process.on('SIGTERM', () => {
  child.kill();
  process.exit(0);
});
