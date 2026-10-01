import { NextResponse } from 'next/server';
export async function forward(request:Request, path:string) {
  const base=process.env.VIDEO_WORKER_URL, secret=process.env.VIDEO_WORKER_SECRET;
  if(!base || !secret) return NextResponse.json({error:'The video service is not configured yet. Set VIDEO_WORKER_URL and VIDEO_WORKER_SECRET.'},{status:503});
  try {
    const body=await request.json();
    const result=await fetch(`${base.replace(/\/$/,'')}/${path}`,{method:'POST',headers:{'Content-Type':'application/json','Authorization':`Bearer ${secret}`},body:JSON.stringify(body),cache:'no-store',signal:AbortSignal.timeout(55000)});
    const data=await result.json();
    return NextResponse.json(data,{status:result.status,headers:{'Cache-Control':'no-store'}});
  } catch {return NextResponse.json({error:'The video service could not respond. Please try again.'},{status:502});}
}
