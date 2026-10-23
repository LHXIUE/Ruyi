# -*- coding: utf-8 -*-
"""
kajhefkhaf TVBox / 影视仓 Spider (dr_py) - 修复版2
===================================================
目标: https://kajhefkhaf.031021.lifestyle:8283/
日期: 20260908

修复版2 改进:
  1. 分类从6个扩展到18个(覆盖purpose 3/4/8/9/16等全部主要分区)
  2. 新增"全部视频"分类(无tag过滤, 全站105000+条)
  3. 子分类从19个扩展到160+(含39个搜索标签组)
  4. VIP视频play_url直接可用, 无需token解锁(CDN不验证)
  5. per_page从20提升到30, 减少翻页

逆向: Fernet加密(AES-128-CBC+HMAC-SHA256)
  - API响应 {"x-data":"gAAAAAB..."} 全部Fernet加密
  - 密钥从webpack module 86315 的 o7 导出项提取
  - 纯Python标准库AES实现, 无需cryptography/pycryptodome
  - API base: sm-api.wieuc.com, site_id=55

接口:
  分类组: /api/vod/tag_group
  标签: /api/vod/tag
  视频列表: /api/vod/video?tag={id}&page={n}&per_page={n}
  视频详情: /api/vod/video/{id}
  搜索: /api/vod/video?search={keyword}
  播放: 详情API返回play_url, 拼接CDN域名(VIP也直接可用)
"""

import sys
import re
import json
import math
import urllib.parse

sys.path.append('..')
try:
    from base.spider import Spider
except Exception:
    class Spider(object):
        def fetch(self, url, headers=None, **kw):
            import requests
            kw.pop('timeout', None)
            return requests.get(url, headers=headers, timeout=15, verify=False, **kw)

        def post(self, url, headers=None, **kw):
            import requests
            return requests.post(url, headers=headers, verify=False, timeout=15, **kw)

        def init(self, extend=""):
            pass


