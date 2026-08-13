/* behavioral.js — demo overlay: device fingerprint + keystroke timing.
 *
 * Computed in the browser and carried on hidden form inputs so the server
 * can compare each login against the user's accepted-login baseline.
 *
 * SHA-256 is pure JS: crypto.subtle is undefined over plain LAN HTTP
 * (non-secure context), so we never rely on it. The fingerprint is a demo
 * indicator, not a security boundary.
 */
(function () {
  'use strict';

  // ---- SHA-256 (pure JS, public-domain compact implementation) ---------
  function sha256(ascii) {
    function rightRotate(value, amount) { return (value >>> amount) | (value << (32 - amount)); }
    var mathPow = Math.pow;
    var maxWord = mathPow(2, 32);
    var result = '';
    var words = [];
    var asciiBitLength = ascii.length * 8;
    var hash = sha256.h = sha256.h || [];
    var k = sha256.k = sha256.k || [];
    var primeCounter = k.length;
    var isComposite = {};
    for (var candidate = 2; primeCounter < 64; candidate++) {
      if (!isComposite[candidate]) {
        for (var i = 0; i < 313; i += candidate) isComposite[i] = candidate;
        hash[primeCounter] = (mathPow(candidate, 0.5) * maxWord) | 0;
        k[primeCounter++] = (mathPow(candidate, 1 / 3) * maxWord) | 0;
      }
    }
    ascii += '\x80';
    while (ascii.length % 64 - 56) ascii += '\x00';
    for (i = 0; i < ascii.length; i++) {
      var j = ascii.charCodeAt(i);
      if (j >> 8) return '';
      words[i >> 2] |= j << ((3 - i) % 4) * 8;
    }
    words[words.length] = ((asciiBitLength / maxWord) | 0);
    words[words.length] = asciiBitLength;
    for (j = 0; j < words.length;) {
      var w = words.slice(j, j += 16);
      var oldHash = hash;
      hash = hash.slice(0, 8);
      for (i = 0; i < 64; i++) {
        var w15 = w[i - 15], w2 = w[i - 2];
        var a = hash[0], e = hash[4];
        var temp1 = hash[7]
          + (rightRotate(e, 6) ^ rightRotate(e, 11) ^ rightRotate(e, 25))
          + ((e & hash[5]) ^ ((~e) & hash[6]))
          + k[i]
          + (w[i] = (i < 16) ? w[i] : (
            w[i - 16]
            + (rightRotate(w15, 7) ^ rightRotate(w15, 18) ^ (w15 >>> 3))
            + w[i - 7]
            + (rightRotate(w2, 17) ^ rightRotate(w2, 19) ^ (w2 >>> 10))
          ) | 0);
        var temp2 = (rightRotate(a, 2) ^ rightRotate(a, 13) ^ rightRotate(a, 22))
          + ((a & hash[1]) ^ (a & hash[2]) ^ (hash[1] & hash[2]));
        hash = [(temp1 + temp2) | 0].concat(hash);
        hash[4] = (hash[4] + temp1) | 0;
      }
      for (i = 0; i < 8; i++) hash[i] = (hash[i] + oldHash[i]) | 0;
    }
    for (i = 0; i < 8; i++) {
      for (j = 3; j + 1; j--) {
        var b = (hash[i] >> (j * 8)) & 255;
        result += ((b < 16) ? 0 : '') + b.toString(16);
      }
    }
    return result;
  }

  // ---- Device fingerprint -------------------------------------------------
  function deviceFingerprint() {
    var parts = [
      navigator.userAgent,
      navigator.platform || '',
      String(screen.width),
      String(screen.height),
      String(screen.colorDepth),
      String(navigator.hardwareConcurrency || ''),
      String(navigator.deviceMemory || ''),
      navigator.language || '',
      String(new Date().getTimezoneOffset()),
    ];
    return sha256(parts.join('|'));
  }

  // ---- Keystroke timing ----------------------------------------------------
  var MODIFIERS = ['Shift', 'Control', 'Alt', 'Meta', 'CapsLock', 'Tab', 'Escape',
    'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Home', 'End', 'PageUp',
    'PageDown', 'Delete', 'Insert'];
  var holds = [];
  var gaps = [];
  var chars = 0;
  var start = null;
  var lastDown = null;
  var downInfo = null;

  document.addEventListener('keydown', function (e) {
    if (e.repeat || MODIFIERS.indexOf(e.key) !== -1) return;
    var now = performance.now();
    if (start === null) start = now;
    if (lastDown !== null && lastDown !== e.code) gaps.push(now - lastDown);
    if (e.key && e.key.length === 1) chars++;
    lastDown = e.code;
    downInfo = { code: e.code, t: now };
  });

  document.addEventListener('keyup', function (e) {
    if (downInfo && downInfo.code === e.code) {
      holds.push(performance.now() - downInfo.t);
      downInfo = null;
    }
  });

  function median(arr) {
    if (!arr.length) return 0;
    var s = arr.slice().sort(function (a, b) { return a - b; });
    var m = Math.floor(s.length / 2);
    return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
  }

  // ---- Form hooks ------------------------------------------------------------
  function setField(form, name, value) {
    var el = form.querySelector('input[name="' + name + '"]');
    if (!el) {
      el = document.createElement('input');
      el.type = 'hidden';
      el.name = name;
      form.appendChild(el);
    }
    el.value = String(value);
  }

  document.addEventListener('submit', function (e) {
    var form = e.target;
    if (!form || form.tagName !== 'FORM') return;
    var elapsed = performance.now() - (start === null ? performance.now() : start);
    var wpm = elapsed > 0 ? Math.round((chars / 5) / (elapsed / 60000)) : 0;
    setField(form, 'fp_hash', deviceFingerprint());
    setField(form, 'key_hold_median', Math.round(median(holds)));
    setField(form, 'key_gap_median', Math.round(median(gaps)));
    setField(form, 'wpm', wpm);
    setField(form, 'typing_n', Math.max(holds.length, gaps.length, chars));
  });
})();