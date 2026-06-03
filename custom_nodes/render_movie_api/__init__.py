import os, uuid, subprocess, urllib.request
from server import PromptServer
from aiohttp import web

HERE = os.path.dirname(__file__)
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))   # ComfyUI root
OUTPUT = os.path.join(ROOT, 'output')
TEMP = os.path.join(ROOT, 'temp')
INPUT = os.path.join(ROOT, 'input')


def _find_font():
    cands = ['/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
             '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
             '/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf']
    for p in cands:
        if os.path.isfile(p):
            return p
    try:
        for r, _, fs in os.walk('/usr/share/fonts'):
            for f in fs:
                if f.lower().endswith('.ttf'):
                    return os.path.join(r, f)
    except Exception:
        pass
    return None

FONT = _find_font()


def _resolve(filename, subfolder, ftype):
    if not filename:
        return None
    bases = [OUTPUT, TEMP, INPUT]
    if ftype == 'temp':
        bases = [TEMP, OUTPUT, INPUT]
    elif ftype == 'input':
        bases = [INPUT, OUTPUT, TEMP]
    cands = []
    for b in bases:
        if subfolder:
            cands.append(os.path.join(b, subfolder, filename))
        cands.append(os.path.join(b, filename))
    for c in cands:
        if os.path.isfile(c):
            return c
    return None


def _download(url, dst):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'})
    with urllib.request.urlopen(req, timeout=90) as r, open(dst, 'wb') as f:
        f.write(r.read())


def _has_audio(path):
    try:
        r = subprocess.run(
            ['ffprobe', '-v', 'error', '-select_streams', 'a',
             '-show_entries', 'stream=index', '-of', 'csv=p=0', path],
            capture_output=True, text=True, timeout=30)
        return bool(r.stdout.strip())
    except Exception:
        return False


def _wrap(text, maxc=22, maxl=3):
    words = str(text).split()
    lines = []
    cur = ''
    for w in words:
        if len(cur) + len(w) + (1 if cur else 0) <= maxc:
            cur = (cur + ' ' + w).strip()
        else:
            if cur:
                lines.append(cur)
            cur = w
            if len(lines) >= maxl:
                break
    if cur and len(lines) < maxl:
        lines.append(cur)
    lines = lines[:maxl]
    used = ' '.join(lines)
    if len(used) < len(' '.join(words)):
        lines[-1] = lines[-1] + '...'
    return '\n'.join(lines)


def _sub_filter(text, work, idx, W, H):
    """Build a drawtext filter for a caption, or '' if none/unsupported."""
    if not text or not FONT:
        return ''
    txt = _wrap(text)
    if not txt.strip():
        return ''
    tf = os.path.join(work, 'sub%03d.txt' % idx)
    with open(tf, 'w') as f:
        f.write(txt)
    fs = max(34, H // 30)
    return ("drawtext=fontfile=%s:textfile=%s:fontcolor=white:fontsize=%d:"
            "box=1:boxcolor=black@0.5:boxborderw=16:line_spacing=8:"
            "x=(w-text_w)/2:y=h-text_h-%d") % (FONT, tf, fs, int(H * 0.10))


def _vf_base(W, H, FPS):
    return ("scale=%d:%d:force_original_aspect_ratio=decrease,"
            "pad=%d:%d:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=%d") % (W, H, W, H, FPS)


def _norm_video(src, dst, W, H, FPS, text=''):
    sub = _sub_filter(text, os.path.dirname(dst), abs(hash(dst)) % 1000, W, H)
    vf = _vf_base(W, H, FPS) + ((',' + sub) if sub else '') + ',format=yuv420p'
    enc = ['-r', str(FPS), '-c:v', 'libx264', '-preset', 'veryfast',
           '-crf', '20', '-pix_fmt', 'yuv420p',
           '-c:a', 'aac', '-ar', '44100', '-ac', '2', '-f', 'mpegts', dst]
    if _has_audio(src):
        cmd = ['ffmpeg', '-y', '-i', src, '-vf', vf] + enc
    else:
        cmd = ['ffmpeg', '-y', '-i', src,
               '-f', 'lavfi', '-i', 'anullsrc=channel_layout=stereo:sample_rate=44100',
               '-vf', vf, '-shortest'] + enc
    subprocess.run(cmd, check=True, capture_output=True, timeout=900)


def _norm_still(src, dst, sec, W, H, FPS, text=''):
    """Ken Burns slow zoom on a still (+ optional caption) -> mpegts segment."""
    sec = max(1.0, float(sec))
    frames = int(round(sec * FPS))
    sub = _sub_filter(text, os.path.dirname(dst), abs(hash(dst)) % 1000, W, H)
    kb = ("scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d,"
          "zoompan=z='min(zoom+0.0010,1.18)':d=%d:"
          "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=%dx%d:fps=%d,setsar=1") % (
              W, H, W, H, frames, W, H, FPS)
    vf = kb + ((',' + sub) if sub else '') + ',format=yuv420p'
    cmd = ['ffmpeg', '-y', '-i', src,
           '-f', 'lavfi', '-i', 'anullsrc=channel_layout=stereo:sample_rate=44100',
           '-vf', vf, '-t', str(sec), '-r', str(FPS),
           '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20', '-pix_fmt', 'yuv420p',
           '-c:a', 'aac', '-ar', '44100', '-ac', '2', '-f', 'mpegts', dst]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=600)
    except subprocess.CalledProcessError:
        # Fallback: static still (no Ken Burns) if zoompan fails on the host ffmpeg
        vf2 = _vf_base(W, H, FPS) + ((',' + sub) if sub else '') + ',format=yuv420p'
        cmd2 = ['ffmpeg', '-y', '-loop', '1', '-t', str(sec), '-i', src,
                '-f', 'lavfi', '-i', 'anullsrc=channel_layout=stereo:sample_rate=44100',
                '-vf', vf2, '-shortest', '-r', str(FPS),
                '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20', '-pix_fmt', 'yuv420p',
                '-c:a', 'aac', '-ar', '44100', '-ac', '2', '-f', 'mpegts', dst]
        subprocess.run(cmd2, check=True, capture_output=True, timeout=300)


