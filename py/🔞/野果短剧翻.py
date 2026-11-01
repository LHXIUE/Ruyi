# -*- coding: utf-8 -*-
# 807916734
"""
野果短剧 (belief.callawtj.cc) —— TVBox / EasyTV 爬虫源
=================================================
站点为 Nuxt3 SPA：列表/分类/搜索走前端 SSR(无盾)；详情与播放走后端 API。

"""

import base64
import json
import re
import ssl
import struct
import urllib.request
import urllib.parse

try:
    import requests
    HAS_REQUESTS = True
except Exception:
    requests = None
    HAS_REQUESTS = False

try:
    import sys
    sys.path.append("..")
    from base.spider import Spider as _BaseSpider
except Exception:
    _BaseSpider = None


# ============================================================
# 纯 Python AES-128-CBC 解密（无第三方依赖，适配 Chaquopy/Android）
# ============================================================
_SBOX = [
    0x63,0x7c,0x77,0x7b,0xf2,0x6b,0x6f,0xc5,0x30,0x01,0x67,0x2b,0xfe,0xd7,0xab,0x76,
    0xca,0x82,0xc9,0x7d,0xfa,0x59,0x47,0xf0,0xad,0xd4,0xa2,0xaf,0x9c,0xa4,0x72,0xc0,
    0xb7,0xfd,0x93,0x26,0x36,0x3f,0xf7,0xcc,0x34,0xa5,0xe5,0xf1,0x71,0xd8,0x31,0x15,
    0x04,0xc7,0x23,0xc3,0x18,0x96,0x05,0x9a,0x07,0x12,0x80,0xe2,0xeb,0x27,0xb2,0x75,
    0x09,0x83,0x2c,0x1a,0x1b,0x6e,0x5a,0xa0,0x52,0x3b,0xd6,0xb3,0x29,0xe3,0x2f,0x84,
    0x53,0xd1,0x00,0xed,0x20,0xfc,0xb1,0x5b,0x6a,0xcb,0xbe,0x39,0x4a,0x4c,0x58,0xcf,
    0xd0,0xef,0xaa,0xfb,0x43,0x4d,0x33,0x85,0x45,0xf9,0x02,0x7f,0x50,0x3c,0x9f,0xa8,
    0x51,0xa3,0x40,0x8f,0x92,0x9d,0x38,0xf5,0xbc,0xb6,0xda,0x21,0x10,0xff,0xf3,0xd2,
    0xcd,0x0c,0x13,0xec,0x5f,0x97,0x44,0x17,0xc4,0xa7,0x7e,0x3d,0x64,0x5d,0x19,0x73,
    0x60,0x81,0x4f,0xdc,0x22,0x2a,0x90,0x88,0x46,0xee,0xb8,0x14,0xde,0x5e,0x0b,0xdb,
    0xe0,0x32,0x3a,0x0a,0x49,0x06,0x24,0x5c,0xc2,0xd3,0xac,0x62,0x91,0x95,0xe4,0x79,
    0xe7,0xc8,0x37,0x6d,0x8d,0xd5,0x4e,0xa9,0x6c,0x56,0xf4,0xea,0x65,0x7a,0xae,0x08,
    0xba,0x78,0x25,0x2e,0x1c,0xa6,0xb4,0xc6,0xe8,0xdd,0x74,0x1f,0x4b,0xbd,0x8b,0x8a,
    0x70,0x3e,0xb5,0x66,0x48,0x03,0xf6,0x0e,0x61,0x35,0x57,0xb9,0x86,0xc1,0x1d,0x9e,
    0xe1,0xf8,0x98,0x11,0x69,0xd9,0x8e,0x94,0x9b,0x1e,0x87,0xe9,0xce,0x55,0x28,0xdf,
    0x8c,0xa1,0x89,0x0d,0xbf,0xe6,0x42,0x68,0x41,0x99,0x2d,0x0f,0xb0,0x54,0xbb,0x16,
]
_RCON = [0x01,0x02,0x04,0x08,0x10,0x20,0x40,0x80,0x1b,0x36]

