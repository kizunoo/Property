#!/usr/bin/env node
/**
 * db-check.js
 * Scans migration files for destructive SQL statements:
 * - DROP TABLE / COLUMN / POLICY / FUNCTION
 * - TRUNCATE
 * - DELETE without WHERE
 * - ALTER COLUMN TYPE / ALTER ... DROP
 * - REVOKE
 * - DISABLE ROW LEVEL SECURITY
 */

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const MIGRATIONS_DIR = path.join(__dirname, '..', 'supabase', 'migrations');

const DESTRUCTIVE_RULES = [
  { name: 'DROP TABLE', regex: /\bDROP\s+TABLE\b/i },
  { name: 'DROP COLUMN', regex: /\bDROP\s+COLUMN\b/i },
  { name: 'DROP POLICY', regex: /\bDROP\s+POLICY\b/i },
  { name: 'DROP FUNCTION', regex: /\bDROP\s+FUNCTION\b/i },
  { name: 'TRUNCATE', regex: /\bTRUNCATE\b/i },
  { name: 'DELETE without WHERE', regex: /\bDELETE\s+FROM\s+[^\n;]+(?!\bWHERE\b)/i },
  { name: 'ALTER ... DROP', regex: /\bALTER\s+TABLE\s+[^\n;]+\s+DROP\b/i },
  { name: 'ALTER COLUMN TYPE', regex: /\bALTER\s+TABLE\s+[^\n;]+\s+ALTER\s+COLUMN\s+[^\n;]+\s+TYPE\b/i },
  { name: 'REVOKE', regex: /\bREVOKE\b/i },
  { name: 'DISABLE RLS', regex: /\bDISABLE\s+ROW\s+LEVEL\s+SECURITY\b/i }
];

function getPendingMigrations() {
  try {
    const output = execSync('npx supabase migration list', { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'ignore'] });
    const pending = [];
    const lines = output.split('\n');
    for (const line of lines) {
      // Supabase migration list format shows local vs remote
      // A pending migration typically has empty/pending remote status
      const match = line.match(/^\s*(\d{14})\s+/);
      if (match && (line.includes('Pending') || !line.includes('Applied'))) {
        pending.push(match[1]);
      }
    }
    if (pending.length > 0) return pending;
  } catch {
    // If CLI not connected or error, scan all migrations
  }
  return null;
}

function scanFile(filePath) {
  const content = fs.readFileSync(filePath, 'utf-8');
  const lines = content.split('\n');
  const findings = [];

  lines.forEach((lineText, idx) => {
    const trimmed = lineText.trim();
    if (trimmed.startsWith('--')) return; // ignore comments

    for (const rule of DESTRUCTIVE_RULES) {
      if (rule.regex.test(trimmed)) {
        findings.push({
          line: idx + 1,
          rule: rule.name,
          text: trimmed
        });
      }
    }
  });

  return findings;
}

function main() {
  console.log('=== [db:check] Database Migration Safety Scanner ===\n');

  if (!fs.existsSync(MIGRATIONS_DIR)) {
    console.error(`Error: Migrations folder not found at ${MIGRATIONS_DIR}`);
    process.exit(1);
  }

  const allFiles = fs.readdirSync(MIGRATIONS_DIR).filter(f => f.endsWith('.sql')).sort();
  if (allFiles.length === 0) {
    console.log('No migration files found.');
    process.exit(0);
  }

  const pendingList = getPendingMigrations();
  const filesToScan = pendingList
    ? allFiles.filter(f => pendingList.some(p => f.startsWith(p)))
    : allFiles;

  console.log(`Checking ${filesToScan.length} migration file(s) for destructive statements...\n`);

  let totalFindings = 0;
  const flaggedFiles = [];

  for (const file of filesToScan) {
    const fullPath = path.join(MIGRATIONS_DIR, file);
    const findings = scanFile(fullPath);

    if (findings.length > 0) {
      totalFindings += findings.length;
      flaggedFiles.push(file);
      console.log(`[!] Migration: ${file}`);
      for (const item of findings) {
        console.log(`    Line ${item.line} [${item.rule}]: ${item.text.slice(0, 80)}`);
      }
      console.log('');
    } else {
      console.log(`[OK] ${file} (Clean - no destructive statements)`);
    }
  }

  console.log('----------------------------------------------------');
  if (totalFindings > 0) {
    console.log(`WARNING: ${totalFindings} destructive statement(s) detected across ${flaggedFiles.length} file(s).`);
    console.log(`To push with db:push, explicit approval is required:`);
    for (const f of flaggedFiles) {
      const version = f.split('_')[0];
      console.log(`  npm run db:push -- --approve ${version}`);
    }
    process.exit(0);
  } else {
    console.log('All scanned migrations are clean of destructive statements.');
    process.exit(0);
  }
}

main();
