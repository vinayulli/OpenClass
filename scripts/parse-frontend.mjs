// Syntax verification without invoking esbuild's parent-directory resolver.
import fs from 'node:fs';
import path from 'node:path';
import {createRequire} from 'node:module';
const require=createRequire(new URL('../frontend/package.json',import.meta.url));
const {parse}=require('@babel/parser');
function walk(dir){return fs.readdirSync(dir,{withFileTypes:true}).flatMap(e=>e.isDirectory()?walk(path.join(dir,e.name)):[path.join(dir,e.name)])}
let count=0;
for(const file of walk('frontend/src').filter(f=>/\.(js|jsx)$/.test(f))){
 parse(fs.readFileSync(file,'utf8'),{sourceType:'module',plugins:['jsx']});count++;
}
console.log(`Parsed ${count} frontend JavaScript/JSX files successfully. This does not verify browser behavior.`);