@PromptServer.instance.routes.post('/render_movie')
async def _render_movie(req):
    """Assemble talking-head clips (+ Ken Burns still scenes, + captions) into one vertical mp4.

    Body: { width, height, fps, output, scenes: [
        {"type":"video","filename":"..","subfolder":"","ftype":"temp","text":"caption"},
        {"type":"still","image_url":"https://..jpg","sec":6,"text":"caption"} ] }
    """
    try:
        d = await req.json()
    except Exception:
        d = {}
    W = int(d.get('width', 1080)); H = int(d.get('height', 1920)); FPS = int(d.get('fps', 25))
    scenes = d.get('scenes') or []
    os.makedirs(OUTPUT, exist_ok=True)
    work = os.path.join(OUTPUT, 'rm_' + uuid.uuid4().hex[:8])
    os.makedirs(work, exist_ok=True)
    parts = []; errors = []
    try:
        for i, s in enumerate(scenes):
            dst = os.path.join(work, 'n%03d.ts' % i)
            typ = (s.get('type') or 'video').lower()
            text = s.get('text') or s.get('caption') or ''
            try:
                if typ == 'video':
                    src = _resolve(s.get('filename') or s.get('file') or '',
                                   s.get('subfolder') or '',
                                   s.get('ftype') or s.get('typ') or 'temp')
                    if not src:
                        errors.append('scene %d: clip not found: %s' % (i, s.get('filename')))
                        continue
                    _norm_video(src, dst, W, H, FPS, text)
                else:
                    img = s.get('image_url') or s.get('image') or s.get('file') or ''
                    local = img
                    if isinstance(img, str) and img.startswith('http'):
                        local = os.path.join(work, 'img%03d' % i)
                        _download(img, local)
                    if not local or not os.path.exists(local):
                        errors.append('scene %d: still image missing' % i)
                        continue
                    sec = float(s.get('sec') or s.get('duration') or 6)
                    _norm_still(local, dst, sec, W, H, FPS, text)
                parts.append(dst)
            except Exception as se:
                errors.append('scene %d (%s) skipped: %s' % (i, typ, str(se)[:160]))
                continue

        if not parts:
            return web.json_response({'error': 'no_renderable_scenes', 'details': errors}, status=500)

        outname = d.get('output') or ('movie_' + uuid.uuid4().hex[:10] + '.mp4')
        if not outname.lower().endswith('.mp4'):
            outname += '.mp4'
        outpath = os.path.join(OUTPUT, outname)
        listfile = os.path.join(work, 'list.txt')
        with open(listfile, 'w') as f:
            for p in parts:
                f.write("file '%s'\n" % p)
        subprocess.run(
            ['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', listfile,
             '-c', 'copy', '-bsf:a', 'aac_adtstoasc', '-movflags', '+faststart', outpath],
            check=True, capture_output=True, timeout=600)
        return web.json_response({'filename': outname, 'subfolder': '', 'type': 'output',
                                  'scenes': len(parts), 'errors': errors})
    except subprocess.CalledProcessError as e:
        err = e.stderr or b''
        if isinstance(err, bytes):
            err = err.decode('utf-8', 'ignore')
        return web.json_response({'error': 'ffmpeg_failed', 'stderr': err[-1200:]}, status=500)
    except Exception as e:
        return web.json_response({'error': str(e)}, status=500)


NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}
