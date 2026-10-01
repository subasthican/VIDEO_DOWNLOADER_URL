"""Extraction service. Deploy separately from the Vercel Next.js app."""
import asyncio, base64, hashlib, hmac, json, os, re, shutil, tempfile, time
from pathlib import Path
from urllib.parse import urlparse
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

SECRET = os.environ.get('VIDEO_WORKER_SECRET', '')
PUBLIC = os.environ.get('WORKER_PUBLIC_URL', 'http://localhost:8000').rstrip('/')
if len(SECRET) < 24:
    raise RuntimeError('Set VIDEO_WORKER_SECRET to at least 24 random characters')
app = FastAPI(docs_url=None, redoc_url=None)
slots = asyncio.Semaphore(2)
PREVIEW_ID = '202610010546486168eaab2eba77e41e6b46c45c8fb2f9abd'
RECONSTRUCTED_FILE = Path(os.environ.get('PICTORY_RECONSTRUCTED_FILE', str(Path(__file__).resolve().parent.parent / 'output/pictory-preview-reconstructed-720p.mp4')))

def reconstructed(url):
    return urlparse(url).hostname=='video.pictory.ai' and urlparse(url).path==f'/v2/preview/{PREVIEW_ID}' and RECONSTRUCTED_FILE.is_file()
HOSTS = {'youtube.com','www.youtube.com','m.youtube.com','youtu.be','instagram.com','www.instagram.com','twitter.com','www.twitter.com','x.com','www.x.com','facebook.com','www.facebook.com','m.facebook.com','fb.watch','video.pictory.ai'}

class Analyze(BaseModel):
    url: str = Field(max_length=2048)
class Download(BaseModel):
    token: str = Field(max_length=16000)
    quality: str = Field(max_length=120)

def auth(value):
    if not hmac.compare_digest(value or '', 'Bearer '+SECRET):
        raise HTTPException(401, 'Unauthorized')
def validate_url(url):
    p=urlparse(url)
    if p.scheme!='https' or p.hostname not in HOSTS or p.username or p.password or p.port not in (None,443):
        raise HTTPException(400, 'Use a public HTTPS video link from YouTube, Instagram, X, Facebook, or Pictory.')
    return p

def sign(data):
    payload=base64.urlsafe_b64encode(json.dumps({**data,'exp':int(time.time())+900},separators=(',',':')).encode()).decode().rstrip('=')
    sig=hmac.new(SECRET.encode(),payload.encode(),hashlib.sha256).hexdigest()
    return payload+'.'+sig

def unsign(token):
    try:
        payload,sig=token.rsplit('.',1)
        if not hmac.compare_digest(sig,hmac.new(SECRET.encode(),payload.encode(),hashlib.sha256).hexdigest()):
            raise ValueError()
        data=json.loads(base64.urlsafe_b64decode(payload+'='*(-len(payload)%4)))
        if data['exp']<time.time(): raise ValueError()
        return data
    except Exception:
        raise HTTPException(410,'This link expired. Check the video again.')