class Spider(Spider):

    SITE_ID = 55
    API_URL = "https://sm-api.wieuc.com"
    IMG_CDN = "https://hm-img.hdstfb.com"
    VIDEO_CDNS = ["hm-vip.hdstfb.com", "hm-img.hdstfb.com"]
    VIDEO_CDN_OVERSEAS = "hm-img.aa66cc.live"
    FERNET_KEY = b"NyGRG56A8i5J2JMqh7da83r2MMfgbM7Ppw1aCF8YnAY="

    # 精选分类组ID (从80个tag_group中挑选内容最丰富的)
    CATEGORY_IDS = [20, 10, 9, 28, 7, 26, 30, 142, 157, 69, 11, 16, 22, 43, 45, 36, 4]

    def __init__(self):
        try:
            super().__init__()
        except Exception:
            pass
        self.host = "https://kajhefkhaf.031021.lifestyle:8283"
        self.ua = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                   'AppleWebKit/537.36 (KHTML, like Gecko) '
                   'Chrome/131.0.0.0 Safari/537.36')
        self._tag_groups = None
        self._img_cache = {}

    # ==================== 基础接口 ====================

    def getName(self):
        return "kajhefkhaf"

    def getDependence(self):
        return []

    def isVideoFormat(self, url):
        if not url:
            return False
        u = url.lower()
        return any(ext in u for ext in ['.m3u8', '.mp4', '.flv', '.ts', '/m3u8'])

    def manualWebSearch(self):
        return False

    def init(self, extend=""):
        ext = str(extend or '').strip()
        if ext.startswith('http'):
            self.host = ext.rstrip('/')

    # ==================== TVBox 接口 ====================

    def homeContent(self, filter):
        groups = self._get_tag_groups()
        classes = []
        filters = {}

        # 1. 全部视频 - 无tag过滤, 全站105000+条
        classes.append({"type_id": "all", "type_name": "全部视频"})
        filters["all"] = []

        # 2. 精选分类组
        for g in groups:
            gid = g.get("id")
            if gid not in self.CATEGORY_IDS:
                continue
            gname = g.get("name", "")
            tags = g.get("tag", [])
            tid = str(gid)
            classes.append({"type_id": tid, "type_name": gname})
            if tags:
                values = [{"n": "全部", "v": ""}]
                for t in tags:
                    tname = t.get("name", "")
                    tid_val = str(t.get("id", ""))
                    if tname and tid_val:
                        values.append({"n": tname, "v": tid_val})
                filters[tid] = [{"key": "tag", "name": "类型", "value": values}]
            else:
                filters[tid] = []

        if len(classes) <= 1:
            classes = [{"type_id": "all", "type_name": "全部视频"}]
            filters["all"] = []

        result = {"class": classes, "filters": filters}
        try:
            home_data = self.homeVideoContent()
            if home_data:
                result["list"] = home_data
        except Exception:
            pass
        return result

    def homeVideoContent(self):
        data = self._api_call("/api/vod/video", {
            "count": "false", "page": 1, "per_page": 30, "random_data": "1"
        })
        items = data.get("data", {}).get("items", [])
        return self._format_video_list(items)

    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg) if pg else 1
        per_page = 30

        params = {"count": "true", "page": page, "per_page": per_page}

        tag_id = None
        if extend and "tag" in extend and extend["tag"]:
            tag_id = extend["tag"]

        if not tag_id and tid != "all":
            groups = self._get_tag_groups()
            for g in groups:
                if str(g.get("id", "")) == tid:
                    tags = g.get("tag", [])
                    if tags:
                        tag_id = ",".join(str(t.get("id", "")) for t in tags)
                    break

        if tag_id:
            params["tag"] = tag_id

        data = self._api_call("/api/vod/video", params)
        d = data.get("data", {})
        items = d.get("items", [])
        total = d.get("total", 0)
        try:
            total = int(total)
        except Exception:
            total = 0
        videos = self._format_video_list(items)
        pagecount = math.ceil(total / per_page) if total else 1
        return {
            "list": videos,
            "page": page,
            "pagecount": pagecount,
            "limit": per_page,
            "total": total
        }

    def detailContent(self, ids):
        vid = ids[0] if isinstance(ids, list) else ids
        data = self._api_call(f"/api/vod/video/{vid}")
        d = data.get("data", {})
        if not d:
            return {"list": []}

        tags = d.get("tag", [])
        tag_names = [t.get("name", "") for t in tags]
        category = "/".join(tag_names[:3]) if tag_names else ""

        play_url = d.get("play_url", "")
        is_paid = d.get("is_paid", 0)

        play_from_parts = []
        play_url_parts = []

        if play_url:
            url1 = self._build_video_url(play_url, 0)
            play_from_parts.append("线路1")
            play_url_parts.append("播放$" + url1)

            url2 = self._build_video_url(play_url, 1)
            play_from_parts.append("线路2")
            play_url_parts.append("播放$" + url2)

            url3 = self._build_video_url(play_url, 2)
            play_from_parts.append("海外专线")
            play_url_parts.append("播放$" + url3)
        else:
            play_from_parts.append("线路1")
            play_url_parts.append("播放$")

        desc = d.get("description", "") or ""
        if is_paid:
            price = d.get("price", "0")
            desc = "[VIP视频可直接播放] " + desc

        return {
            "list": [{
                "vod_id": vid,
                "vod_name": d.get("name", ""),
                "vod_pic": self._build_pic_url(d.get("pic", "")),
                "vod_year": str(d.get("year", "")),
                "vod_content": desc,
                "type_name": category,
                "vod_remarks": self._format_remarks(d),
                "vod_play_from": "$$$".join(play_from_parts),
                "vod_play_url": "$$$".join(play_url_parts),
            }]
        }

    def searchContent(self, key, quick, pg=1):
        page = int(pg) if pg else 1
        if not key:
            return {"list": [], "page": page, "pagecount": 1, "limit": 30, "total": 0}
        data = self._api_call("/api/vod/video", {
            "count": "true", "page": page, "per_page": 30, "search": key
        })
        d = data.get("data", {})
        items = d.get("items", [])
        total = d.get("total", 0)
        try:
            total = int(total)
        except Exception:
            total = 0
        videos = self._format_video_list(items)
        pagecount = math.ceil(total / 30) if total else 1
        return {
            "list": videos,
            "page": page,
            "pagecount": pagecount,
            "limit": 30,
            "total": total
        }

    def searchContentPage(self, key, quick, pg=1):
        return self.searchContent(key, quick, pg)

    def playerContent(self, flag, id, vipFlags):
        if id.startswith("http"):
            return {
                "parse": 0,
                "url": id,
                "header": {
                    "User-Agent": self.ua,
                    "Referer": self.host + "/",
                    "Origin": self.host
                }
            }

        data = self._api_call(f"/api/vod/video/{id}")
        d = data.get("data", {})
        play_url = d.get("play_url", "")
        if play_url:
            if "海外" in flag:
                url = self._build_video_url(play_url, 2)
            elif "2" in flag:
                url = self._build_video_url(play_url, 1)
            else:
                url = self._build_video_url(play_url, 0)
            return {
                "parse": 0,
                "url": url,
                "header": {
                    "User-Agent": self.ua,
                    "Referer": self.host + "/",
                    "Origin": self.host
                }
            }
        return {
            "parse": 1,
            "url": "",
            "header": {"User-Agent": self.ua, "Referer": self.host + "/"}
        }

    # ==================== 内部方法 ====================

    def _api_call(self, path, params=None):
        if params is None:
            params = {}
        params["site_id"] = self.SITE_ID
        url = self.API_URL + path + "?" + urllib.parse.urlencode(params)
        headers = {
            "User-Agent": self.ua,
            "Origin": self.host,
            "Referer": self.host + "/",
            "Content-Type": "application/json",
        }
        try:
            resp = self.fetch(url, headers=headers, timeout=15)
            raw = resp.text
            j = json.loads(raw)
            x_data = j.get("x-data", "")
            if x_data:
                return self._fernet_decrypt(x_data)
            return j
        except Exception:
            try:
                import requests
                resp = requests.get(url, headers=headers, timeout=15, verify=False)
                raw = resp.text
                j = json.loads(raw)
                x_data = j.get("x-data", "")
                if x_data:
                    return self._fernet_decrypt(x_data)
                return j
            except Exception:
                return {"data": {"items": [], "total": 0}}

    # ==================== 纯Python Fernet解密 (无需cryptography库) ====================

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
    _INV_SBOX = [0]*256
    for _i in range(256):
        _INV_SBOX[_SBOX[_i]] = _i
    _RCON = [0x01,0x02,0x04,0x08,0x10,0x20,0x40,0x80,0x1b,0x36]

    @staticmethod
    def _xtime(a):
        return ((a << 1) ^ 0x1b) & 0xff if a & 0x80 else (a << 1)

    @classmethod
    def _gmul(cls, a, b):
        r = 0
        for _ in range(8):
            if b & 1:
                r ^= a
            b >>= 1
            a = cls._xtime(a)
        return r

    @classmethod
    def _key_expansion(cls, key):
        w = list(key)
        for i in range(4, 44):
            temp = w[(i-1)*4:(i-1)*4+4]
            if i % 4 == 0:
                temp = temp[1:] + temp[:1]
                temp = [cls._SBOX[b] for b in temp]
                temp[0] ^= cls._RCON[i//4 - 1]
            for j in range(4):
                w.append(w[(i-4)*4+j] ^ temp[j])
        return w

    @classmethod
    def _aes128_decrypt_block(cls, block, w):
        s = list(block)
        cls._add_round_key(s, w, 10)
        for rnd in range(9, 0, -1):
            cls._inv_shift_rows(s)
            cls._inv_sub_bytes(s)
            cls._add_round_key(s, w, rnd)
            cls._inv_mix_columns(s)
        cls._inv_shift_rows(s)
        cls._inv_sub_bytes(s)
        cls._add_round_key(s, w, 0)
        return bytes(s)

    @staticmethod
    def _add_round_key(s, w, rnd):
        for i in range(16):
            s[i] ^= w[rnd*16 + i]

    @classmethod
    def _inv_sub_bytes(cls, s):
        for i in range(16):
            s[i] = cls._INV_SBOX[s[i]]

    @staticmethod
    def _inv_shift_rows(s):
        s[1], s[5], s[9], s[13] = s[13], s[1], s[5], s[9]
        s[2], s[6], s[10], s[14] = s[10], s[14], s[2], s[6]
        s[3], s[7], s[11], s[15] = s[7], s[11], s[15], s[3]

    @classmethod
    def _inv_mix_columns(cls, s):
        for c in range(4):
            i = c*4
            a0, a1, a2, a3 = s[i], s[i+1], s[i+2], s[i+3]
            s[i]   = cls._gmul(a0,0x0e)^cls._gmul(a1,0x0b)^cls._gmul(a2,0x0d)^cls._gmul(a3,0x09)
            s[i+1] = cls._gmul(a0,0x09)^cls._gmul(a1,0x0e)^cls._gmul(a2,0x0b)^cls._gmul(a3,0x0d)
            s[i+2] = cls._gmul(a0,0x0d)^cls._gmul(a1,0x09)^cls._gmul(a2,0x0e)^cls._gmul(a3,0x0b)
            s[i+3] = cls._gmul(a0,0x0b)^cls._gmul(a1,0x0d)^cls._gmul(a2,0x09)^cls._gmul(a3,0x0e)

    @classmethod
    def _aes_cbc_decrypt(cls, ciphertext, key, iv):
        w = cls._key_expansion(list(key))
        pt = b''
        prev = iv
        for i in range(0, len(ciphertext), 16):
            block = ciphertext[i:i+16]
            dec = cls._aes128_decrypt_block(block, w)
            pt += bytes(a ^ b for a, b in zip(dec, prev))
            prev = block
        if pt:
            pad = pt[-1]
            if 1 <= pad <= 16:
                pt = pt[:-pad]
        return pt

    def _fernet_decrypt(self, token):
        import base64, hashlib, hmac
        key_b64 = self.FERNET_KEY
        if isinstance(key_b64, bytes):
            key_b64 = key_b64.decode()
        kpad = 4 - len(key_b64) % 4
        if kpad != 4:
            key_b64_pad = key_b64 + '=' * kpad
        else:
            key_b64_pad = key_b64
        key_raw = base64.urlsafe_b64decode(key_b64_pad)
        enc_key = key_raw[16:]

        tpad = 4 - len(token) % 4
        if tpad != 4:
            token_pad = token + '=' * tpad
        else:
            token_pad = token
        token_raw = base64.urlsafe_b64decode(token_pad)

        iv = token_raw[9:25]
        ciphertext = token_raw[25:-32]

        plaintext = self._aes_cbc_decrypt(ciphertext, enc_key, iv)
        return json.loads(plaintext)

    def _fernet_decrypt_text(self, token):
        """Fernet解密, 返回原始字符串(不解析JSON), 用于图片解密"""
        import base64
        key_b64 = self.FERNET_KEY
        if isinstance(key_b64, bytes):
            key_b64 = key_b64.decode()
        kpad = 4 - len(key_b64) % 4
        if kpad != 4:
            key_b64_pad = key_b64 + '=' * kpad
        else:
            key_b64_pad = key_b64
        key_raw = base64.urlsafe_b64decode(key_b64_pad)
        enc_key = key_raw[16:]

        tpad = 4 - len(token) % 4
        if tpad != 4:
            token_pad = token + '=' * tpad
        else:
            token_pad = token
        token_raw = base64.urlsafe_b64decode(token_pad)

        iv = token_raw[9:25]
        ciphertext = token_raw[25:-32]

        plaintext = self._aes_cbc_decrypt(ciphertext, enc_key, iv)
        return plaintext.decode('utf-8')

    def _get_tag_groups(self):
        if self._tag_groups is not None:
            return self._tag_groups
        data = self._api_call("/api/vod/tag_group", {"page": 1, "per_page": 1000})
        items = data.get("data", {}).get("items", [])
        self._tag_groups = items
        return items

    def _build_pic_url(self, path):
        if not path:
            return ""
        if path.startswith("http"):
            return path
        if not path.startswith("/"):
            path = "/" + path

        # 缓存
        cache_key = path
        if cache_key in self._img_cache:
            return self._img_cache[cache_key]

        # 图片CDN返回Fernet加密数据: "FernetToken@@@RawBase64Data"
        # 解密流程: Fernet解密前半部分得到 data:image/...;base64,<缩略图>
        # 拼接后半部分原始base64数据 -> 完整图片data URI
        url = self.IMG_CDN + path
        headers = {
            "User-Agent": self.ua,
            "Referer": self.host + "/",
            "Origin": self.host,
        }
        try:
            resp = self.fetch(url, headers=headers, timeout=10)
            text = resp.text
            if "@@@" in text:
                parts = text.split("@@@", 1)
                dec_prefix = self._fernet_decrypt_text(parts[0].strip())
                data_uri = dec_prefix + parts[1]
            elif text.startswith("gAAAA"):
                # 纯Fernet加密(无@@@分隔)
                data_uri = self._fernet_decrypt_text(text.strip())
            else:
                data_uri = ""
            if data_uri:
                self._img_cache[cache_key] = data_uri
                return data_uri
        except Exception:
            try:
                import requests as _req
                resp = _req.get(url, headers=headers, timeout=10, verify=False)
                text = resp.text
                if "@@@" in text:
                    parts = text.split("@@@", 1)
                    dec_prefix = self._fernet_decrypt_text(parts[0].strip())
                    data_uri = dec_prefix + parts[1]
                elif text.startswith("gAAAA"):
                    data_uri = self._fernet_decrypt_text(text.strip())
                else:
                    data_uri = ""
                if data_uri:
                    self._img_cache[cache_key] = data_uri
                    return data_uri
            except Exception:
                pass

        # 解密失败, 返回原始URL (TVBox可能无法显示但不会崩溃)
        return url

    def _build_video_url(self, path, line=0):
        if not path:
            return ""
        if path.startswith("http"):
            return path
        cdns = self.VIDEO_CDNS if line < 2 else [self.VIDEO_CDN_OVERSEAS]
        cdn = cdns[line % len(cdns)] if cdns else self.VIDEO_CDNS[0]
        return "https://" + cdn + path

    def _format_remarks(self, v):
        is_paid = v.get("is_paid", 0)
        price = v.get("price", "0")
        duration = v.get("duration", 0)
        if is_paid and float(price) > 0:
            return "VIP " + str(price) + "积分"
        elif duration:
            mins = duration // 60
            secs = duration % 60
            return str(mins) + ":" + str(secs).zfill(2)
        return ""

    def _format_video_list(self, items):
        videos = []
        for v in items:
            videos.append({
                "vod_id": str(v.get("id", "")),
                "vod_name": v.get("name", ""),
                "vod_pic": self._build_pic_url(v.get("pic", "")),
                "vod_remarks": self._format_remarks(v),
            })
        return videos


# ==================== 测试 ====================
if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")

    sp = Spider()
    sp.init()

    print("=" * 60)
    print("TVBox 爬虫测试 - kajhefkhaf 修复版2")
    print("=" * 60)

    # 1. 首页分类栏
    print("\n[1] 首页分类栏...")
    r = sp.homeContent(0)
    cats = r.get("class", [])
    print(f"  分类数: {len(cats)}")
    for c in cats:
        print(f"    {c['type_id']}: {c['type_name']}")
    videos = r.get("list", [])
    print(f"  首页视频数: {len(videos)}")
    if videos:
        print(f"  首条: {videos[0]['vod_name'][:50]}")
    print("  [PASS]" if len(cats) > 0 and len(videos) > 0 else "  [FAIL]")

    # 2. 全部视频分类 (核心修复: 无tag过滤, 全站10万+)
    print("\n[2] 全部视频分类...")
    r = sp.categoryContent("all", 1, True, {})
    videos = r.get("list", [])
    total = r.get("total", 0)
    print(f"  视频数: {len(videos)}")
    print(f"  总数: {total}")
    if videos:
        print(f"  首条: {videos[0]['vod_name'][:50]}")
    print("  [PASS]" if len(videos) > 0 and total > 1000 else "  [FAIL]")

    # 3. 国产专区分类 (有子分类)
    print("\n[3] 国产专区分类...")
    r = sp.categoryContent("20", 1, True, {})
    videos = r.get("list", [])
    total = r.get("total", 0)
    print(f"  视频数: {len(videos)}")
    print(f"  总数: {total}")
    if videos:
        print(f"  首条: {videos[0]['vod_name'][:50]}")
    print("  [PASS]" if len(videos) > 0 else "  [FAIL]")

    # 4. 子分类筛选 (国产专区->国产自拍)
    print("\n[4] 子分类筛选...")
    groups = sp._get_tag_groups()
    test_tag = None
    test_name = ""
    for g in groups:
        if str(g.get("id")) == "20":
            tags = g.get("tag", [])
            for t in tags:
                tid = str(t.get("id"))
                r = sp.categoryContent("20", 1, True, {"tag": tid})
                vids = r.get("list", [])
                if vids:
                    test_tag = tid
                    test_name = t.get("name", "")
                    break
            break
    if test_tag:
        r = sp.categoryContent("20", 1, True, {"tag": test_tag})
        videos = r.get("list", [])
        print(f"  子分类[{test_name}] tag={test_tag}")
        print(f"  视频数: {len(videos)}")
        if videos:
            print(f"  首条: {videos[0]['vod_name'][:50]}")
        print("  [PASS]" if len(videos) > 0 else "  [FAIL]")
    else:
        print("  [SKIP]")

    # 5. 详情页 (含VIP视频)
    print("\n[5] 详情页...")
    r = sp.categoryContent("all", 1, True, {})
    videos = r.get("list", [])
    if videos:
        vid = videos[0]["vod_id"]
        d = sp.detailContent([vid])
        dv = d.get("list", [])
        if dv:
            v = dv[0]
            print(f"  标题: {v.get('vod_name','')[:60]}")
            print(f"  封面: {v.get('vod_pic','')[:60]}")
            print(f"  播放源: {v.get('vod_play_from','')}")
            urls = v.get("vod_play_url", "").split("$")
            if len(urls) > 1:
                print(f"  播放URL: {urls[1][:80]}")
            print("  [PASS]" if v.get("vod_name") else "  [FAIL]")
        else:
            print("  [FAIL] 详情为空")

    # 6. 搜索
    print("\n[6] 搜索...")
    r = sp.searchContent("网红", False)
    videos = r.get("list", [])
    print(f"  搜索结果数: {len(videos)}")
    if videos:
        print(f"  首条: {videos[0]['vod_name'][:50]}")
    print("  [PASS]" if len(videos) > 0 else "  [FAIL]")

    # 7. 播放
    print("\n[7] 播放(m3u8)...")
    r = sp.categoryContent("all", 1, True, {})
    videos = r.get("list", [])
    if videos:
        vid = videos[0]["vod_id"]
        p = sp.playerContent("线路1", vid, "")
        url = p.get("url", "")
        print(f"  播放URL: {url[:80]}")
        print(f"  parse: {p.get('parse', 0)}")
        print("  [PASS]" if url and ".m3u8" in url else "  [FAIL]")

    # 8. 搜索标签组 (39个子分类)
    print("\n[8] 搜索标签组(39个子分类)...")
    filters = sp.homeContent(0).get("filters", {})
    search_filter = filters.get("4", [])
    if search_filter:
        vals = search_filter[0].get("value", [])
        print(f"  子分类数: {len(vals)}")
        print("  [PASS]" if len(vals) > 10 else "  [FAIL]")
    else:
        print("  [FAIL] 无搜索标签组")

    # 9. 翻页测试
    print("\n[9] 翻页测试(全部视频第2页)...")
    r = sp.categoryContent("all", 2, True, {})
    videos = r.get("list", [])
    print(f"  第2页视频数: {len(videos)}")
    print(f"  总页数: {r.get('pagecount', 0)}")
    print("  [PASS]" if len(videos) > 0 else "  [FAIL]")

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)
