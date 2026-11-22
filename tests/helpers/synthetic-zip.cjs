'use strict';
const {deflateRawSync}=require('node:zlib');
function crc(b){
 let n=0xffffffff;for(const v of b){n^=v;for(let i=0;i<8;i++)n=n&1?(n>>>1)^0xedb88320:n>>>1;}
 return(n^0xffffffff)>>>0;
}
function zip(text,{stored=false,descriptor=false,name}={}){
 const csvBytes=Buffer.from(text),compressed=stored?csvBytes:deflateRawSync(csvBytes),
  nameBytes=Buffer.from(name),crcValue=crc(csvBytes),flags=descriptor?8:0,method=stored?0:8;
 const local=Buffer.alloc(30),central=Buffer.alloc(46),end=Buffer.alloc(22);
 local.writeUInt32LE(0x04034b50,0);local.writeUInt16LE(flags,6);local.writeUInt16LE(method,8);
 if(!descriptor){local.writeUInt32LE(crcValue,14);local.writeUInt32LE(compressed.length,18);local.writeUInt32LE(csvBytes.length,22);}
 local.writeUInt16LE(nameBytes.length,26);
 central.writeUInt32LE(0x02014b50,0);central.writeUInt16LE(flags,8);central.writeUInt16LE(method,10);
 central.writeUInt32LE(crcValue,16);central.writeUInt32LE(compressed.length,20);central.writeUInt32LE(csvBytes.length,24);
 central.writeUInt16LE(nameBytes.length,28);central.writeUInt32LE(0,42);
 const dd=descriptor?Buffer.alloc(16):Buffer.alloc(0);
 if(descriptor){dd.writeUInt32LE(0x08074b50,0);dd.writeUInt32LE(crcValue,4);
 dd.writeUInt32LE(compressed.length,8);dd.writeUInt32LE(csvBytes.length,12);}
 const first=Buffer.concat([local,nameBytes,compressed,dd]),directory=Buffer.concat([central,nameBytes]);
 end.writeUInt32LE(0x06054b50,0);end.writeUInt16LE(1,8);end.writeUInt16LE(1,10);
 end.writeUInt32LE(directory.length,12);end.writeUInt32LE(first.length,16);
 return Buffer.concat([first,directory,end]);
}

module.exports=zip;
