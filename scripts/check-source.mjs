import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
function walk(dir){return fs.readdirSync(dir,{withFileTypes:true}).flatMap(e=>e.isDirectory()?walk(path.join(dir,e.name)):[path.join(dir,e.name)])}
let count=0;
for(const file of walk('frontend/src').filter(f=>/\.(jsx?|css)$/.test(f))){
 const text=fs.readFileSync(file,'utf8');
 for(const match of text.matchAll(/(?:from\s*|import\s*)['"]([.][^'"]+)['"]/g)){
  const base=path.resolve(path.dirname(file),match[1]);
  assert([base,base+'.js',base+'.jsx',base+'.css'].some(p=>fs.existsSync(p)),`Unresolved import ${match[1]} in ${file}`);count++;
 }
}
for(const name of ['frontend/package.json','evals/scenarios.json','deployment/project.json','deployment/model-armor-template.json','deployment/toolspec.json']) JSON.parse(fs.readFileSync(name,'utf8'));
console.log(`Resolved ${count} local frontend imports and parsed configuration JSON. This does not replace a Vite build or runtime tests.`);
