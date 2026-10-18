import React, {useState} from 'react';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

function CodeBlock({children}) {
  const [status,setStatus]=useState('Copy code');
  const code=React.Children.toArray(children).find(React.isValidElement);
  const text=String(code?.props.children||'');
  const language=code?.props.className?.replace('language-','')||'code';
  return React.createElement('div',{className:'agent-code'},
    React.createElement('div',{className:'agent-code-toolbar'},language,
      React.createElement('button',{type:'button',onClick:async()=>{try{await navigator.clipboard.writeText(text);setStatus('Copied')}catch{setStatus('Select code to copy')}}},status)),
    React.createElement('pre',null,children));
}

export default function AgentMarkdown({children}) {
  return React.createElement('div',{className:'agent-markdown'},React.createElement(Markdown,{
    remarkPlugins:[remarkGfm],skipHtml:true,
    urlTransform:url=>/^https?:\/\//i.test(url)?url:'',
    components:{pre:CodeBlock,img:()=>null,a:({href,children})=>React.createElement('a',{href:href||undefined,target:'_blank',rel:'noopener noreferrer'},children)}
  },String(children||'')));
}
