import {forward} from '@/lib/worker';
export const maxDuration=60;
export async function POST(request:Request){return forward(request,'analyze')}
