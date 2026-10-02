// Runs Pyodide + claudon off the main thread so the page stays responsive during analysis.
const PYODIDE_URL = 'https://cdn.jsdelivr.net/pyodide/v0.26.1/full/';
const PYODIDE_SRI = 'sha384-Zt+txBUVind9SDPtCx7HTNK8jiZiFKX/Cm3Ml1tEnAmGKO/QSRn1VqM+Vr45Cbrj';
const ROOT = '/home/pyodide/transcripts';

async function text(url, init) {
  const resp = await fetch(url, init);
  if (!resp.ok) throw new Error(`${url}: HTTP ${resp.status}`);
  return resp.text();
}

async function bytes(url) {
  const resp = await fetch(url);
  if (!resp.ok) throw new Error(`${url}: HTTP ${resp.status}`);
  return new Uint8Array(await resp.arrayBuffer());
}

const ready = (async () => {
  // claudon.pyz is the zipapp built by scripts/build_zipapp.py (deploy-pages.yml puts it next to this file;
  // for local use build it into dist/ and serve the repo root)
  let bundle;
  try {
    bundle = await bytes('claudon.pyz');
  } catch (err) {
    bundle = await bytes('../dist/claudon.pyz');
  }
  // importScripts() can't check SRI, so fetch with integrity and run the verified source from a blob.
  // This pins pyodide.js only; the .wasm/stdlib files it loads come unverified from the same version dir.
  const loader = await text(PYODIDE_URL + 'pyodide.js', { integrity: PYODIDE_SRI });
  importScripts(URL.createObjectURL(new Blob([loader], { type: 'text/javascript' })));
  const py = await loadPyodide({ indexURL: PYODIDE_URL });
  py.FS.writeFile('/home/pyodide/claudon.pyz', bundle);
  py.runPython("import sys; sys.path.insert(0, '/home/pyodide/claudon.pyz')");   // zipimport
  return py;
})();

ready.then(() => postMessage({ type: 'ready' }), err => postMessage({ type: 'fatal', message: err.message }));

// files: [{ path, data: ArrayBuffer, mtime }] with paths already sanitised under ROOT by the page
onmessage = async ({ data: { files } }) => {
  try {
    const py = await ready;
    py.runPython(`import os, shutil; shutil.rmtree('${ROOT}', ignore_errors=True); os.makedirs('${ROOT}')`);
    for (const { path, data, mtime } of files) {
      py.FS.mkdirTree(path.slice(0, path.lastIndexOf('/')));
      py.FS.writeFile(path, new Uint8Array(data));
      py.FS.utime(path, mtime, mtime);     // claudon breaks session-order ties by mtime
    }
    postMessage({ type: 'status', text: 'Analyzing on this computer (WebAssembly)...' });
    const html = py.runPython(`
import claudon
data = claudon.build('${ROOT}')
data['root'] = 'files opened in your browser'   # not the worker's internal path
claudon.render_html(data) if data['tasks'] else ''
`);
    postMessage({ type: 'result', html });
  } catch (err) {
    postMessage({ type: 'error', message: err.message });
  }
};
