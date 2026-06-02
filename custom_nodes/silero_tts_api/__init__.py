import os, uuid, wave, threading
import numpy as np, torch
from server import PromptServer
from aiohttp import web

_lock=threading.Lock(); _model=None
def _get():
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                dev=torch.device('cuda' if torch.cuda.is_available() else 'cpu')
                m,_=torch.hub.load('snakers4/silero-models','silero_tts',language='ru',speaker='v4_ru',trust_repo=True)
                m.to(dev); _model=m
    return _model

HERE=os.path.dirname(__file__)
INPUT=os.path.abspath(os.path.join(HERE,'..','..','input'))
SPK={'aidar','baya','kseniya','xenia','eugene'}

@PromptServer.instance.routes.post('/silero_tts')
async def _silero(req):
    try: d=await req.json()
    except Exception: d={}
    text=(d.get('text') or '').strip() or '\u043f\u0440\u0438\u0432\u0435\u0442'
    speaker=d.get('speaker') or 'eugene'
    if speaker not in SPK: speaker='eugene'
    sr=48000
    try:
        m=_get()
        a=m.apply_tts(text=text[:980], speaker=speaker, sample_rate=sr, put_accent=True, put_yo=True)
        os.makedirs(INPUT, exist_ok=True)
        fn='tts_'+uuid.uuid4().hex[:12]+'.wav'
        pcm=np.clip(a.detach().cpu().numpy(),-1,1); pcm=(pcm*32767).astype('<i2')
        with wave.open(os.path.join(INPUT,fn),'wb') as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes(pcm.tobytes())
        return web.json_response({'filename':fn,'speaker':speaker})
    except Exception as e:
        return web.json_response({'error':str(e)}, status=500)

NODE_CLASS_MAPPINGS={}; NODE_DISPLAY_NAME_MAPPINGS={}
