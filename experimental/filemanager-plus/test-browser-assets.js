'use strict';
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const root = path.join(__dirname, 'browser');
const {Sha256} = require(path.join(root, 'app.js'));
let passes = 0;
for (const length of [0,1,55,56,63,64,65,1000,1048577]) {
  const data = crypto.randomBytes(length);
  const digest = new Sha256();
  for (let offset = 0; offset < length; offset += 31) {
    digest.update(data.subarray(offset, offset + 31));
  }
  if (digest.hex() !== crypto.createHash('sha256').update(data).digest('hex'))
    throw new Error('SHA-256 mismatch length ' + length);
  passes++;
}
const html = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
const app = fs.readFileSync(path.join(root, 'app.js'), 'utf8');
const css = fs.readFileSync(path.join(root, 'style.css'), 'utf8');
for (const id of ['status','session','pick','folder','send','job','progress','cancel','files','refresh']) {
  if (!html.includes('id="' + id + '"')) throw new Error('Missing browser control ' + id);
  passes++;
}
for (const api of ['/pair','/files','/batch','/offer','/upload/','/ticket/']) {
  if (!app.includes(api)) throw new Error('Missing endpoint ' + api);
  passes++;
}
if (!html.includes('src="/appjs"') || !html.includes('href="/style"'))
  throw new Error('Browser assets should be served by the device itself');
passes++;
if (/(https?:)?\/\/[^\s"']+\.js/i.test(html) || /(https?:)?\/\/[^\s"']+\.css/i.test(html))
  throw new Error('Third-party content in local transfer page');
passes++;
if (!css.includes(':focus-visible')) throw new Error('Missing keyboard/TV focus style');
passes++;
console.log('PASS ' + passes + ' transfer browser page, endpoints, and SHA-256 checks');
