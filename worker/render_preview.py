"""Local reconstruction of publicly accessible Pictory preview media.
Not an official export; preview watermarks remain and title animation is simplified.
Usage: python render_preview.py path/to/project.json path/to/workdir
Requires httpx, Pillow, and FFmpeg. No login or storage tokens are used.
"""
import concurrent.futures, json, subprocess, sys
from pathlib import Path
from urllib.parse import urlparse
import httpx
from PIL import Image, ImageDraw, ImageFont

project=json.loads(Path(sys.argv[1]).read_text())
root=Path(sys.argv[2]).resolve();root.mkdir(parents=True,exist_ok=True)
width,height,fps=1280,720,30
videos=sorted([e for e in project['elements'] if e['type']=='video'],key=lambda e:e['startTime'])
audios=[e for e in project['elements'] if e['type']=='audio']
allowed={'media.gettyimages.com','dm0qx8t0i9gc9.cloudfront.net','audios-prod.pictorycontent.com','tracks.melod.ie'}

def command(args):
    p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    if p.returncode: raise RuntimeError(p.stderr.decode(errors='replace')[-2000:])
    return p.stdout

def fetch(item):
    key,e=item;url=e['url'];target=root/(key+('.mp3' if e['type']=='audio' else '.mp4'))
    if target.exists() and target.stat().st_size: return key,target
    parsed=urlparse(url)
    if parsed.scheme!='https' or parsed.hostname not in allowed: raise ValueError('Unexpected source media host')
    with httpx.Client(timeout=90,follow_redirects=False) as client:
        with client.stream('GET',url) as response:
            response.raise_for_status()
            with target.with_suffix('.part').open('wb') as f:
                for chunk in response.iter_bytes(): f.write(chunk)
    target.with_suffix('.part').rename(target)
    print('Fetched',key,flush=True)
    return key,target

items=[(f'clip-{i:02}',e) for i,e in enumerate(videos)]+[(e['id'],e) for e in audios]
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    assets=dict(pool.map(fetch,items))

# Build static title overlays in the positions published by the project.
# Preview motion effects are not reproduced; no watermark is removed.
def percent(value,base): return float(str(value).rstrip('%'))/100*base

def title_overlay(index,element):
    overlay=Image.new('RGBA',(width,height),(0,0,0,0));draw=ImageDraw.Draw(overlay)
    texts=[e for e in project['elements'] if e['type']=='text' and abs(e['startTime']-element['startTime'])<0.05]
    for e in texts:
        size=round(float(e.get('fontSize',24))*width/960)
        font=ImageFont.truetype('/System/Library/Fonts/Helvetica.ttc',size)
        x=percent(e.get('xPercent','0%'),width);y=percent(e.get('yPercent','0%'),height)
        maxwidth=percent(e.get('width','100%'),width)
        words=e['text'].split();lines=[];line=''
        for word in words:
            candidate=(line+' '+word).strip()
            if line and draw.textlength(candidate,font=font)>maxwidth: lines.append(line);line=word
            else: line=candidate
        if line:lines.append(line)
        for line in lines:
            draw.text((x,y),line,font=font,fill=(204,204,204,255));y+=size*float(e.get('lineHeight',1.45))
    target=root/f'title-{index:02}.png';overlay.save(target)
    return target,bool(texts)

def render(item):
    i,e=item;target=root/f'scene-{i:02}.mp4'
    if target.exists() and target.stat().st_size: return target
    start=round(e['startTime']*fps);end=round((e['startTime']+e['duration'])*fps);frames=end-start
    w=round(percent(e.get('width','100%'),width)/2)*2
    h=round(percent(e.get('height','100%'),height)/2)*2
    x=round(percent(e.get('xPercent','0%'),width));y=round(percent(e.get('yPercent','0%'),height))
    overlay,has_text=title_overlay(i,e)
    args=['ffmpeg','-hide_banner','-loglevel','error','-y','-stream_loop','-1','-i',str(assets[f'clip-{i:02}']),'-f','lavfi','-i',f'color=c=black:s={width}x{height}:r={fps}']
    graph=f'[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,fps={fps}[clip];[1:v][clip]overlay={x}:{y}:shortest=1[base]'
    if has_text:
        args+=['-loop','1','-i',str(overlay)]
        graph+=';[base][2:v]overlay=0:0:shortest=1[out]'
    else: graph+=';[base]null[out]'
    args+=['-filter_complex',graph,'-map','[out]','-an','-frames:v',str(frames),'-c:v','libx264','-preset','veryfast','-crf','23','-pix_fmt','yuv420p','-threads','2',str(target)]
    command(args);print(f'Rendered scene {i+1}/{len(videos)}',flush=True);return target

with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
    scenes=list(pool.map(render,enumerate(videos)))
concat=root/'scenes.txt';concat.write_text(''.join(f"file '{p.name}'\n" for p in scenes))
command(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','concat','-safe','0','-i',str(concat),'-c','copy',str(root/'silent.mp4')])
total=round((videos[-1]['startTime']+videos[-1]['duration'])*fps)/fps
# Voiceover is continuous in this project. Validate rather than silently misalign it.
voice=next(e for e in audios if e['id']=='voiceOver')
if any(abs(s['audioTime']-s['startTime'])>.05 for s in voice['segments']): raise ValueError('Voiceover requires custom segment assembly')
music=next(e for e in audios if e['id']=='bgMusic')
# Preserve each published music offset and volume, including wrap boundaries.
musicfilters=[];labels=[]
for i,s in enumerate(music['segments']):
    label=f'm{i}';labels.append(f'[{label}]')
    musicfilters.append(f"[2:a]atrim=start={s['audioTime']}:duration={s['duration']},asetpts=PTS-STARTPTS,volume={s.get('volume',.1)}[{label}]")
musicfilters.append(''.join(labels)+f'concat=n={len(labels)}:v=0:a=1[music]')
musicfilters.append(f'[music]afade=t=out:st={max(0,total-2)}:d=2[musicfade]')
musicfilters.append('[1:a][musicfade]amix=inputs=2:duration=longest:normalize=0[audio]')
output=root.parent/'pictory-preview-reconstructed-720p.mp4'
command(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(root/'silent.mp4'),'-i',str(assets['voiceOver']),'-stream_loop','-1','-i',str(assets['bgMusic']),'-filter_complex',';'.join(musicfilters),'-map','0:v','-map','[audio]','-t',str(total),'-c:v','copy','-c:a','aac','-b:a','192k','-movflags','+faststart',str(output)])
print('Saved',output,flush=True)
