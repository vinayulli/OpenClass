import React from 'react';
import {messageTime} from '../messageTime';

export default function MessageTime({at,durationMs}){
  const time=messageTime(at);
  return <span className="message-timing">{time?<time dateTime={time.iso} title={time.full}>{time.label}</time>:<span title="This older message has no recorded sent time">Time unavailable</span>}{Number.isFinite(durationMs)&&durationMs>=0&&<span className="message-duration"> · Took {(durationMs/1000).toFixed(1)}s</span>}</span>;
}