# 逆 S 盒（InvSubBytes 使用，不能直接用 _SBOX）
_INV_SBOX = [
    0x52,0x09,0x6a,0xd5,0x30,0x36,0xa5,0x38,0xbf,0x40,0xa3,0x9e,0x81,0xf3,0xd7,0xfb,
    0x7c,0xe3,0x39,0x82,0x9b,0x2f,0xff,0x87,0x34,0x8e,0x43,0x44,0xc4,0xde,0xe9,0xcb,
    0x54,0x7b,0x94,0x32,0xa6,0xc2,0x23,0x3d,0xee,0x4c,0x95,0x0b,0x42,0xfa,0xc3,0x4e,
    0x08,0x2e,0xa1,0x66,0x28,0xd9,0x24,0xb2,0x76,0x5b,0xa2,0x49,0x6d,0x8b,0xd1,0x25,
    0x72,0xf8,0xf6,0x64,0x86,0x68,0x98,0x16,0xd4,0xa4,0x5c,0xcc,0x5d,0x65,0xb6,0x92,
    0x6c,0x70,0x48,0x50,0xfd,0xed,0xb9,0xda,0x5e,0x15,0x46,0x57,0xa7,0x8d,0x9d,0x84,
    0x90,0xd8,0xab,0x00,0x8c,0xbc,0xd3,0x0a,0xf7,0xe4,0x58,0x05,0xb8,0xb3,0x45,0x06,
    0xd0,0x2c,0x1e,0x8f,0xca,0x3f,0x0f,0x02,0xc1,0xaf,0xbd,0x03,0x01,0x13,0x8a,0x6b,
    0x3a,0x91,0x11,0x41,0x4f,0x67,0xdc,0xea,0x97,0xf2,0xcf,0xce,0xf0,0xb4,0xe6,0x73,
    0x96,0xac,0x74,0x22,0xe7,0xad,0x35,0x85,0xe2,0xf9,0x37,0xe8,0x1c,0x75,0xdf,0x6e,
    0x47,0xf1,0x1a,0x71,0x1d,0x29,0xc5,0x89,0x6f,0xb7,0x62,0x0e,0xaa,0x18,0xbe,0x1b,
    0xfc,0x56,0x3e,0x4b,0xc6,0xd2,0x79,0x20,0x9a,0xdb,0xc0,0xfe,0x78,0xcd,0x5a,0xf4,
    0x1f,0xdd,0xa8,0x33,0x88,0x07,0xc7,0x31,0xb1,0x12,0x10,0x59,0x27,0x80,0xec,0x5f,
    0x60,0x51,0x7f,0xa9,0x19,0xb5,0x4a,0x0d,0x2d,0xe5,0x7a,0x9f,0x93,0xc9,0x9c,0xef,
    0xa0,0xe0,0x3b,0x4d,0xae,0x2a,0xf5,0xb0,0xc8,0xeb,0xbb,0x3c,0x83,0x53,0x99,0x61,
    0x17,0x2b,0x04,0x7e,0xba,0x77,0xd6,0x26,0xe1,0x69,0x14,0x63,0x55,0x21,0x0c,0x7d,
]


def _keyexp(key):
    Nk = len(key) // 4
    w = [list(key[4*i:4*i+4]) for i in range(Nk)]
    for i in range(Nk, 44):
        temp = list(w[i-1])
        if i % Nk == 0:
            temp = temp[1:] + temp[:1]
            temp = [_SBOX[b] for b in temp]
            temp[0] ^= _RCON[i//Nk - 1]
        elif Nk > 6 and i % Nk == 4:
            temp = [_SBOX[b] for b in temp]
        w.append([w[i-Nk][j] ^ temp[j] for j in range(4)])
    return w


def _xtime(a):
    a <<= 1
    if a & 0x100:
        a ^= 0x11b
    return a & 0xff


def _gmul(a, b):
    p = 0
    for _ in range(8):
        if b & 1:
            p ^= a
        hi = a & 0x80
        a = (a << 1) & 0xff
        if hi:
            a ^= 0x1b
        b >>= 1
    return p & 0xff


def _dec_block(key, block):
    # AES-128 单块解密（FIPS-197 逆轮，列主序 state[r][c]）
    # 逆轮结构：A10 -> InvShift -> InvSub -> [A9,InvMix,InvShift,InvSub] -> ... -> A0
    Nr = 10
    w = _keyexp(key)
    # 载入为列主序：state[r][c] = block[r + 4*c]
    state = [[block[r + 4*c] for c in range(4)] for r in range(4)]

    def _ark(rk):
        for r in range(4):
            for c in range(4):
                state[r][c] ^= w[4*rk + c][r]

    def _ishift():
        for r in range(4):
            state[r] = [state[r][(c - r) % 4] for c in range(4)]

    def _isub():
        for r in range(4):
            for c in range(4):
                state[r][c] = _INV_SBOX[state[r][c]]

    def _imix():
        ns = [[0] * 4 for _ in range(4)]
        for c in range(4):
            col = [state[r][c] for r in range(4)]
            ns[0][c] = _gmul(col[0],14)^_gmul(col[1],11)^_gmul(col[2],13)^_gmul(col[3],9)
            ns[1][c] = _gmul(col[0],9)^_gmul(col[1],14)^_gmul(col[2],11)^_gmul(col[3],13)
            ns[2][c] = _gmul(col[0],13)^_gmul(col[1],9)^_gmul(col[2],14)^_gmul(col[3],11)
            ns[3][c] = _gmul(col[0],11)^_gmul(col[1],13)^_gmul(col[2],9)^_gmul(col[3],14)
        for r in range(4):
            state[r] = ns[r][:]

    # 初始 AddRoundKey(第 Nr 轮)
    _ark(Nr)
    # 末轮（无 InvMixColumns）：InvShiftRows + InvSubBytes
    _ishift()
    _isub()
    # 中间轮 9..1：AddRoundKey -> InvMixColumns -> InvShiftRows -> InvSubBytes
    for rnd in range(Nr-1, 0, -1):
        _ark(rnd)
        _imix()
        _ishift()
        _isub()
    # 最后 AddRoundKey(第 0 轮)
    _ark(0)
    # 列主序转回标准字节序
    return bytes(state[r][c] for c in range(4) for r in range(4))


def _aes_cbc_decrypt(key, iv, data):
    if len(data) % 16:
        data = data + b"\x00" * (16 - len(data) % 16)
    # 1) Android/Chaquopy：javax.crypto 走 Java 原生实现，2MB 封面解起来毫秒级
    #    （纯 Python 实现解 2.3MB 要跑到十几秒，列表一页 12 张必然超时 → 封面出不来）
    try:
        from javax.crypto import Cipher
        from javax.crypto.spec import SecretKeySpec, IvParameterSpec
        _c = Cipher.getInstance("AES/CBC/NoPadding")
        _c.init(Cipher.DECRYPT_MODE, SecretKeySpec(key, "AES"), IvParameterSpec(iv))
        out = _c.doFinal(data)
        out = out if isinstance(out, (bytes, bytearray)) else bytes(bytearray(out))
        return _strip_pad(bytes(out))
    except Exception:
        pass
    # 2) pycryptodome（存在即用，速度快且零出错）
    try:
        from Crypto.Cipher import AES as _CAES
        out = _CAES.new(key, _CAES.MODE_CBC, iv).decrypt(data)
        return _strip_pad(out)
    except Exception:
        pass
    # 3) 手写纯 Python 兜底（慢，但没有第三方库时唯一能出图的路）
    prev = iv
    out = bytearray()
    for i in range(0, len(data), 16):
        blk = _dec_block(key, data[i:i+16])
        plain = bytes(a ^ b for a, b in zip(blk, prev))
        out.extend(plain)
        prev = data[i:i+16]
    return _strip_pad(bytes(out))


def _strip_pad(out):
    """去 PKCS7 填充；末字节落在 1..16 且前 n 字节都等于 n 时才截断（防误删 PNG 尾部）。"""
    if not out:
        return out
    n = out[-1]
    if 1 <= n <= 16 and len(out) >= n and out[-n:] == bytes([n]) * n:
        return out[:-n]
    return out


# ============================================================
# 常量
# ============================================================
HOST = "https://belief.callawtj.cc"
API = "https://www.yeguodj.com/api.php"
UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
      "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
      "Mobile/15E148 Safari/604.1")
