import {useEffect,useState} from 'react';

const pages=new Set(['learning-paths','self-study','overview','analytics','digital-twin','test-studio','assignments','students','curriculum','assessments','interventions','tutor','code','audit']);
export function readRoute(path=window.location.pathname){
  const parts=path.split('/').filter(Boolean);
  if(parts[0]==='courses'&&parts[1]){let courseId;try{courseId=decodeURIComponent(parts[1])}catch{return {courseId:'',page:'overview'}}return {courseId,page:pages.has(parts[2])?parts[2]:'overview'}};
  return {courseId:'',page:pages.has(parts[0])?parts[0]:'overview'};
}

export function useWorkspaceRoute(user){
  const [page,setPage]=useState(()=>readRoute().page),[courseId,setCourseId]=useState(()=>readRoute().courseId);
  useEffect(()=>{
    const pop=()=>{const route=readRoute();setPage(route.page);setCourseId(route.courseId)};
    window.addEventListener('popstate',pop);
    return()=>window.removeEventListener('popstate',pop);
  },[]);
  useEffect(()=>{
    if(!user||!courseId)return;
    // Timed attempts are in-memory views of the Assessments page.
    const path=`/courses/${encodeURIComponent(courseId)}/${page==='exam'?'assessments':page}`;
    if(window.location.pathname!==path){
      if(!window.location.pathname.startsWith('/courses/'))window.history.replaceState({},'',path);
      else window.history.pushState({},'',path);
    }
  },[page,courseId,user?.id]);
  return {page,setPage,courseId,setCourseId};
}
