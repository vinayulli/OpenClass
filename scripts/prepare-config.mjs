import fs from 'node:fs';
import path from 'node:path';
const project=JSON.parse(fs.readFileSync('deployment/project.json','utf8'));
const target='deployment/generated';
fs.mkdirSync(target,{recursive:true});
for(const name of fs.readdirSync('deployment/gateway')){
 const text=fs.readFileSync(path.join('deployment/gateway',name),'utf8')
  .replaceAll('PROJECT_ID',project.project_id).replaceAll('REGION',project.region);
 fs.writeFileSync(path.join(target,name.replace('.example','')),text);
}
fs.writeFileSync(path.join(target,'plan.json'),JSON.stringify({...project,status:'prepared locally; no cloud resources applied'},null,2));
console.log(`Prepared gateway and protection configuration for ${project.project_id}/${project.region}; no cloud changes.`);
