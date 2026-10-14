// Writes www/ota-ver.js: the version (hash) of the screens built into the APK, worked out exactly as the server's
// /app/ota.json does (cprb_alerts.py app_ota), so the app doesn't fetch the same screens again. Run before a build.
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const www = path.join(__dirname, '..', 'www');
const h = crypto.createHash('sha256');
for (const f of ['app.js', 'style.css', 'index.html']) {
  h.update(Buffer.concat([Buffer.from(f), Buffer.from([0]), fs.readFileSync(path.join(www, f)), Buffer.from([0])]));
}
const ver = h.digest('hex').slice(0, 12);
fs.writeFileSync(path.join(www, 'ota-ver.js'), `window.__bundledVer = '${ver}';\n`);
console.log('ota-ver.js: ' + ver);
