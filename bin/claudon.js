#!/usr/bin/env node

const { spawn, spawnSync } = require('child_process');
const path = require('path');

const scriptPath = path.join(__dirname, '..', 'claudon.py');
const args = process.argv.slice(2);

// Probe instead of trusting the name: on Windows `python3` is often the Microsoft Store stub,
// which exists on PATH but isn't Python; `python` may also be Python 2.
function findPython() {
  for (const cmd of ['python3', 'python', 'py']) {
    const probe = spawnSync(cmd, ['-c', 'import sys; sys.exit(sys.version_info < (3, 11))'], { stdio: 'ignore' });
    if (probe.status === 0) return cmd;
  }
  return null;
}

const python = findPython();
if (!python) {
  console.error('Error: Claudon needs Python 3.11+ (standard library only).');
  console.error('Install it and make sure python3, python or py is on your PATH.');
  process.exit(1);
}

const child = spawn(python, [scriptPath, ...args], { stdio: 'inherit' });
child.on('error', err => {
  console.error(`Error: failed to run ${python}: ${err.message}`);
  process.exit(1);
});
child.on('exit', (code, signal) => {
  if (signal) process.kill(process.pid, signal);
  else process.exit(code);
});
