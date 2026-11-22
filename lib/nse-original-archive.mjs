/**
 * Independent offline NSE CM UDiFF ZIP32 verifier (Node 22).
 * No network or private accounts. This is byte/content verification, NOT
 * independent NSE publisher authentication. Fail closed on unexpected ZIP shape.
 */
import {createHash} from 'node:crypto';
import {inflateRawSync} from 'node:zlib';
const MAX_ZIP=2*1024*1024,MAX_CSV=12*1024*1024,MAX_ROWS=6500;
const KNOWN={};
const crcTable=Uint32Array.from({length:256},(_,i)=>{
 let c=i;for(let n=0;n<8;n++)c=(c&1)?(0xedb88320^(c>>>1)):(c>>>1);return c>>>0;
});
function crc32(buf){let crc=0xffffffff;for(const x of buf)crc=crcTable[(crc^x)&255]^(crc>>>8);return(crc^0xffffffff)>>>0;}
const fail=reason=>{throw Error('SOURCE_ZIP_'+reason);};
function validDate(d){
 if(typeof d!=='string'||!/^20\d\d-\d\d-\d\d$/.test(d))return false;
 const parsed=new Date(d+'T00:00:00Z');
 return Number.isFinite(parsed.getTime())&&parsed.toISOString().slice(0,10)===d;
}
function bytesEquals(a,b){return a.length===b.length&&a.equals(b);}
function readCSV(text){
 const rows=[];let row=[],field='',quoted=false,lastQuote=false;
 for(let i=0;i<text.length;i++){
  const ch=text[i];
  if(quoted){
   if(ch==='"'){
    if(text[i+1]==='"'){field+='"';i++;}else{quoted=false;lastQuote=true;}
   }else field+=ch;
  }else if(ch===','){row.push(field);field='';lastQuote=false;}
  else if(ch==='\r'||ch==='\n'){
   if(ch==='\r'&&text[i+1]==='\n')i++;
   if(row.length||field){row.push(field);rows.push(row);}
   row=[];field='';lastQuote=false;
   if(rows.length>MAX_ROWS+1)fail('TOO_MANY_ROWS');
  }else if(ch==='"'&&field===''&&!lastQuote){quoted=true;}
  else if(ch==='"'||lastQuote){fail('MALFORMED_CSV_QUOTING');}
  else field+=ch;
  if(field.length>150000)fail('OVERSIZED_CSV_CELL');
 }
 if(quoted)fail('UNCLOSED_QUOTED_CSV_FIELD');
 if(row.length||field){row.push(field);rows.push(row);}
 return rows;
}
export function verifyOriginalArchive(bytes,{date,expectedSha256=null,filename=null}={}){
 if(!validDate(date))fail('INVALID_DATE');
 const name='BhavCopy_NSE_CM_0_0_0_'+date.replaceAll('-','')+'_F_0000.csv.zip';
 if(filename!==null&&filename!==name)fail('WRONG_OUTER_FILENAME');
 if(!Buffer.isBuffer(bytes)||bytes.length<100||bytes.length>MAX_ZIP)fail('ZIP_BYTES_LIMIT');
 if(expectedSha256!==null&&!/^[a-f0-9]{64}$/.test(expectedSha256))fail('EXPECTED_HASH_FORMAT');
 const hash=createHash('sha256').update(bytes).digest('hex');
 if(KNOWN[date]&&hash!==KNOWN[date])fail('PINNED_SOURCE_HASH_MISMATCH');
 if(expectedSha256&&hash!==expectedSha256)fail('EXPECTED_SOURCE_HASH_MISMATCH');
 const u16=i=>{if(i<0||i+2>bytes.length)fail('ZIP_TRUNCATED');return bytes.readUInt16LE(i);};
 const u32=i=>{if(i<0||i+4>bytes.length)fail('ZIP_TRUNCATED');return bytes.readUInt32LE(i);};
 const magic=(p,v)=>p>=0&&p+4<=bytes.length&&u32(p)===v;
 if(!magic(0,0x04034b50))fail('LOCAL_HEADER_MISSING');
 let eocd=-1;
 for(let p=bytes.length-22;p>=Math.max(0,bytes.length-65557);p--){
  if(magic(p,0x06054b50)&&p+22+u16(p+20)===bytes.length){eocd=p;break;}
 }
 if(eocd===-1)fail('CENTRAL_TRAILER_MISSING');
 if(u16(eocd+4)!==0||u16(eocd+6)!==0||u16(eocd+8)!==1||u16(eocd+10)!==1)
  fail('SPLIT_OR_MULTIFILE_ARCHIVE');
 const centralLen=u32(eocd+12),central=u32(eocd+16);
 if(centralLen<46||centralLen>65535||central+centralLen!==eocd||!magic(central,0x02014b50))
  fail('CENTRAL_OFFSET_INVALID');
 const flags=u16(central+8),method=u16(central+10),crc=u32(central+16);
 const packed=u32(central+20),plain=u32(central+24),namelen=u16(central+28);
 const extra=u16(central+30),comment=u16(central+32),local=u32(central+42);
 const allowedFlags=0x0808 | (method===8?0x0006:0); // UTF-8 names, descriptor and DEFLATE options.
 if((flags & ~allowedFlags)!==0||u16(central+34)!==0||![0,8].includes(method)||plain<100||plain>MAX_CSV||
  packed<1||packed>MAX_ZIP||namelen<5||namelen>130||
  central+46+namelen+extra+comment!==eocd||local!==0||!magic(local,0x04034b50))
  fail('MEMBER_LIMIT_OR_ENCRYPTION');
 const localFlags=u16(local+6),localMethod=u16(local+8),localName=u16(local+26),localExtra=u16(local+28);
 if(localFlags!==flags||localMethod!==method||localName!==namelen||local+30+namelen+localExtra+packed>central)
  fail('LOCAL_CENTRAL_MISMATCH');
 if((flags&8)===0&&(u32(local+14)!==crc||u32(local+18)!==packed||u32(local+22)!==plain))
  fail('LOCAL_SIZE_OR_CRC_MISMATCH');
 const actualName=bytes.subarray(central+46,central+46+namelen);
 if(!bytesEquals(actualName,bytes.subarray(local+30,local+30+namelen)))
  fail('LOCAL_FILENAME_MISMATCH');
 const expectedMember=Buffer.from(name.slice(0,-4),'ascii');
 if(!bytesEquals(actualName,expectedMember))fail('WRONG_INNER_FILENAME');
 const start=local+30+localName+localExtra,end=start+packed;
 if((flags&8)!==0){
  const descriptor=end;
  if(end+12>central)fail('DATA_DESCRIPTOR_MISSING');
  const offset=magic(descriptor,0x08074b50)?4:0;
  if(descriptor+offset+12!==central||u32(descriptor+offset)!==crc||
     u32(descriptor+offset+4)!==packed||u32(descriptor+offset+8)!==plain)
    fail('DATA_DESCRIPTOR_MISMATCH');
 }else if(end!==central)fail('UNEXPECTED_ARCHIVE_TRAILING_BYTES');
 let csv;
 try{csv=method===0?Buffer.from(bytes.subarray(start,end)):
   inflateRawSync(bytes.subarray(start,end),{maxOutputLength:MAX_CSV});}
 catch(e){fail('UNSUPPORTED_OR_OVERSIZED_DEFLATE');}
 if(csv.length!==plain||crc32(csv)!==crc)fail('CSV_BYTES_OR_CRC_MISMATCH');
 let text;
 try{text=new TextDecoder('utf-8',{fatal:true}).decode(csv);}
 catch{fail('INVALID_CSV_TEXT_ENCODING');}
 const rows=readCSV(text);
 if(rows.length<101||rows.length>MAX_ROWS+1)fail('UNSUPPORTED_CSV_ROW_COUNT');
 const normalized=rows[0].map(x=>x.replace(/^\uFEFF/,'').trim().toLowerCase());
 const indices={};for(const [key,alias] of Object.entries({
  date:'traddt',symbol:'tckrsymb',series:'sctysrs',close:'clspric',
  previous:'prvsclsgpric',volume:'ttltradgvol'})){
  const matches=normalized.flatMap((v,i)=>v===alias?[i]:[]);
  if(matches.length!==1)fail('REQUIRED_CSV_COLUMNS');
  indices[key]=matches[0];
 }
 const seen=new Set();let usable=0,eq=0,other=0,invalid=0;
 for(let r=1;r<rows.length;r++){
  const row=rows[r];
  if(row.length!==normalized.length)fail('MALFORMED_CSV_ROW');
  const trade=row[indices.date].trim(),symbol=row[indices.symbol].trim().toUpperCase(),
    series=row[indices.series].trim().toUpperCase(),close=row[indices.close].trim(),
    prev=row[indices.previous].trim(),volume=row[indices.volume].trim();
  if(trade!==date)fail('SOURCE_DATE_MISMATCH');
  if(symbol&&!/^[A-Z0-9][A-Z0-9&._-]{0,59}$/.test(symbol))fail('UNSAFE_CSV_SYMBOL');
  if(series&&!/^[A-Z0-9]{1,12}$/.test(series))fail('UNSAFE_CSV_SERIES');
  const numbers=[close,prev,volume];
  if(numbers.some(v=>v!==''&&(!/^\d+(?:\.\d+)?$/.test(v)||!Number.isFinite(Number(v)))))
   fail('INVALID_NUMERIC_FIELD');
  if(!symbol||!series||numbers.includes('')||Number(close)===0){invalid++;continue;}
  const key=symbol+'|'+series;
  if(seen.has(key))fail('DUPLICATE_INSTRUMENT');
  seen.add(key);usable++;if(series==='EQ')eq++;else other++;
 }
 if(usable<100)fail('TOO_FEW_USABLE_INSTRUMENTS');
 return {schema:'NSE_ORIGINAL_ZIP_OFFLINE_V1',status:'LOCAL_SOURCE_BYTES_AND_CONTENT_VALIDATED',
  date,filename:name,sourceURL:'https://nsearchives.nseindia.com/content/cm/'+name,
  sha256:hash,sourceProof:KNOWN[date]?'PINNED_HISTORICAL_BYTES_MATCH':
   expectedSha256?'EXPECTED_HASH_MATCH_SUPPLIED_BY_OPERATOR':'UNPINNED_LOCAL_BYTES_ONLY',
  rangeReference:bytes.length>=1024?{start:0,end:1023,totalBytes:bytes.length,
   sha256:createHash('sha256').update(bytes.subarray(0,1024)).digest('hex')}:null,
  bytes:bytes.length,uncompressedBytes:csv.length,zipMember:actualName.toString('ascii'),
  csvRows:rows.length-1,usableInstruments:usable,eqInstruments:eq,otherSeriesInstruments:other,
  skippedRows:invalid,compression:method===8?'DEFLATE':'STORED',
  warning:'Local byte/digest/CRC/contents verified; NSE publisher and actual Google-hosted availability NOT independently authenticated. No private holdings or API used.'};
}
