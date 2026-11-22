#!/usr/bin/env node
/** Local NSE original ZIP verifier — offline only; no private portfolio input. */
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {verifyOriginalArchive} from '../lib/nse-original-archive.mjs';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const option=(args,key)=>{const n=args.indexOf(key);return n===-1?null:args[n+1];};
export function auditOriginalSource({file,date,expectedSha256=null,output=null}){
 if(typeof file!=='string'||!file.endsWith('.zip')||typeof date!=='string')
  throw Error('Provide an exact local final ZIP and selected YYYY-MM-DD date.');
 const source=path.resolve(file),stat=fs.lstatSync(source);
 if(!stat.isFile()||stat.isSymbolicLink()||stat.size<100||stat.size>2*1024*1024)
  throw Error('Original ZIP is not a supported regular local file.');
 const report=verifyOriginalArchive(fs.readFileSync(source),{
  date,filename:path.basename(source),expectedSha256});
 if(output!==null){
  if(typeof output!=='string'||!output.endsWith('.json'))throw Error('Output must be a private .json file.');
  const dest=path.resolve(output),rel=path.relative(root,dest).replaceAll('\\','/');
  if(!rel.startsWith('..')&&!path.isAbsolute(rel)&&!rel.startsWith('private-data/'))
    throw Error('Inside repository outputs must go under gitignored private-data/.');
  fs.mkdirSync(path.dirname(dest),{recursive:true,mode:0o700});
  fs.writeFileSync(dest,JSON.stringify(report,null,2)+'\n',{flag:'wx',mode:0o600});
 }
 return report;
}
async function main(){
 const args=process.argv.slice(2);
 if(!args.length||args.includes('--help')){
  console.log('node scripts/verify-nse-original.mjs --file /private/BhavCopy_NSE_CM_0_0_0_YYYYMMDD_F_0000.csv.zip --date YYYY-MM-DD [--expected-sha256 64_lowercase_hex] [--output private-data/nse-check.json]\nOffline verification only. No NSE fetch, brokerage access, alert or Google deployment.');
  return;
 }
 const allowed=new Set(['--file','--date','--expected-sha256','--output']);
 if(args.length%2)throw Error('Every named CLI flag must have one value.');
 for(let i=0;i<args.length;i+=2){
  if(!allowed.has(args[i])||!args[i+1]||args[i+1].startsWith('--'))
   throw Error('Invalid flag or missing argument; see --help.');
 }
 const result=auditOriginalSource({file:option(args,'--file'),date:option(args,'--date'),
  expectedSha256:option(args,'--expected-sha256'),output:option(args,'--output')});
 console.log(JSON.stringify(result,null,2));
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 main().catch(e=>{
  const safe=/^(?:SOURCE_ZIP_|Provide |Original ZIP|Output |Inside repository|Every named|Invalid flag)/.test(e.message);
  console.error('NSE_ORIGINAL_OFFLINE_ERROR: '+(safe?e.message:'Check the local original file and output path.'));
  process.exitCode=1;
 });
}
