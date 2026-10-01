'use client';

import {useEffect, useRef, useState} from 'react';
import {ArrowDown, ExternalLink, Circle, Square} from 'lucide-react';

export default function PreviewRecorder({url, title}:{url:string; title:string}) {
  const [recording,setRecording]=useState(false);
  const [starting,setStarting]=useState(false);
  const [status,setStatus]=useState('');
  const recorder=useRef<MediaRecorder|null>(null);
  const stream=useRef<MediaStream|null>(null);
  const timer=useRef<ReturnType<typeof setTimeout>|null>(null);
  const alive=useRef(true);
  const cancel=useRef(false);

  useEffect(()=>{
    alive.current=true;
    const cleanup=()=>{
      alive.current=false;
      cancel.current=true;
      if(timer.current) clearTimeout(timer.current);
      if(recorder.current?.state==='recording') recorder.current.stop();
      stream.current?.getTracks().forEach(track=>track.stop());
    };
    window.addEventListener('pagehide',cleanup);
    return()=>{window.removeEventListener('pagehide',cleanup);cleanup()};
  },[]);

  async function start() {
    if(!navigator.mediaDevices?.getDisplayMedia || typeof MediaRecorder==='undefined') {
      setStatus('Preview recording is unavailable in this browser. Use desktop Chrome or Edge, or export the video in Pictory.');return;
    }
    setStarting(true);setStatus('');cancel.current=false;
    try {
      const capture=await navigator.mediaDevices.getDisplayMedia({video:{frameRate:30},audio:true});
      if(!alive.current){capture.getTracks().forEach(t=>t.stop());return}
      stream.current=capture;
      if(!capture.getAudioTracks().length){
        capture.getTracks().forEach(t=>t.stop());
        throw new Error('No audio was shared. Try again: choose the Pictory browser tab and enable “Share tab audio”.');
      }
      const mime=['video/webm;codecs=vp9,opus','video/webm;codecs=vp8,opus','video/mp4','video/webm'].find(type=>MediaRecorder.isTypeSupported(type));
      if(!mime) throw new Error('This browser cannot save a compatible recording. Use desktop Chrome or Edge.');
      const instance=new MediaRecorder(capture,{mimeType:mime,videoBitsPerSecond:8_000_000});
      recorder.current=instance;
      const parts:Blob[]=[];let bytes=0;
      instance.ondataavailable=event=>{
        if(event.data.size){parts.push(event.data);bytes+=event.data.size}
        if(bytes>=400*1024*1024 && instance.state==='recording') {
          setStatus('The recording reached its size limit. Saving the captured portion.');instance.stop();
        }
      };
      instance.onerror=()=>{cancel.current=true;setStatus('The browser could not finish the recording. Please try again.');capture.getTracks().forEach(t=>t.stop());setRecording(false)};
      instance.onstop=()=>{
        if(timer.current) clearTimeout(timer.current);
        capture.getTracks().forEach(t=>t.stop());
        if(cancel.current || !alive.current) return;
        setRecording(false);
        if(!parts.length){setStatus('No video was recorded. Please try again.');return}
        const blob=new Blob(parts,{type:instance.mimeType});
        const href=URL.createObjectURL(blob);
        const anchor=document.createElement('a');anchor.href=href;
        anchor.download=(title.replace(/[^a-zA-Z0-9 _-]/g,'').slice(0,80)||'pictory')+'-preview-recording.'+(mime.includes('mp4')?'mp4':'webm');
        document.body.append(anchor);anchor.click();anchor.remove();
        setTimeout(()=>URL.revokeObjectURL(href),60_000);
        setStatus('Recording saved. This is captured playback, including the selected tab’s visible content, not the original exported video.');
      };
      capture.getVideoTracks()[0].addEventListener('ended',()=>{if(instance.state==='recording') instance.stop()},{once:true});
      instance.start(1000);setRecording(true);
      setStatus('Recording now. Switch to the Pictory tab, play the video from the beginning, then return here and select Stop & download.');
      timer.current=setTimeout(()=>{if(instance.state==='recording') instance.stop()},30*60*1000);
    } catch(error) {
      stream.current?.getTracks().forEach(track=>track.stop());
      if(alive.current) setStatus(error instanceof DOMException && error.name==='NotAllowedError' ? 'Recording was cancelled or screen sharing was denied. You can try again.' : (error as Error).message);
    } finally {if(alive.current) setStarting(false)}
  }

  return <div className="preview-actions">
    <div className="unavailable-download"><button className="primary" disabled title="Pictory has not exposed an exported video through this preview link"><ArrowDown size={18}/> Download original unavailable</button><p>This public link contains a preview timeline. Original MP4, 1080p, and 720p downloads require an export from the project owner.</p></div>
    <div className="recording-option"><h3>Save a recording of this preview</h3><ol><li>Open the preview in a separate tab and pause at the beginning.</li><li>Select Record preview, choose that tab, and enable Share tab audio.</li><li>Play the preview. When it finishes, select Stop &amp; download here.</li></ol><p className="message">Recording saves the selected tab’s visible content and audio, usually as WebM. Quality depends on playback and your display. Use full-screen playback to keep the video large. Recording stays on your device.</p><div className="preview-buttons"><a href={url} target="_blank" rel="noopener noreferrer" className="secondary"><ExternalLink size={16}/> Open preview tab</a>{recording?<button className="primary" onClick={()=>recorder.current?.stop()}><Square size={15}/> Stop &amp; download</button>:<button className="primary" onClick={start} disabled={starting}><Circle size={15}/> {starting?'Choose a tab…':'Record preview'}</button>}</div>{status&&<p className="recording-status" role="status">{status}</p>}</div>
  </div>;
}
