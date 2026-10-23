# -*- coding: utf-8 -*-
# by @嗷呜
import base64
import hashlib
import json
import os
import re
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import quote, unquote, urlparse, parse_qs
sys.path.append('..')
try:
    from base.spider import Spider
except ImportError:
    class Spider:
        pass
try:
    import requests
except Exception:
    requests = None
HOST = "https://55666.hpdztro0rdqb.cc/home"
DATA = "https://tjqzku.ymz16835.com"
CFG_PATH = "/data/config/base-1.js"
MEDIA = "https://cf-worker-r2.mtzionhub.com"
IMG = "https://m3m.1vkx.cn"
IMG2 = "https://wzzqlm.erbaiwulaoge.com"
API = "https://ma0m1ss3a5chap.621g3uxa.com"
SR = "hIAUOQEWOOw1IW0983U93iXfV09"
SK = "D7hGKHnWThaECaQ3ji4XyAF3MfYKJ53M"
UA = "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Mobile Safari/537.36"
KEYB64 = "SWRUSnEwSGtscHVJNm11OGlCJU9PQCF2ZF40SyZ1WFc="
IVB64 = "JDB2QGtySDdWMg=="
SIGNKEY = base64.b64decode("JkI2OG1AJXpnMzJfJXUqdkhVbEU0V2tTJjFKNiUleG1VQGZO").decode()
_PATH_PREFIX = "gt6ikshg458mns4f"


def _b64url(path):
    """数据站路径加密：base64(站点前缀+明文路径)"""
    return base64.b64encode((_PATH_PREFIX + path).encode()).decode()
CATEGORIES = {
    "dsp": "短视频区", "mnzb": "美女主播", "gcjp": "国产精品", "zwzm": "中文字幕",
    "yzwm": "亚洲无码", "omjp": "欧美精品", "crdm": "成人动漫", "nyzq": "女优专区",
    "mmtj": "VIP猫咪推荐", "ycgc": "VIP原创国产", "zfyx": "VIP制服淫穴",
    "hlaiq": "VIP换脸AI区", "sjzy": "VIP三级综艺", "cydm": "VIP次元动漫",
    "omdp": "VIP欧美大片", "txzq": "VIP同性恋区",
}
_CH = {k: "shipin" for k in ("dsp", "mnzb", "gcjp", "zwzm", "yzwm", "omjp", "crdm", "nyzq")}
_CH.update({k: "vip" for k in ("mmtj", "ycgc", "zfyx", "hlaiq", "sjzy", "cydm", "omdp", "txzq")})
DEF_PIC = "https://1fvy0.cc/apple-touch-icon-180.png"


def _diag(msg):
    try:
        with open("/sdcard/Download/1fvy0_diag.txt", "a") as f:
            f.write(time.strftime("%m-%d %H:%M:%S") + " " + msg + "\n")
    except Exception:
        pass


_IMGCACHE = {}
_IMGBASES = (IMG, IMG2, "https://catsta.tingqian.top/public/1")


def _parse_img(c):
    if c.startswith(b"data:"):
        bm = re.search(rb"base64,([A-Za-z0-9+/=]+)", c)
        if not bm:
            return None
        try:
            c = base64.b64decode(bm.group(1))
        except Exception:
            return None
    if c[:3] == b"\xff\xd8\xff":
        return c, "image/jpeg"
    if c[:4] == b"\x89PNG":
        return c, "image/png"
    if c[:4] == b"RIFF" and c[8:12] == b"WEBP":
        return c, "image/webp"
    if c[:3] == b"GIF":
        return c, "image/gif"
    return None


