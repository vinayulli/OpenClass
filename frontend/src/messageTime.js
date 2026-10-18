export function messageTime(value,locale=undefined){
  if(!value)return null;
  const date=new Date(value);
  if(Number.isNaN(date.getTime()))return null;
  return {
    iso:date.toISOString(),
    label:date.toLocaleTimeString(locale,{hour:'2-digit',minute:'2-digit'}),
    full:date.toLocaleString(locale,{dateStyle:'medium',timeStyle:'long'})
  };
}

export function conversationMessages(rows){
  return rows.flatMap(row=>[
    {role:'you',message:row.question,at:row.question_at},
    {role:'assistant',message:row.response,at:row.response_at||row.at,duration_ms:row.duration_ms,actions:row.actions,sources:row.sources,memory_status:row.memory_status}
  ]);
}
