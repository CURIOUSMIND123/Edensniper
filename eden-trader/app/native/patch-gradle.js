// Numbers the version from the GitHub build number and, when the app's own signing key is given (repository
// secrets EDEN_KEYSTORE_B64 / EDEN_KEYSTORE_PASSWORD, decoded by the workflow to $EDEN_KEYSTORE), signs with it so
// every new APK installs over the old one and keeps the settings. Appends a block at the end of app/build.gradle.
const fs = require('fs');
const f = 'android/app/build.gradle';
let g = fs.readFileSync(f, 'utf8');
const MARK = '// >>> eden trader build';
if (g.includes(MARK)) { console.log('gradle already patched'); process.exit(0); }
const build = parseInt(process.env.BUILD_NUMBER || '1', 10);
const ks = process.env.EDEN_KEYSTORE;
const signing = ks && fs.existsSync(ks) ? `
    signingConfigs {
        eden {
            storeFile file(System.getenv("EDEN_KEYSTORE"))
            storePassword System.getenv("EDEN_KEYSTORE_PASSWORD")
            keyAlias "eden"
            keyPassword System.getenv("EDEN_KEYSTORE_PASSWORD")
        }
    }
    buildTypes {
        release { signingConfig signingConfigs.eden }
    }` : '';
g += `

${MARK}
android {
    defaultConfig {
        versionCode ${build}
        versionName "1.0.${build}"
    }${signing}
}
// <<< eden trader build
`;
fs.writeFileSync(f, g);
console.log('gradle patched: version 1.0.' + build + (signing ? ', signed with the app\'s own key' : ', build key (no EDEN_KEYSTORE_B64 secret)'));
