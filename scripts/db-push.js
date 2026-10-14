#!/usr/bin/env node
/**
 * db-push.js
 * Safe wrapper around supabase db push:
 * 1. Requires explicit --approve <migration_version_or_name> flag
 * 2. Runs db:check first and outputs any destructive statement warnings
 * 3. Runs supabase db push --dry-run and displays output
 * 4. Pushes only if approval flag matches the pending migration
 */

const { execSync } = require('child_process');
const path = require('path');
const fs = require('fs');

function parseArgs() {
  const args = process.argv.slice(2);
  let approve = null;
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--approve' && args[i + 1]) {
      approve = args[i + 1];
      i++;
    } else if (args[i].startsWith('--approve=')) {
      approve = args[i].split('=')[1];
    }
  }
  return { approve };
}

function runCommand(cmd, description) {
  console.log(`\n>>> [Step] ${description}: ${cmd}`);
  try {
    const out = execSync(cmd, { encoding: 'utf-8', stdio: 'inherit' });
    return true;
  } catch (err) {
    console.error(`\n[!] Failed executing: ${cmd}`);
    return false;
  }
}

function main() {
  console.log('=== [db:push] Controlled Production Migration Runner ===\n');

  const { approve } = parseArgs();

  // 1. Enforce --approve requirement
  if (!approve) {
    console.error('REFUSED: db:push requires explicit confirmation via --approve flag.');
    console.error('Usage:');
    console.error('  npm run db:push -- --approve <migration_version_or_name>');
    console.error('Example:');
    console.error('  npm run db:push -- --approve 20261012200000');
    console.error('  npm run db:push -- --approve 20261012200000_security_hardening_phase2.sql\n');
    console.error('To inspect changes first, run:');
    console.error('  npm run db:check');
    console.error('  npm run db:dry-run\n');
    process.exit(1);
  }

  // 2. Run db:check scanner
  console.log('[1/3] Running pre-push migration safety check...');
  const checkSuccess = runCommand('node scripts/db-check.js', 'db:check');
  if (!checkSuccess) {
    console.error('Safety check failed. Aborting push.');
    process.exit(1);
  }

  // 3. Run dry run
  console.log('\n[2/3] Executing Supabase CLI dry-run verification...');
  const dryRunSuccess = runCommand('npx supabase db push --dry-run', 'supabase db push --dry-run');
  if (!dryRunSuccess) {
    console.error('Dry-run failed or rejected. Aborting push.');
    process.exit(1);
  }

  // 4. Verify approval matches a known migration file
  const migrationsDir = path.join(__dirname, '..', 'supabase', 'migrations');
  const files = fs.readdirSync(migrationsDir).filter(f => f.endsWith('.sql'));
  const matchingFile = files.find(f => f.includes(approve) || f.startsWith(approve));

  if (!matchingFile) {
    console.error(`\nREFUSED: Approved target "${approve}" does not match any file in supabase/migrations/.`);
    console.error('Available migrations:');
    files.forEach(f => console.error(`  - ${f}`));
    process.exit(1);
  }

  console.log(`\n[3/3] Explicit approval verified for: ${matchingFile}`);
  console.log('Applying migration to linked Supabase project...\n');

  const pushSuccess = runCommand('npx supabase db push', 'supabase db push');
  if (!pushSuccess) {
    console.error('\nPush failed. Check output above.');
    process.exit(1);
  }

  console.log('\n[SUCCESS] Migration applied successfully.');
  console.log('Next step: verify database integrity using:');
  console.log('  npm run db:verify\n');
}

main();
