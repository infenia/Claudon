#!/usr/bin/env node

const { spawn } = require('child_process');
const path = require('path');

const scriptPath = path.join(__dirname, '..', 'claudon.py');
const args = process.argv.slice(2);

function runPython(pythonCmd) {
  return new Promise((resolve, reject) => {
    const proc = spawn(pythonCmd, [scriptPath, ...args], { stdio: 'inherit' });
    proc.on('close', code => {
      if (code === 0) {
        resolve();
      } else {
        const err = new Error(`Process exited with code ${code}`);
        err.status = code;
        reject(err);
      }
    });
    proc.on('error', err => {
      reject(err);
    });
  });
}

async function main() {
  const pythonCmds = ['python3', 'python', 'py'];
  let lastErr = null;

  for (const cmd of pythonCmds) {
    try {
      await runPython(cmd);
      return;
    } catch (err) {
      if (err.code === 'ENOENT') {
        lastErr = err;
        continue;
      }
      process.exit(err.status || 1);
    }
  }

  console.error('Error: Python 3 standard library is required to run Claudon.');
  console.error('Please ensure python3 or python is installed and available in your PATH.');
  process.exit(1);
}

main();
