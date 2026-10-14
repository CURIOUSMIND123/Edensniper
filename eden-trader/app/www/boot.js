/*
 * boot.js: loads the app's screens either from an over-the-air (OTA) copy the server sent, or from the copy built into
 * the APK. app.js, style.css and index.html can then change with no new APK: the app checks the server
 * (/app/ota.json) when it opens and when it comes back to the front, and takes a new version straight away.
 *
 * Safety (a bad update can never stop the app):
 *  - no OTA copy                          -> the built-in files;
 *  - an OTA copy that fails while loading -> thrown away, back to the built-in files (and that version is not taken
 *    again);
 *  - an OTA copy that loads but never finishes starting (app.js calls window.__otaBooted() once it has) -> thrown away
 *    after 15 seconds or at the next start.
 * Not part of the OTA copy: this file and the native notification service (those need a new APK; the app offers it).
 */
(function () {
  'use strict';
  var BUILD = 5;                                      // this APK's build number (versionCode)
  window.__apkBuild = BUILD;

  function get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
  function set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* storage full or blocked */ } }
  function del(k) { try { localStorage.removeItem(k); } catch (e) { /* ignore */ } }

  var ota = null;
  try { ota = JSON.parse(get('ota') || 'null'); } catch (e) { ota = null; }
  var use = false;
  if (ota && ota.files && ota.files['app.js'] && ota.ver && (ota.min || 0) <= BUILD) {
    if (ota.status === 'active') {
      use = true;
    } else if (ota.status === 'ready') {               // first start on a new version: 'trying' until it has started
      ota.status = 'trying';
      set('ota', JSON.stringify(ota));
      use = true;
    } else {                                          // 'trying' last time and never started: not this version again
      set('ota_bad', ota.ver);
      del('ota');
      ota = null;
    }
  } else if (ota) {
    del('ota');
    ota = null;
  }

  window.__otaVer = use ? ota.ver : (window.__bundledVer || null);
  var booted = false;
  window.__otaBooted = function () {
    booted = true;
    if (!use) return;
    try {
      var o = JSON.parse(get('ota') || 'null');
      if (o && o.ver === ota.ver && o.status !== 'active') { o.status = 'active'; set('ota', JSON.stringify(o)); }
    } catch (e) { /* ignore */ }
  };
  function backToBuiltIn() {
    if (ota) set('ota_bad', ota.ver);
    del('ota');
    location.reload();
  }

  if (!use) {
    var s0 = document.createElement('script');
    s0.src = 'app.js';
    document.body.appendChild(s0);
    return;
  }
  try {
    var f = ota.files;
    if (f['index.html']) {
      var m = /<body[^>]*>([\s\S]*)<\/body>/i.exec(f['index.html']);
      if (m) document.body.innerHTML = m[1].replace(/<script[\s\S]*?<\/script>/gi, '');
    }
    if (f['style.css']) {
      var st = document.createElement('style');
      st.textContent = f['style.css'];
      document.head.appendChild(st);
      var old = document.querySelector('link[href="style.css"]');
      if (old) old.parentNode.removeChild(old);
    }
    var failed = false;
    var onErr = function () { failed = true; };
    window.addEventListener('error', onErr);
    var sc = document.createElement('script');
    sc.textContent = f['app.js'];
    document.body.appendChild(sc);                    // runs now; an error in it goes to onErr
    window.removeEventListener('error', onErr);
    if (failed) { backToBuiltIn(); return; }
    setTimeout(function () { if (!booted) backToBuiltIn(); }, 15000);
  } catch (e) {
    backToBuiltIn();
  }
})();