async def run(args, timeout=45):
    process=await asyncio.create_subprocess_exec('yt-dlp','--ignore-config','--js-runtimes','node','--no-playlist','--no-warnings','--socket-timeout','15','--retries','1',*args,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
    try:
        out,err=await asyncio.wait_for(process.communicate(),timeout)
    except (asyncio.TimeoutError,asyncio.CancelledError):
        process.kill(); await process.wait()
        raise HTTPException(504,'The source took too long. Try a shorter video or try again later.')
    if process.returncode:
        raise HTTPException(422,'This video is unavailable to the downloader. It may be private, restricted, or blocked by the platform.')
    return out

@app.get('/health')
def health(): return {'ok':True}

@app.post('/analyze')
async def analyze(body:Analyze, authorization:str|None=Header(default=None)):
    auth(authorization); parsed=validate_url(body.url)
    async with slots:
        if parsed.hostname=='video.pictory.ai':
            if not re.fullmatch(r'/v2/preview/[a-zA-Z0-9]+',parsed.path):
                raise HTTPException(400,'Use a Pictory public preview link.')
            if reconstructed(body.url):
                return {'title':'DATA NEBULA AI · reconstructed preview','platform':'Pictory','preview':f'{PUBLIC}/preview/{PREVIEW_ID}', 'formats':[{'id':'720','label':'720p · reconstructed preview MP4'}], 'token':sign({'url':body.url,'qualities':['720']}), 'message':'Download the locally reconstructed preview with scenes, narration, and music. Source watermarks remain. Title animation is simplified; this is not the original Pictory export. Preview clips may have lower native resolution than the 720p output.'}
            # A Pictory timeline is not a rendered MP4. Do not return individual stock clips as the complete video.
            return {'title':'Pictory project preview','platform':'Pictory','embed':body.url,'formats':[], 'message':'This link opens a Pictory project preview. Export the finished video in Pictory to download the complete video with its text, scenes, and audio.'}
        info=json.loads(await run(['--dump-single-json','--skip-download','--',body.url]))
    if info.get('_type') in ('playlist','multi_video'):
        raise HTTPException(422,'Paste a link to one video rather than a collection.')
    if info.get('is_live') or (info.get('duration') or 0)>1800:
        raise HTTPException(422,'Use a finished video shorter than 30 minutes.')
    formats=[f for f in info.get('formats',[]) if f.get('vcodec') not in (None,'none') and not f.get('has_drm')]
    if not formats: raise HTTPException(422,'No downloadable video formats were found.')
    heights=sorted({int(f['height']) for f in formats if f.get('height')},reverse=True)
    choices=[{'id':'original','label':'Best available · original quality'}]
    choices += [{'id':str(h),'label':f'{h}p'} for h in heights]
    progressive=[f for f in formats if f.get('acodec') not in (None,'none') and f.get('ext')=='mp4' and f.get('protocol') in ('https','http')]
    preview=max(progressive,key=lambda f:f.get('height') or 0).get('url') if progressive else None
    return {'title':info.get('title','Video'),'platform':info.get('extractor_key','Video'),'thumbnail':info.get('thumbnail'),'preview':preview,'duration':info.get('duration'),'formats':choices,'token':sign({'url':body.url,'qualities':[f['id'] for f in choices]}),'message':None if preview else 'An inline preview is unavailable for this source. You can still download an available quality.'}

@app.post('/download')
def download(body:Download,authorization:str|None=Header(default=None)):
    auth(authorization); data=unsign(body.token)
    if body.quality not in data.get('qualities',[]): raise HTTPException(400,'Choose an available quality.')
    ticket=sign({'url':data['url'],'quality':body.quality,'kind':'file'})
    return {'url':f'{PUBLIC}/file/{ticket}'}

@app.get('/file/{ticket}')
async def file(ticket:str):
    data=unsign(ticket)
    if data.get('kind')!='file': raise HTTPException(400,'Invalid download link')
    validate_url(data['url'])
    quality=data['quality']
    if quality!='original' and not str(quality).isdigit(): raise HTTPException(400,'Invalid quality')
    if reconstructed(data['url']):
        if quality!='720': raise HTTPException(400,'Only the reconstructed 720p file is available.')
        return FileResponse(RECONSTRUCTED_FILE,filename=RECONSTRUCTED_FILE.name,headers={'Cache-Control':'no-store'})
    selector='bv*+ba/b' if quality=='original' else f'bv*[height<={int(quality)}]+ba/b[height<={int(quality)}]'
    folder=tempfile.mkdtemp(prefix='linkdrop-')
    try:
        async with slots:
            await run(['--max-filesize','500M','--format',selector,'--merge-output-format','mp4','--output',folder+'/video.%(ext)s','--',data['url']],timeout=600)
        files=[p for p in Path(folder).iterdir() if p.suffix in ('.mp4','.webm','.mkv','.mov')]
        if not files: raise HTTPException(422,'The source did not provide a downloadable file within the 500 MB limit.')
        result=files[0]
        if result.stat().st_size>500*1024*1024: raise HTTPException(413,'The video exceeds the 500 MB download limit.')
        return FileResponse(result,filename='video'+result.suffix,background=BackgroundTask(shutil.rmtree,folder),headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer'})
    except BaseException:
        shutil.rmtree(folder,ignore_errors=True);raise

@app.get('/preview/{preview_id}')
def preview(preview_id:str):
    if preview_id != PREVIEW_ID or not RECONSTRUCTED_FILE.is_file(): raise HTTPException(404,'Reconstructed preview unavailable')
    return FileResponse(RECONSTRUCTED_FILE,media_type='video/mp4',headers={'Cache-Control':'no-store'})

@app.get('/download/pictory-preview.mp4')
def download_reconstructed_preview():
    if not RECONSTRUCTED_FILE.is_file(): raise HTTPException(404,'Reconstructed preview unavailable')
    return FileResponse(RECONSTRUCTED_FILE,media_type='video/mp4',filename=RECONSTRUCTED_FILE.name,headers={'Cache-Control':'no-store'})