TIMEOUT = 15
CTX = ssl._create_unverified_context()

KEY = b"2acf7e91e9864673"   # AES-128 key (hex 串的 ASCII 字节) —— API 响应解密
IV = b"1c29882d3ddfcfd6"    # AES-128 iv —— API 响应解密
MEDIA_KEY = b"f5d965df75336270"   # AES-128 key —— 图床图片解密(PKCS7 填充)
MEDIA_IV = b"97b60394abc2fbe1"    # AES-128 iv  —— 图床图片解密(图床返回 AES-CBC 密文)
OAUTH_ID = "7d05538c4b8a5e74e82f93c0dab0163c"

# ---- 封面代理：走设备本地代理(端口 9978)的 do=py 通道，由 spider.localProxy 解密回传 ----
COVER_PROXY = "http://127.0.0.1:9978/proxy?do=py&type=cover&url="
DEAD_IMG_HOSTS = ("imgpublic.ycomesc.live", "pic.wlwvch.cn")
LIVE_IMG_HOST = "pic.jtzatly.cn"
OLD_IMG_HOST = DEAD_IMG_HOSTS[0]   # 兼容旧引用
NEW_IMG_HOST = LIVE_IMG_HOST
_COVER_CACHE = {}   # url -> (mime, bytes)
_COVER_CACHE_BYTES = [0]        # 已缓存字节数（大图不能无限攒，按字节封顶）
_COVER_CACHE_LIMIT = 24 * 1024 * 1024   # 24MB

MD = {
    "bundleId": "com.pwa.mater",
    "version": "1.3.2",
    "oauth_type": "web",
    "language": "zh",
    "via": "pwa",
    "oauth_id": OAUTH_ID,
    "token": "",
    "trace_id": OAUTH_ID,
}

# 站点登录账号（搜索接口需要登录态 token；列表/详情/播放无需登录）
ACCOUNT = "ygdj123a"
PASSWORD = "123456a"


# ============================================================
# 工具
# ============================================================
def _decode(raw):
    for enc in ("utf-8", "gb18030", "big5"):
        try:
            return raw.decode(enc)
        except Exception:
            continue
    return raw.decode("utf-8", "ignore")


def _clean(text):
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", "", text)
    text = (text.replace("&nbsp;", " ").replace("&amp;", "&")
            .replace("&quot;", '"').replace("&#39;", "'"))
    return re.sub(r"\s+", " ", text).strip()


def _abs(url):
    if not url:
        return ""
    url = url.strip()
    if url.startswith("//"):
        return "http:" + url
    if url.startswith("http"):
        return url
    if url.startswith("/"):
        return HOST + url
    return HOST + "/" + url


