import os, uuid, subprocess, urllib.request
from server import PromptServer
from aiohttp import web

HERE = os.path.dirname(__file__)
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))   # ComfyUI root
OUTPUT = os.path.join(ROOT, 'output')
TEMP = os.path.join(ROOT, 'temp')
INPUT = os.path.join(ROOT, 'input')

VF = ("scale=%d:%d:force_original_aspect_ratio=decrease,"
      "pad=%d:%d:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=%d,format=yuv420p")


def _resolve(filename, subfolder, ftype):
    """Find a clip file produced by ComfyUI (output/temp/input)."""
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


def _norm_video(src, dst, W, H, FPS):
    vf = VF % (W, H, W, H, FPS)
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


def _norm_still(src, dst, sec, W, H, FPS):
    vf = VF % (W, H, W, H, FPS)
    cmd = ['ffmpeg', '-y', '-loop', '1', '-t', str(sec), '-i', src,
           '-f', 'lavfi', '-i', 'anullsrc=channel_layout=stereo:sample_rate=44100',
           '-vf', vf, '-shortest',
           '-r', str(FPS), '-c:v', 'libx264', '-preset', 'veryfast',
           '-crf', '20', '-pix_fmt', 'yuv420p',
           '-c:a', 'aac', '-ar', '44100', '-ac', '2', '-f', 'mpegts', dst]
    subprocess.run(cmd, check=True, capture_output=True, timeout=300)


@PromptServer.instance.routes.post('/render_movie')
async def _render_movie(req):
    """Assemble talking-head clips (+ still scenes) into one vertical mp4 via ffmpeg.

    Body: {
      width, height, fps,
      output: "movie_x.mp4",
      scenes: [
        {"type":"video","filename":"WanVideo_x.mp4","subfolder":"","ftype":"temp"},
        {"type":"still","image_url":"https://...jpg","sec":12}
      ]
    }
    Returns {filename, subfolder, type:"output", scenes, errors} or {error,...}.
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
            try:
                if typ == 'video':
                    src = _resolve(s.get('filename') or s.get('file') or '',
                                   s.get('subfolder') or '',
                                   s.get('ftype') or s.get('typ') or 'temp')
                    if not src:
                        errors.append('scene %d: clip not found: %s' % (i, s.get('filename')))
                        continue
                    _norm_video(src, dst, W, H, FPS)
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
                    _norm_still(local, dst, sec, W, H, FPS)
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