def _dl_img(u):
    if u in _IMGCACHE:
        return _IMGCACHE[u]
    if requests is None:
        return None
    m = re.match(r"^(https?://[^/]+)(/.*)$", u)
    path = m.group(2) if m else ""
    cands = [u] + [b + path for b in _IMGBASES[1:] if path]
    out = [None]

    def _try(cu):
        try:
            r = requests.get(cu, headers={"User-Agent": UA, "Referer": HOST + "/", "Accept": "image/*"}, verify=False, timeout=5)
            if r.status_code == 200 and r.content:
                p = _parse_img(r.content)
                if p and out[0] is None:
                    out[0] = p
        except Exception:
            pass

    ts = [threading.Thread(target=_try, args=(c,)) for c in cands[:3]]
    for t in ts:
        t.start()
    for t in ts:
        t.join(8)
    if out[0]:
        _IMGCACHE[u] = out[0]
        if len(_IMGCACHE) > 300:
            for k in list(_IMGCACHE)[:150]:
                del _IMGCACHE[k]
    return out[0]


_SRV = {"port": 0}


class _ImgH(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            q = parse_qs(urlparse(self.path).query)
            u = q.get("url", [""])[0]
            if not u or not u.startswith("http"):
                self.send_error(400)
                return
            r = _dl_img(u)
            if not r:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", r[1])
            self.send_header("Content-Length", str(len(r[0])))
            self.send_header("Cache-Control", "max-age=86400")
            self.end_headers()
            self.wfile.write(r[0])
        except Exception:
            self.send_error(502)

    def log_message(self, *a):
        pass


def _start_srv():
    if _SRV["port"]:
        return _SRV["port"]
    for p in range(9978, 9988):
        try:
            srv = ThreadingHTTPServer(("127.0.0.1", p), _ImgH)
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            _SRV["port"] = p
            _diag("SRV OK port=%d" % p)
            return p
        except Exception:
            continue
    _diag("SRV FAIL all ports busy")
    return 0


_SB = [99,124,119,123,242,107,111,197,48,1,103,43,254,215,171,118,202,130,201,125,250,89,71,240,173,212,162,175,156,164,114,192,183,253,147,38,54,63,247,204,52,165,229,241,113,216,49,21,4,199,35,195,24,150,5,154,7,18,128,226,235,39,178,117,9,131,44,26,27,110,90,160,82,59,214,179,41,227,47,132,83,209,0,237,32,252,177,91,106,203,190,57,74,76,88,207,208,239,170,251,67,77,51,133,69,249,2,127,80,60,159,168,81,163,64,143,146,157,56,245,188,182,218,33,16,255,243,210,205,12,19,236,95,151,68,23,196,167,126,61,100,93,25,115,96,129,79,220,34,42,144,136,70,238,184,20,222,94,11,219,224,50,58,10,73,6,36,92,194,211,172,98,145,149,228,121,231,200,55,109,141,213,78,169,108,86,244,234,101,122,174,8,186,120,37,46,28,166,180,198,232,221,116,31,75,189,139,138,112,62,181,102,72,3,246,14,97,53,87,185,134,193,29,158,225,248,152,17,105,217,142,148,155,30,135,233,206,85,40,223,140,161,137,13,191,230,66,104,65,153,45,15,176,84,187,22]
_RSB = [0] * 256
for _i, _v in enumerate(_SB):
    _RSB[_v] = _i


def _aes_key_expand(key):
    nk = len(key) // 4
    nr = nk + 6
    w = [list(key[4 * i:4 * i + 4]) for i in range(nk)]
    rcon = 1
    for i in range(nk, 4 * (nr + 1)):
        t = list(w[i - 1])
        if i % nk == 0:
            t = t[1:] + t[:1]
            t = [_SB[x] for x in t]
            t[0] ^= rcon
            rcon = (rcon << 1) ^ (0x11B if rcon & 0x80 else 0)
        elif nk > 6 and i % nk == 4:
            t = [_SB[x] for x in t]
        w.append([w[i - nk][j] ^ t[j] for j in range(4)])
    return w, nr


def _gfmul(a, b):
    p = 0
    for _ in range(8):
        if b & 1:
            p ^= a
        hi = a & 0x80
        a = (a << 1) & 0xFF
        if hi:
            a ^= 0x1B
        b >>= 1
    return p


def _aes_dec_block(blk, w, nr):
    def add_round(rnd):
        for c in range(4):
            for r in range(4):
                st[r][c] ^= w[rnd * 4 + c][r]

    st = [[blk[r + 4 * c] for c in range(4)] for r in range(4)]
    add_round(nr)
    for rnd in range(nr - 1, 0, -1):
        for r in range(4):
            st[r] = st[r][-r:] + st[r][:-r]
        for c in range(4):
            for r in range(4):
                st[r][c] = _RSB[st[r][c]]
        add_round(rnd)
        for c in range(4):
            s0, s1, s2, s3 = st[0][c], st[1][c], st[2][c], st[3][c]
            st[0][c] = _gfmul(s0, 14) ^ _gfmul(s1, 11) ^ _gfmul(s2, 13) ^ _gfmul(s3, 9)
            st[1][c] = _gfmul(s0, 9) ^ _gfmul(s1, 14) ^ _gfmul(s2, 11) ^ _gfmul(s3, 13)
            st[2][c] = _gfmul(s0, 13) ^ _gfmul(s1, 9) ^ _gfmul(s2, 14) ^ _gfmul(s3, 11)
            st[3][c] = _gfmul(s0, 11) ^ _gfmul(s1, 13) ^ _gfmul(s2, 9) ^ _gfmul(s3, 14)
    for r in range(4):
        st[r] = st[r][-r:] + st[r][:-r]
    for c in range(4):
        for r in range(4):
            st[r][c] = _RSB[st[r][c]]
    add_round(0)
    out = bytearray(16)
    for c in range(4):
        for r in range(4):
            out[r + 4 * c] = st[r][c]
    return bytes(out)


def _aes_pure(data, key, iv):
    w, nr = _aes_key_expand(key)
    prev = iv
    out = bytearray()
    for i in range(0, len(data), 16):
        blk = _aes_dec_block(data[i:i + 16], w, nr)
        out += bytes(b ^ p for b, p in zip(blk, prev))
        prev = data[i:i + 16]
    pad = out[-1]
    return bytes(out[:-pad])


def _dec(data, sf="123456"):
    try:
        from Crypto.Cipher import AES
        from Crypto.Util.Padding import unpad
        k = base64.b64decode(KEYB64)
        iv = base64.b64decode(IVB64) + sf.encode()
        raw = base64.b64decode(data)
        if raw[:8] == b"Salted__":
            raw = raw[16:]
        return unpad(AES.new(k, AES.MODE_CBC, iv).decrypt(raw), 16).decode()
    except Exception:
        try:
            from javax.crypto import Cipher
            from javax.crypto.spec import SecretKeySpec, IvParameterSpec
            k = SecretKeySpec(base64.b64decode(KEYB64), "AES")
            iv = IvParameterSpec(base64.b64decode(IVB64) + sf.encode())
            c = Cipher.getInstance("AES/CBC/PKCS5Padding")
            c.init(2, k, iv)
            raw = base64.b64decode(data)
            if raw[:8] == b"Salted__":
                raw = raw[16:]
            return bytes(c.doFinal(raw)).decode()
        except Exception:
            try:
                raw = base64.b64decode(data)
                if raw[:8] == b"Salted__":
                    raw = raw[16:]
                return _aes_pure(raw, base64.b64decode(KEYB64), base64.b64decode(IVB64) + sf.encode()).decode()
            except Exception:
                return ""


def _enc(data, sf="123456"):
    try:
        from Crypto.Cipher import AES
        from Crypto.Util.Padding import pad
        k = base64.b64decode(KEYB64)
        iv = base64.b64decode(IVB64) + sf.encode()
        c = AES.new(k, AES.MODE_CBC, iv)
        return base64.b64encode(c.encrypt(pad(data.encode(), 16))).decode()
    except Exception:
        try:
            from javax.crypto import Cipher
            from javax.crypto.spec import SecretKeySpec, IvParameterSpec
            k = SecretKeySpec(base64.b64decode(KEYB64), "AES")
            iv = IvParameterSpec(base64.b64decode(IVB64) + sf.encode())
            c = Cipher.getInstance("AES/CBC/PKCS5Padding")
            c.init(1, k, iv)
            raw = bytes(c.doFinal(data.encode()))
            return base64.b64encode(raw).decode()
        except Exception:
            return ""


def _sign(params):
    p = dict(sorted(params.items()))
    s = "".join(k + "=" + str(v) + "&" for k, v in p.items())
    return hashlib.md5((s + SIGNKEY).encode()).hexdigest()


class Spider(Spider):
    def init(self, extend=""):
        self._h = {"User-Agent": UA, "Referer": HOST + "/"}
        self._hc = {}
        self._data, self._img, self._media, self._api = DATA, IMG, MEDIA, API
        try:
            j = self._get(CFG_PATH)
            if isinstance(j, dict):
                cfg = j.get("config") or {}
                self._data = (cfg.get("json_host") or DATA).rstrip("/")
                self._img = j.get("image_url") or j.get("img_host") or IMG
                self._media = j.get("m3u8_host_encrypt") or MEDIA
        except Exception:
            pass

    def _get(self, path):
        if requests is None:
            return None
        try:
            if path in self._hc and time.time() - self._hc[path][0] < 60:
                return self._hc[path][1]
            url = "%s/%s" % (self._data, _b64url(path))
            r = requests.get(url, headers=self._h, verify=False, timeout=(3.05, 12))
            j = None
            try:
                j = r.json()
            except Exception:
                return None
            if isinstance(j, dict) and j.get("data"):
                txt = _dec(str(j["data"]), str(j.get("suffix", "123456")))
                try:
                    d = json.loads(txt)
                    self._hc[path] = (time.time(), d)
                    if len(self._hc) > 60:
                        self._hc = dict(list(self._hc.items())[-40:])
                    return d
                except Exception:
                    return None
            return None
        except Exception:
            return None

    def _pic(self, p):
        if not p:
            return DEF_PIC
        u = p if p.startswith("http") else self._img + p
        port = _start_srv()
        if port:
            return "http://127.0.0.1:%d/img?url=%s" % (port, quote(u, safe=""))
        return "http://127.0.0.1:9978/proxy?do=pic&url=" + quote(u, safe="")

    def _fetch_img(self, u):
        return _dl_img(u)
    def _vkey(self, path):
        a = int(time.time()) + 300
        k = hashlib.md5((SK + path + str(a)).encode()).hexdigest()
        return "?wsSecret=" + k + "&wsTime=" + str(a) + "&ip="
    def _pkey(self, path):
        t = format(int(time.time()), "x")
        k = hashlib.md5((SR + path.replace("//", "/") + t).encode()).hexdigest()
        return "?key=" + k + "&t=" + t

    def _fmt(self, it):
        return {
            "vod_id": str(it.get("id", "")),
            "vod_name": it.get("title", ""),
            "vod_pic": self._pic(it.get("thumb") or it.get("thumb_ori")),
            "vod_remarks": it.get("duration") or it.get("tags") or "",
        }

    def homeContent(self, filter=False):
        return {"class": [{"type_id": k, "type_name": v} for k, v in CATEGORIES.items()], "list": []}

    def homeVideoContent(self):
        try:
            d = self._get("/data/index/homeV2.js")
            if not d:
                return {"list": []}
            seen, out = set(), []
            for key in ("japanese_av_list", "world_cup_special_list", "domestic_media_list",
                        "adult_anime_list", "uncensored_asia_list", "beauty_anchor_list"):
                for it in (d.get(key) or {}).get("data", []) or []:
                    if it.get("id") in seen:
                        continue
                    seen.add(it.get("id"))
                    out.append(self._fmt(it))
                    if len(out) >= 80:
                        return {"list": out}
            return {"list": out}
        except Exception:
            return {"list": []}

    def categoryContent(self, tid, pg=1, filter=False, extend=""):
        try:
            pn = max(int(str(pg)), 1)
        except Exception:
            pn = 1
        try:
            name = str(tid).split(",")[0]
            ch = _CH.get(name, "shipin")
            d = self._get("/data/list/base-%s-%s-%s.js" % (ch, name, pn))
            if not d:
                return {"list": []}
            return {"list": [self._fmt(it) for it in (d.get("list") or {}).get("data", []) or []]}
        except Exception:
            return {"list": []}

    def detailContent(self, ids):
        try:
            vid = re.search(r"\d+", str(ids))
            vid = vid.group(0) if vid else ""
            d = self._get("/data/shipin/detail-" + vid + ".js")
            if not d:
                _diag("detail EMPTY ids=" + str(ids)[:60] + " vid=" + vid)
                return {"list": []}
            info = d.get("info") or {}
            src = d.get("source") or {}
            media = (self._media or src.get("m3u8_host") or "").rstrip("/")
            vurl = info.get("video_url", "")
            durl = info.get("down_url", "") or ""
            if vurl:
                vurl = media + vurl + self._vkey(vurl)
            if durl:
                p = re.sub(r"^https?://[^/]+", "", durl)
                durl = media + p + self._pkey(p)
            if vurl:
                play_from = "hls$$$mp4" if durl and durl != vurl else "hls"
                play_url = "全集$" + vurl
                if durl and durl != vurl:
                    play_url += "#全集$" + durl
            else:
                play_from, play_url = "", ""
            vod = {
                "vod_id": vid,
                "vod_name": info.get("title", ""),
                "vod_pic": self._pic(info.get("thumb") or info.get("thumb_ori")),
                "vod_content": (info.get("description") or info.get("content") or "").replace("\n", ""),
                "vod_play_from": play_from,
                "vod_play_url": play_url,
                "vod_year": str(info.get("publish_time", ""))[:4],
                "vod_actor": ",".join(info.get("actors") or []),
            }
            return {"list": [vod]}
        except Exception:
            return {"list": []}

    def searchContent(self, keyword, quick=False):
        try:
            p = {"page": "1", "q": str(keyword), "system": 2,
                 "timestamp": str(int(time.time())), "device": "mobile"}
            p["encode_sign"] = _sign(p)
            body = {"post-data": _enc(json.dumps(p))}
            h = dict(self._h)
            h["Content-Type"] = "application/json"
            h["suffix"] = "123456"
            try:
                r = requests.post(self._api + "/search", data=json.dumps(body),
                                  headers=h, verify=False, timeout=10)
                if r.status_code != 200:
                    return {"list": []}
                j = r.json()
                if not j.get("data"):
                    return {"list": []}
                d = json.loads(_dec(str(j["data"]), str(j.get("suffix", "123456"))))
                items = (d or {}).get("list") or []
                return {"list": [self._fmt(it) for it in items]}
            except Exception:
                return {"list": []}
        except Exception:
            return {"list": []}

    def playerContent(self, flag, id, vipFlags=None):
        url = str(id) if id else str(flag)
        if not url.startswith("http"):
            url = self._media + url
        return {"parse": 0, "url": url}

    def localProxy(self, param):
        try:
            u = param.get("url") if isinstance(param, dict) else str(param)
            if not u:
                return [404, "text/plain", ""]
            u = unquote(u)
            if "url=" in u:
                m = re.search(r"url=([^&]+)", u)
                if m:
                    u = unquote(m.group(1))
            if not u.startswith("http"):
                return [404, "text/plain", ""]
            r = self._fetch_img(u)
            if not r:
                return [404, "text/plain", ""]
            return [200, r[1], r[0]]
        except Exception:
            return [404, "text/plain", ""]
