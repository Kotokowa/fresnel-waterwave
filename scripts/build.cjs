const fs = require('node:fs');
const path = require('node:path');
const root = path.join(__dirname, '..');
const source = path.join(root, 'waterwave');
const destination = path.join(root, 'dist', 'water-wave');

fs.cpSync(path.join(root, 'src', 'water-wave'), destination, { recursive: true });
const modules = path.join(destination, 'python');
fs.mkdirSync(modules, { recursive: true });
for (const name of ['__init__.py', 'core.py', 'session.py', 'measurement.py', 'analysis.py', 'fields.py', 'colors.py', 'colormaps.json']) {
  fs.copyFileSync(path.join(source, name), path.join(modules, name));
}
fs.copyFileSync(path.join(source, 'LICENSE-FCD.txt'), path.join(destination, 'LICENSE-FCD.txt'));
fs.writeFileSync(path.join(destination, '.nojekyll'), '');
console.log('Built the Water Wave Lab in dist/water-wave/.');