def _decrypt(b64):
    """解密 API 响应的 data 字段 -> 明文 JSON 字符串"""
    if not b64:
        return ""
    raw = base64.b64decode(b64.replace(" ", "+"))
    return _aes_cbc_decrypt(KEY, IV, raw).decode("utf-8", "replace")


def _http_post(url, data):
    headers = {
        "User-Agent": UA,
        "Referer": HOST + "/",
        "Accept": "application/json, text/plain, */*",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": HOST,
        "Content-Type": "application/x-www-form-urlencoded",
    }
    if HAS_REQUESTS:
        try:
            r = requests.post(url, data=data, headers=headers, timeout=TIMEOUT, verify=False)
            if r.status_code == 200:
                return r.text
        except Exception:
            pass
    try:
        req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode("utf-8"), headers=headers)
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=CTX) as resp:
            return _decode(resp.read())
    except Exception:
        return ""


def _http_get(url, referer=""):
    headers = {
        "User-Agent": UA,
        "Referer": referer or (HOST + "/"),
        "Accept-Language": "zh-CN,zh;q=0.9",
    }
    if HAS_REQUESTS:
        try:
            r = requests.get(url, headers=headers, timeout=TIMEOUT, verify=False)
            if r.status_code == 200:
                return r.text
        except Exception:
            pass
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=CTX) as resp:
            return _decode(resp.read())
    except Exception:
        return ""


def _http_get_bytes(url, referer=""):
    """抓取二进制(图片)原始字节，返回 bytes；对图床连接重置/超时做重试。"""
    headers = {
        "User-Agent": UA,
        "Referer": referer or (HOST + "/"),
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*",
    }
    last = b""
    for attempt in range(3):
        if HAS_REQUESTS:
            try:
                r = requests.get(url, headers=headers, timeout=TIMEOUT, verify=False)
                if r.status_code == 200 and r.content:
                    return r.content
            except Exception:
                pass
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=TIMEOUT, context=CTX) as resp:
                data = resp.read()
                if data:
                    return data
        except Exception:
            last = b""
            continue
    return last


def _decrypt_image(body):
    """图床图片 = AES-128-CBC 密文(无 PKCS7 填充，块对齐明文)，用 media_key/media_iv 解密。
    解密后为合法 PNG/JPEG，直接回传即可被 TVBox 显示。"""
    if not body or len(body) % 16:
        return b""
    try:
        from Crypto.Cipher import AES
        return AES.new(MEDIA_KEY, AES.MODE_CBC, MEDIA_IV).decrypt(body)
    except Exception:
        prev = MEDIA_IV
        out = bytearray()
        for i in range(0, len(body), 16):
            blk = _dec_block(MEDIA_KEY, body[i:i + 16])
            out.extend(bytes(a ^ b for a, b in zip(blk, prev)))
            prev = body[i:i + 16]
        return bytes(out)


def _login():
    """登录获取 token 并写入 MD；返回 token 或 None"""
    try:
        raw = _http_post(API + "/api/account/login",
                         dict(MD, username=ACCOUNT, password=PASSWORD))
        if not raw:
            return None
        j = json.loads(raw)
        if not isinstance(j.get("data"), str):
            return None
        d = json.loads(_decrypt(j["data"]))
        tok = (d.get("data") or {}).get("token") or d.get("token")
        if tok:
            MD["token"] = tok
        return tok
    except Exception:
        return None


def _ensure_token():
    """确保已登录（token 非空），否则尝试登录"""
    if not MD.get("token"):
        _login()
    return MD.get("token")


def _api(path, params, auth=False):
    """调用后端 API 并解密返回明文 JSON（dict）
    auth=True 时先确保登录态；若返回「未登录」会自动重新登录重试一次。
    """
    if auth:
        _ensure_token()
    data = dict(MD)
    data.update({k: str(v) for k, v in params.items()})
    txt = _http_post(API + path, data)
    if not txt:
        return None
    try:
        j = json.loads(txt)
    except Exception:
        return None
    if j.get("errcode") != 0 or not j.get("data"):
        return None
    try:
        inner = json.loads(_decrypt(j["data"]))
    except Exception:
        return None
    # 需要登录却返回未登录：清 token 重登后重试一次
    if auth and isinstance(inner, dict) and inner.get("status") == -1 \
            and "未登录" in (inner.get("msg") or ""):
        MD["token"] = ""
        if _login():
            return _api(path, params, auth=True)
    return inner


# ============================================================
# SSR 列表解析（前端无盾）
# ============================================================
_CARD_HREF_RE = re.compile(r'<a\b[^>]*href="(/drama/detail/(\d+)/)"', re.S)
_PIC_RE = re.compile(r'(?:data-src|src)="((?:https?://|/)[^"]+)"')
_TITLE_TXT_RE = re.compile(r'>([^<>]{2,60})<')
# Nuxt 把 SSR 数据外链成 <script id="__NUXT_DATA__" data-src="...">，真实封面只在这里
_PAYLOAD_SRC_RE = re.compile(r'id="__NUXT_DATA__"[^>]*?data-src="([^"]+)"', re.S)


