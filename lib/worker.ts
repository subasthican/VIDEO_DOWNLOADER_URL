import { NextResponse } from 'next/server';
export async function forward(request:Request, path:string) {
  const internal=process.env.VIDEO_WORKER_INTERNAL_URL;
  const base=internal || process.env.VIDEO_WORKER_URL, secret=process.env.VIDEO_WORKER_SECRET;
  if(!base || !secret || secret.length<24) {
    console.error('Video worker configuration missing: check the service binding and VIDEO_WORKER_SECRET (at least 24 characters).');
    return NextResponse.json({error:'The download service is not available yet. Please try again later.'},{status:503});
  }
  try {
    const body=await request.json();
    const result=await fetch(`${base.replace(/\/$/,'')}/${path}`,{method:'POST',headers:{'Content-Type':'application/json','Authorization':`Bearer ${secret}`},body:JSON.stringify(body),cache:'no-store',signal:AbortSignal.timeout(55000)});
    const data=await result.json();
    // Standalone/local workers need an absolute origin; Vercel services share the website's routes.
    if(!internal) for(const key of ['url','preview']) {
      if(typeof data[key]==='string' && data[key].startsWith('/') && !data[key].startsWith('//')) {
        data[key]=new URL(data[key],base).toString();
      }
    }
    return NextResponse.json(data,{status:result.status,headers:{'Cache-Control':'no-store'}});
  } catch {return NextResponse.json({error:'The video service could not respond. Please try again.'},{status:502});}
}
