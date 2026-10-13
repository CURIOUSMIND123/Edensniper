// Adds what the notification service needs to the generated AndroidManifest.xml: permissions, the service, and the
// receiver that starts it again after a phone restart. Safe to run more than once.
const fs = require('fs');
const f = 'android/app/src/main/AndroidManifest.xml';
let x = fs.readFileSync(f, 'utf8');
const perms = [
  'android.permission.INTERNET',
  'android.permission.POST_NOTIFICATIONS',
  'android.permission.FOREGROUND_SERVICE',
  'android.permission.FOREGROUND_SERVICE_SPECIAL_USE',
  'android.permission.RECEIVE_BOOT_COMPLETED',
  'android.permission.WAKE_LOCK',
  'android.permission.REQUEST_IGNORE_BATTERY_OPTIMIZATIONS',
];
let ins = '';
for (const p of perms) if (!x.includes(`"${p}"`)) ins += `    <uses-permission android:name="${p}" />\n`;
if (ins) x = x.replace(/<application/, ins + '    <application');
if (!x.includes('.TraderService')) {
  const parts =
    '        <service\n' +
    '            android:name=".TraderService"\n' +
    '            android:exported="false"\n' +
    '            android:foregroundServiceType="specialUse">\n' +
    '            <property android:name="android.app.PROPERTY_SPECIAL_USE_FGS_SUBTYPE" android:value="Live market call alerts the user asked for" />\n' +
    '        </service>\n' +
    '        <receiver android:name=".BootReceiver" android:exported="true">\n' +
    '            <intent-filter>\n' +
    '                <action android:name="android.intent.action.BOOT_COMPLETED" />\n' +
    '            </intent-filter>\n' +
    '        </receiver>\n';
  x = x.replace('</application>', parts + '    </application>');
}
fs.writeFileSync(f, x);
console.log('manifest patched' + (ins ? ':\n' + ins : ' (permissions already there)'));