def _payload_cover_map(html, page_url=""):
    """抓 Nuxt 的 _payload.json 并解析 devalue 扁平数组，返回 {video_id: cover}。

    devalue 的序列化规则：所有落在 [0, len(arr)) 的整数都是「数组下标引用」，
    其余（负数、超大数）是字面值。剧集对象在数组里长这样：
        {"video_id":7,"title":8,"cover":9,"intro":10,...}   7/8/9/10 都是下标
    故只要逐个 dict 判断有没有 cover 键，再把值递归解引用即可。
    """
    srcs = [m.group(1).replace("&amp;", "&") for m in _PAYLOAD_SRC_RE.finditer(html)]
    if not srcs:
        srcs = ["_payload.json"]
    base = page_url or (HOST + "/")
    for src in srcs[:2]:
        try:
            url = urllib.parse.urljoin(base, src)
        except Exception:
            continue
        txt = _http_get(url, referer=base)
        if not txt:
            continue
        txt = txt.strip()
        if not txt.startswith("["):
            continue
        try:
            arr = json.loads(txt)
        except Exception:
            continue
        if not isinstance(arr, list) or not arr:
            continue
        n = len(arr)

        def dv(v, d=0):
            if d > 6:
                return v
            if isinstance(v, bool):
                return v
            if isinstance(v, int) and 0 <= v < n:
                return dv(arr[v], d + 1)
            return v

        mapping = {}
        for it in arr:
            if not isinstance(it, dict) or "cover" not in it:
                continue
            vid = dv(it.get("video_id", it.get("id")))
            cov = dv(it.get("cover"))
            if isinstance(vid, int):
                vid = str(vid)
            if vid and isinstance(cov, str) and cov.startswith("http"):
                mapping.setdefault(str(vid), cov)
        if mapping:
            return mapping
    return {}


def _cover_map(html):
    """从 SSR 的 __NUXT__ 数据中提取 video_id -> 封面URL 映射（旧版兜底）。
    前端列表图是懒加载占位图，真实封面内联在序列化数据里（任意图床）。
    两种序列化结构都兼容：
      video_id,"标题","https://...png",...   （常规列表）
      video_id,"https://...png",[...]        （榜单/热门区，封面紧跟 id）
    注意：新版站点已把数据挪到 _payload.json，这里只作兜底。
    """
    m = {}
    pats = (
        re.compile(r'(\d+),"[^"]*?","(https:\\u002F\\u002F[^"]+\.(?:png|jpe?g|webp))"'),
        re.compile(r'(\d+),"(https:\\u002F\\u002F[^"]+\.(?:png|jpe?g|webp))"'),
    )
    for pat in pats:
        for mm in pat.finditer(html):
            vid, url = mm.group(1), mm.group(2).replace("\\u002F", "/")
            m.setdefault(vid, url)
    return m


def _cover_map_all(html, page_url=""):
    """封面映射统一入口：优先 payload(devalue)，取不到再退回 HTML 内联正则。"""
    m = _payload_cover_map(html, page_url)
    if not m:
        m = _cover_map(html)
    return m


def _cover_proxy(url):
    """将封面原始 URL 换成本地解密代理地址（顺带把已死的旧图床迁到新图床）。
    返回 http://127.0.0.1:9978/proxy?do=py&type=cover&url=<b64>&param=<b64>，
    由设备本地代理回调本源 localProxy 解密后输出标准图片。
    b64 用标准 base64（不是 urlsafe）：框架若对 param 先做一次 Base64.decode，
    标准串能正常解出明文 URL；urlsafe 的 -_ 会让 Android Base64 直接抛异常。
    """
    if not url:
        return ""
    url = url.strip()
    if not url.startswith("http"):
        url = _abs(url)
    for dead in DEAD_IMG_HOSTS:
        if dead in url:
            url = url.replace(dead, LIVE_IMG_HOST)
            break
    token = base64.b64encode(url.encode("utf-8")).decode("ascii")
    q = urllib.parse.quote(token, safe="")
    return "%s%s&param=%s" % (COVER_PROXY, q, q)


def _b64_to_text(s):
    """base64 -> str；标准/urlsafe 两种字母表都试（框架可能自行 decode 过一次）。
    标准 b64decode 遇到 urlsafe 的 '-'/'_' 会静默丢弃而不是报错，所以取到结果后
    还要判断它是不是合法 URL，否则再换 urlsafe 解一次。"""
    s = (s or "").strip()
    if not s:
        return ""
    pad = "=" * (-len(s) % 4)
    first = ""
    for fn in (base64.b64decode, base64.urlsafe_b64decode):
        try:
            r = fn(s + pad, validate=False).decode("utf-8", "ignore")
        except Exception:
            continue
        if r.startswith("http"):
            return r
        if not first:
            first = r
    return first


