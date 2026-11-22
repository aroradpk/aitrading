# NSE UDiFF Offline Audit

A dependency-free Node.js 22+ tool to validate a **locally supplied** NSE CM UDiFF end-of-day bhavcopy ZIP. Checks SHA-256 (including optional caller-supplied expected hash), ZIP32 structure, DEFLATE/STORE, CRC32, CSV content, date, duplicate instruments, numeric fields and unsafe symbols.

**Not affiliated with NSE.** It does not authenticate an NSE publisher, download market data, access brokerage accounts, or offer trading advice. It makes no network requests.

## Run

Obtain the official original bhavcopy archive yourself. Then:

```bash
node scripts/verify-nse-original.mjs --file /your/local/BhavCopy_NSE_CM_0_0_0_20261030_F_0000.csv.zip --date 2026-10-30
```

For an independently known digest, append `--expected-sha256 <64-lowercase-hex-digest>`. To save a report, append `--output private-data/report.json`. Saved reports never overwrite existing files. Inside the repo, reports must live under gitignored `private-data/`.

### Library

```js
import {readFileSync} from 'node:fs';
import {verifyOriginalArchive} from './lib/nse-original-archive.mjs';
const report=verifyOriginalArchive(readFileSync('/local/original.zip'), {date:'2026-10-30'});
console.log(report.sha256,report.usableInstruments);
```

An ordinary successful parse means **structure and contents verified**, not that the source was genuinely published by NSE. Without a trusted external digest, authenticity remains unverified.

## Tests

```bash
npm test
```

Tests use **synthetic** in-memory ZIPs (STORE, DEFLATE, data descriptor and adversarial failures). They do not claim validation against live NSE originals. No network access, API keys, real market data, portfolio holdings or account identifiers are required.

## Scope

Supports one CSV member with expected filename and date, bounded ZIP32 archives and NSE CM CSV headers `TradDt`, `TckrSymb`, `SctySrs`, `ClsPric`, `PrvsClsgPric` and `TtlTradgVol`. Rejects ZIP64, extra files, encryption, abnormal row counts and other unsupported formats. Preserve your own input files and obey the source provider's distribution terms. The offline validator was isolated from a private portfolio app; no private data or personal integrations were carried over.
