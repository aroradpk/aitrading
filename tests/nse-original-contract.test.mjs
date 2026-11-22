import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import syntheticZip from './helpers/synthetic-zip.cjs';
import {verifyOriginalArchive} from '../lib/nse-original-archive.mjs';
import {auditOriginalSource} from '../scripts/verify-nse-original.mjs';
const date='2026-10-30',filename='BhavCopy_NSE_CM_0_0_0_20261030_F_0000.csv.zip';
const member=filename.slice(0,-4);
const rows=Array.from({length:1201},(_,i)=>
  [date,'TEST'+String(i).padStart(4,'0'),'EQ',String(100+i/100),String(99+i/100),String(1000+i)].join(','));
const csv=['TradDt,TckrSymb,SctySrs,ClsPric,PrvsClsgPric,TtlTradgVol',...rows].join('\r\n')+'\r\n';
const zip=(text,options={})=>syntheticZip(text,{name:member,...options});
const zipStored=zip(csv,{stored:true}),zipDeflated=zip(csv),zipDescriptor=zip(csv,{descriptor:true});
const digest=bytes=>createHash('sha256').update(bytes).digest('hex');
for(const [style,bytes] of [['STORE',zipStored],['DEFLATE',zipDeflated],['DESCRIPTOR',zipDescriptor]]){
 const r=verifyOriginalArchive(bytes,{date,filename,expectedSha256:digest(bytes)});
 assert.equal(r.schema,'NSE_ORIGINAL_ZIP_OFFLINE_V1');
 assert.deepEqual(r.rangeReference,{start:0,end:1023,totalBytes:bytes.length,sha256:digest(bytes.subarray(0,1024))});
 assert.equal(r.csvRows,rows.length);
 assert.equal(r.usableInstruments,1201);
 assert.equal(r.eqInstruments,1201);
 assert.equal(r.skippedRows,0);
 assert.equal(r.sourceProof,'EXPECTED_HASH_MATCH_SUPPLIED_BY_OPERATOR');
 assert.equal(r.zipMember,member);
 assert.equal(r.sha256,digest(bytes));
 assert(['STORED','DEFLATE'].includes(r.compression));
}
const fail=(b,code,options={})=>
 assert.throws(()=>verifyOriginalArchive(b,{date,filename,...options}),new RegExp('SOURCE_ZIP_'+code));
fail(zipDeflated,'EXPECTED_SOURCE_HASH_MISMATCH',{expectedSha256:'0'.repeat(64)});
fail(zipDeflated,'WRONG_OUTER_FILENAME',{filename:'something-else.zip'});
fail(zip(csv,{name:'../other.csv'}),'WRONG_INNER_FILENAME');
fail(zip(csv.replaceAll(date,'2026-10-29')),'SOURCE_DATE_MISMATCH');
fail(zip(csv.replace('TEST0000','=IMPORTXML')),'UNSAFE_CSV_SYMBOL');
fail(zip(csv.replace('TEST0000','TEST0001')),'DUPLICATE_INSTRUMENT');
const bom=Buffer.from([0xef,0xbb,0xbf]);
assert.equal(verifyOriginalArchive(zip(Buffer.concat([bom,Buffer.from(csv)])),{date}).usableInstruments,1201);
fail(zip(Buffer.concat([bom,Buffer.from(csv),Buffer.from([0xff])])),'INVALID_CSV_TEXT_ENCODING');
const disk=Buffer.from(zipDeflated),centralOffset=disk.readUInt32LE(disk.length-6);
disk.writeUInt16LE(1,centralOffset+34);
fail(disk,'MEMBER_LIMIT_OR_ENCRYPTION');
const unsupportedFlags=Buffer.from(zipDeflated);
unsupportedFlags.writeUInt16LE(0x20,6);unsupportedFlags.writeUInt16LE(0x20,centralOffset+8);
fail(unsupportedFlags,'MEMBER_LIMIT_OR_ENCRYPTION');
const badCRC=Buffer.from(zipDeflated);
const localLength=30+Buffer.byteLength(member);
badCRC[localLength+5]^=31;
assert.throws(()=>verifyOriginalArchive(badCRC,{date,filename}),/SOURCE_ZIP_/);
const wrongCount=Buffer.from(zipDeflated);
wrongCount.writeUInt16LE(2,wrongCount.length-12);
fail(wrongCount,'SPLIT_OR_MULTIFILE_ARCHIVE');
const wrongCentral=Buffer.from(zipDeflated);
wrongCentral.writeUInt32LE(1,wrongCentral.length-6);
fail(wrongCentral,'CENTRAL_OFFSET_INVALID');
const malformed=zip(csv.replace('TEST0000','"UNFINISHED'));
fail(malformed,'UNCLOSED_QUOTED_CSV_FIELD');
const folder=fs.mkdtempSync(path.join(os.tmpdir(),'nse-recovery-'));
try{
 const input=path.join(folder,filename),out=path.join(folder,'report.json');
 fs.writeFileSync(input,zipDescriptor);
 const r=auditOriginalSource({file:input,date,expectedSha256:digest(zipDescriptor),output:out});
 assert.equal(r.csvRows,1201);
 assert.equal(JSON.parse(fs.readFileSync(out,'utf8')).sha256,digest(zipDescriptor));
 assert.throws(()=>auditOriginalSource({file:input,date,output:out}),/EEXIST/);
 assert.throws(()=>auditOriginalSource({file:input,date,output:'README.json'}),/gitignored/);
 const call=spawnSync(process.execPath,['scripts/verify-nse-original.mjs','--file',input,'--date',date],
  {encoding:'utf8',timeout:30000});
 assert.equal(call.status,0,call.stderr);
 assert.equal(JSON.parse(call.stdout).usableInstruments,1201);
 assert(!call.stdout.includes('TEST0001'),'Report must not include raw source symbols');
 const bad=spawnSync(process.execPath,['scripts/verify-nse-original.mjs','--file',input,
  '--date','2026-10-29'],{encoding:'utf8',timeout:30000});
 assert.notEqual(bad.status,0);
 assert(!bad.stderr.includes(input),'Never leak full private source filename');
}finally{fs.rmSync(folder,{recursive:true,force:true});}
console.log('Verified synthetic ZIP32 STORE, DEFLATE, data descriptors, hashes, CRC, dates, malformed input and safe local CLI output. No real NSE original or private data used.');