def _img_mime(b):
    """按文件魔数判定图片 MIME；非标准图片返回空串。"""
    if not b:
        return ""
    if b[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if b[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if b[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
        return "image/webp"
    if b[:2] == b"BM":
        return "image/bmp"
    return ""


def _cover_type(url, body=b""):
    u = (url or "").lower()
    if u.endswith(".png"):
        return "image/png"
    if u.endswith(".webp"):
        return "image/webp"
    if u.endswith(".gif"):
        return "image/gif"
    # 按解密后魔数兜底判断
    head = body[:16]
    if head[:4] == b"\x89PNG":
        return "image/png"
    if head[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if head[:4] == b"RIFF" and body[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


def _parse_cards(html, limit=40, cover_map=None):
    items, seen = [], set()
    cmap = cover_map or {}
    for m in _CARD_HREF_RE.finditer(html):
        href, vid = m.group(1), m.group(2)
        if vid in seen:
            continue
        seen.add(vid)
        # 标题：img 的 alt > a 的 aria-label（排除通用词）> 临近文本
        tag = html[m.start():m.start() + 500]
        tail = html[m.end():m.end() + 900]
        cand = []
        am = re.search(r'alt="([^"]+)"', tail)
        if am:
            cand.append(am.group(1).strip())
        al = re.search(r'aria-label="([^"]+)"', tag)
        if al and al.group(1).strip() not in ("查看剧集", "查看", "详情", "播放"):
            cand.append(al.group(1).strip())
        tm = _TITLE_TXT_RE.search(tail)
        if tm:
            cand.append(_clean(tm.group(1)))
        title = ""
        for c in cand:
            c = _clean(c)
            if c:
                title = c
                break
        if not title:
            continue
        # 封面：优先 SSR 数据映射（真实图床），其次临近非占位 img；
        # 一律走 localProxy 解码(图床返回 AES 密文，且 Content-Type 为 octet-stream)
        real = cmap.get(vid) or ""
        if not real:
            pm = _PIC_RE.search(tail)
            if pm:
                u = pm.group(1)
                if "base64" not in u and "data:" not in u and not u.lower().endswith(".gif"):
                    real = _abs(u)
        items.append({
            "vod_id": vid,
            "vod_name": title,
            "vod_pic": _cover_proxy(real),
        })
        if len(items) >= limit:
            break
    return items


# ============================================================
# Spider
# ============================================================
class Spider(_BaseSpider if _BaseSpider else object):

    def __init__(self):
        self._session = None

    def getName(self):
        return "野果短剧"

    def init(self, extend=""):
        return

    def isVideoFormat(self, url):
        u = (url or "").lower()
        return any(k in u for k in (".m3u8", ".mp4", ".flv", ".mkv"))

    # -------------------------------------------------- 首页
    def homeContent(self, filter=False):
        url = HOST + "/"
        html = _http_get(url)
        classes = self._classes(html)
        cmap = _cover_map_all(html, url)
        return {
            "class": classes,
            "filters": {},
            "list": _parse_cards(html, cover_map=cmap),
        }

    def homeVideoContent(self):
        url = HOST + "/"
        html = _http_get(url)
        return {"list": _parse_cards(html, cover_map=_cover_map_all(html, url))}

    def _classes(self, html):
        classes = []
        seen = set()
        for m in re.finditer(r'href="(/tag/([^"]+)/)"', html):
            tid = m.group(2)
            if tid in seen:
                continue
            seen.add(tid)
            label = urllib.parse.unquote(tid)
            classes.append({"type_id": tid, "type_name": label})
        if not classes:
            classes = [{"type_id": "%E5%B7%A8%E4%B9%B3", "type_name": "巨乳"}]
        return classes

    # -------------------------------------------------- 分类
    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg or 1)
        tag = urllib.parse.unquote(str(tid))
        # 首选后端分页接口 /api/theater/tagList：
        #   tag=标签名 & page=n -> {total, page, limit, total_pages, has_more, list[...cover]}
        # 这是唯一能真正翻页的来源 —— tag 页 SSR 只有第 1 页有数据，
        # /tag/x/page/2/ 是 5.9KB 的空壳，?page=2 又永远返回第 1 页内容。
        rj = _api("/api/theater/tagList", {"tag": tag, "page": pg})
        data = (rj or {}).get("data") if isinstance(rj, dict) else None
        # 注意：接口成功但"本页为空"是有效结果（已翻到末页），不能当成失败去走 SSR 回退，
        # 否则超范围页会拿回第 1 页内容 → 表现为无限翻页、内容重复。
        if isinstance(data, dict) and isinstance(data.get("list"), list):
            items = []
            for it in data["list"]:
                vid = str(it.get("video_id") or it.get("id") or "")
                if not vid:
                    continue
                items.append({
                    "vod_id": vid,
                    "vod_name": _clean(it.get("title") or ""),
                    "vod_pic": _cover_proxy(_abs(it.get("cover") or "")),
                    "vod_remarks": _clean(it.get("serialize_status_text") or ""),
                })
            try:
                pages = int(data.get("total_pages") or pg)
            except Exception:
                pages = pg
            try:
                total = int(data.get("total") or len(items))
            except Exception:
                total = len(items)
            return {
                "page": pg,
                "pagecount": pages if pages >= 1 else pg,
                "limit": len(items),
                "total": total,
                "list": items,
            }
        # 回退：SSR 抓取（接口异常时至少能出第 1 页）
        url = ("%s/tag/%s/?page=%d" % (HOST, str(tid), pg)) if pg > 1 \
            else ("%s/tag/%s/" % (HOST, str(tid)))
        html = _http_get(url)
        items = _parse_cards(html, limit=60, cover_map=_cover_map_all(html, url))
        if not items:
            return {"page": pg, "pagecount": pg, "limit": 0, "total": 0, "list": []}
        return {
            "page": pg,
            "pagecount": (pg + 1) if len(items) >= 10 else pg,
            "limit": len(items),
            "total": len(items),
            "list": items,
        }

    # -------------------------------------------------- 详情 + 播放
    def detailContent(self, ids):
        vid = ids[0] if isinstance(ids, list) and ids else str(ids or "")
        m = re.search(r"(\d+)", str(vid))
        vid = m.group(1) if m else ""
        if not vid:
            return {"list": []}
        # 后端 detail 接口拿标题/封面/简介/剧集列表
        dj = _api("/api/playlet/detail", {"video_id": vid, "episode_id": 0, "related_limit": 10})
        if not dj or not dj.get("data"):
            return {"list": []}
        d = dj["data"]
        episodes = d.get("episodes") or []
        name = _clean(d.get("title") or "")
        pic = _cover_proxy(_abs(d.get("cover") or ""))
        desc = _clean(d.get("description") or "")
        actor = " ".join(a.get("name", "") for a in (d.get("actor_list") or []) if a.get("name"))
        tags = " ".join(d.get("tags") or [])
        # 构建播放串：每集存 "video_id_episode_id"，由 playerContent 动态取地址
        froms, urls = ["野果短剧"], []
        eps = []
        for ep in episodes:
            eid = ep.get("id")
            if eid is None:
                continue
            title = ep.get("title") or ("第%d集" % (ep.get("sort") or len(eps) + 1))
            state = (ep.get("access") or {}).get("state") or "free"
            # 锁定的集仍可尝试请求；标 free 优先
            eps.append((title, "%s_%s" % (vid, eid), state))
        # 注意：必须用元组里存好的每集 id(pid)，不能用外层循环变量 eid
        # （循环结束后 eid 只剩最后一集的值，会导致每集都播放同一集）
        line = "#".join("%s$%s" % (t, pid) for t, pid, _ in eps)
        vod = {
            "vod_id": vid,
            "vod_name": name,
            "vod_pic": pic,
            "vod_actor": actor,
            "vod_remarks": tags,
            "vod_content": desc,
            "vod_play_from": "$$$".join(froms),
            "vod_play_url": "$$$".join([line]),
        }
        return {"list": [vod]}

    def playerContent(self, flag, id, vipFlags):
        # id 形如 "video_id_episode_id"
        vid, _, eid = str(id).partition("_")
        result = {
            "parse": 0,
            "playUrl": "",
            "url": "",
            "header": json.dumps({
                "User-Agent": UA,
                "Referer": HOST + "/",
            }, ensure_ascii=False),
        }
        if not eid or not vid:
            return result
        pj = _api("/api/playlet/play", {"video_id": vid, "episode_id": eid})
        if not pj:
            return result
        data = pj.get("data") or {}
        url = data.get("video_url") or data.get("url") or ""
        if url:
            result["url"] = url
        return result

    # -------------------------------------------------- 搜索（需登录态）
    def searchContent(self, keyword, quick=False, pg=1):
        kw = (keyword or "").strip()
        if not kw:
            return {"list": []}
        pg = int(pg or 1)
        rj = _api("/api/search/result",
                  {"keyword": kw, "page": pg, "page_size": 20}, auth=True)
        if not rj or not isinstance(rj.get("data"), dict):
            return {"list": [], "page": pg, "pagecount": pg, "limit": 0, "total": 0}
        data = rj["data"]
        lst = data.get("list") or []
        items = []
        for it in lst:
            vid = str(it.get("video_id") or it.get("id") or "")
            if not vid:
                continue
            items.append({
                "vod_id": vid,
                "vod_name": _clean(it.get("title") or ""),
                "vod_pic": _cover_proxy(_abs(it.get("cover") or "")),
            })
        if not items:
            return {"list": [], "page": pg, "pagecount": pg, "limit": 0, "total": 0}
        has_more = data.get("has_more")
        return {
            "page": pg,
            "pagecount": (pg + 1) if has_more else pg,
            "limit": data.get("limit") or len(items),
            "total": data.get("total") or len(items),
            "list": items,
        }

    # -------------------------------------------------- 其他
    def localProxy(self, param):
        """封面解密代理(PY 代理格式)：图床返回 AES-128-CBC(PKCS7) 加密二进制，
        此处解密为标准图片，返回 [status, mime, body] 三元组。
        兼容三种入参形态：dict / 完整 query 字符串 / 裸 urlsafe-base64。"""
        raw = self._extract_proxy_url(param)
        if not raw:
            return [404, "text/plain", b""]
        # 已是标准图片直链（兼容未加密图床），否则解 b64 拿真实 URL
        if raw.startswith("http"):
            target = raw
        else:
            dec = _b64_to_text(raw)
            target = dec if dec.startswith("http") else ""
        if not target:
            return [404, "text/plain", b""]
        for dead in DEAD_IMG_HOSTS:
            if dead in target:
                target = target.replace(dead, LIVE_IMG_HOST)
                break
        hit = _COVER_CACHE.get(target)
        if hit:
            return [200, hit[0], hit[1]]
        data = _http_get_bytes(target)
        if not data:
            return [404, "text/plain", b""]
        mime = _img_mime(data)
        body = data
        if not mime:
            # 非标准图片 -> 视为 AES 加密密文，解密(去 PKCS7 填充)后再判魔数
            try:
                body = _aes_cbc_decrypt(MEDIA_KEY, MEDIA_IV, data)
            except Exception:
                body = b""
            mime = _img_mime(body)
        if not mime:
            return [404, "text/plain", b""]
        # 缓存按字节封顶：一张封面动辄 1~2MB，按条数封顶会吃掉几百 MB 内存；
        # 超限直接整体清空重来（比"满了就再也不缓存"更实用，热点图仍能命中）
        if len(body) <= 4 * 1024 * 1024:
            if _COVER_CACHE_BYTES[0] + len(body) > _COVER_CACHE_LIMIT:
                _COVER_CACHE.clear()
                _COVER_CACHE_BYTES[0] = 0
            _COVER_CACHE[target] = (mime, body)
            _COVER_CACHE_BYTES[0] += len(body)
        return [200, mime, body]

    @staticmethod
    def _extract_proxy_url(param):
        """从 dict / query 字符串 / 裸 base64 中抽取封面目标(原始URL或urlsafe-base64串)。"""
        if isinstance(param, dict):
            if param.get("url"):
                return str(param["url"])
            if param.get("param"):
                return str(param["param"])
            sub = param.get("params") or {}
            if isinstance(sub, dict) and sub.get("url"):
                return str(sub["url"])
            return ""
        s = (param or "").strip()
        if not s:
            return ""
        s = s.replace("&amp;", "&")
        # 框架可能把**完整代理 URL**原样传进来（http://127.0.0.1:9978/proxy?do=py&...&url=x）
        # 此时不能当成图片直链，要剥掉 ? 之前的代理部分继续走 query 解析
        if s.startswith("http") and "/proxy?" in s and "url=" in s:
            s = s.split("?", 1)[-1]
        # 框架可能已经把 param 做过一次 Base64.decode —— 此时收到的就是明文图片 URL
        elif s.startswith("http"):
            return s
        # 框架可能把整个 query 包装成 JSON 字符串传入：{"do":"py","type":"cover","url":"..."}
        # base64 串首字符不可能是 "{"/"["，故不会误判
        if s[:1] in "{[":
            try:
                d = json.loads(s)
                if isinstance(d, dict):
                    for k in ("url", "param", "path"):
                        v = d.get(k)
                        if v:
                            return str(v)
                    sub = d.get("params") or {}
                    if isinstance(sub, dict) and sub.get("url"):
                        return str(sub["url"])
                    return ""
            except Exception:
                pass
        if "url=" in s:
            qs = s.split("?", 1)[-1] if "?" in s else s
            for kv in qs.split("&"):
                k, _, v = kv.partition("=")
                if k == "url":
                    return urllib.parse.unquote(v)
            return ""
        return s

    # 部分 TVBox/影视仓 fork 走 proxy() 而非 localProxy()，此处做别名兜底
    def proxy(self, param):
        return self.localProxy(param)

    def destroy(self):
        return

    def close(self):
        return


# ============================================================
# 模块级双协议转发
# ============================================================
_spider = Spider()


def init(extend=""):
    return _spider.init(extend)


def getName():
    return _spider.getName()


def isVideoFormat(url):
    return _spider.isVideoFormat(url)


def homeContent(filter=False):
    return _spider.homeContent(filter)


def homeVideoContent():
    return _spider.homeVideoContent()


def categoryContent(tid, pg, filter, extend):
    return _spider.categoryContent(tid, pg, filter, extend)


def detailContent(ids):
    return _spider.detailContent(ids)


def playerContent(flag, id, vipFlags):
    return _spider.playerContent(flag, id, vipFlags)


def searchContent(keyword, quick=False, pg=1):
    return _spider.searchContent(keyword, quick, pg)


def localProxy(param):
    return _spider.localProxy(param)


def proxy(param):
    return _spider.proxy(param)


def destroy():
    return _spider.destroy()


def close():
    return _spider.close()
