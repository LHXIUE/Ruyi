#coding=utf-8
import sys
import re
import requests
from urllib.parse import quote

sys.path.append('..')
try:
    from base.spider import Spider
except ImportError:
    class Spider:
        def fetch(self, url, headers=None, **kw):
            import requests as rq
            kw.pop('timeout', None)
            r = rq.get(url, headers=headers, timeout=15, **kw)
            r.encoding = 'utf-8'
            return r

HOST = "https://jlj.xbsp6.boats"
PUBLISH = "https://ruv.xxkk7.com/323/"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
CATEGORIES = {
    "20": "熟母少妇", "21": "网红直播", "22": "自拍偷拍", "23": "强奸乱伦",
    "24": "高清国产", "25": "韩国专区", "26": "日本有码", "27": "日本无码",
    "28": "欧美情色", "29": "动漫卡通", "30": "三级伦理",
}


class Spider(Spider):
    def __init__(self):
        self.site_url = HOST

    def init(self, extend=""):
        self.site_url = HOST
        if not self._alive(HOST):
            self._refresh_host()
        return {}

    def getName(self):
        return "杏吧视频"

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def getHeader(self):
        return {"User-Agent": UA, "Referer": self.site_url + "/"}

    def _alive(self, url):
        try:
            r = requests.get(url, headers=self.getHeader(), timeout=4)
            return r.status_code == 200
        except Exception:
            return False

    def _refresh_host(self):
        try:
            r = requests.get(PUBLISH, headers={"User-Agent": UA}, timeout=8)
            r.encoding = 'utf-8'
            m = re.search(r"sub_domain\s*=\s*['\"]([^'\"]+)['\"][\s\S]*?prefix\s*=\s*['\"]([^'\"]+)['\"][\s\S]*?suffix\s*=\s*['\"]([^'\"]+)['\"]", r.text)
            if m:
                self.site_url = "https://%s.%s.%s" % (m.group(1), m.group(2), m.group(3))
        except Exception:
            pass

    def _items(self, html):
        out = []
        for m in re.finditer(r'<article[^>]*>([\s\S]*?)</article>', html):
            b = m.group(1)
            hm = re.search(r'href=["\']([^"\']+)["\']', b)
            if not hm:
                continue
            u = hm.group(1)
            if not u.startswith('http'):
                u = self.site_url + ('' if u.startswith('/') else '/') + u
            tm = re.search(r'<h2[^>]*>([\s\S]*?)</h2>', b)
            t = re.sub(r'<[^>]+>', '', tm.group(1)).strip() if tm else ''
            im = re.search(r'data-src=["\']([^"\']+)["\']|src=["\']([^"\']+)["\']', b)
            pic = im.group(1) or im.group(2) or ''
            rm = re.search(r'meta-content[^>]*>([\s\S]*?)</', b)
            remark = re.sub(r'<[^>]+>', '', rm.group(1)).strip() if rm else ''
            if t or u:
                out.append({'vod_id': u, 'vod_name': t, 'vod_pic': pic, 'vod_remarks': remark[:30]})
        return out

    def homeContent(self, filter=False):
        classes = [{'type_id': k, 'type_name': v} for k, v in CATEGORIES.items()]
        lst = []
        try:
            r = requests.get(self.site_url + '/xbsp/', headers=self.getHeader(), timeout=10)
            r.encoding = 'utf-8'
            lst = self._items(r.text)
        except Exception:
            pass
        return {'class': classes, 'list': lst, 'filter': False}

    def homeVideoContent(self):
        return self.categoryContent('20', 1)

    def categoryContent(self, tid, pg=1, filter=False, extend=""):
        pn = 1
        try:
            pn = max(int(str(pg)), 1)
        except Exception:
            pass
        lst = []
        html = ''
        try:
            r = requests.get('%s/vodtype/%s-%s.html' % (self.site_url, tid, pn), headers=self.getHeader(), timeout=10)
            r.encoding = 'utf-8'
            html = r.text
            lst = self._items(html)
        except Exception:
            pass
        pc = pn
        if re.search(r'link-pagination[^"\']*only-next', html):
            pc = pn + 1
        return {'list': lst, 'page': pn, 'pagecount': pc, 'limit': len(lst), 'total': len(lst)}

    def detailContent(self, ids):
        url = ids[0] if isinstance(ids, list) else str(ids)
        vod = {'vod_id': url, 'vod_name': '在线播放', 'vod_pic': '', 'type_name': '', 'vod_actor': '', 'vod_director': '', 'vod_year': '', 'vod_area': '', 'vod_remarks': '', 'vod_content': '', 'vod_play_from': '杏吧播放', 'vod_play_url': '正片$' + url}
        try:
            r = requests.get(url, headers=self.getHeader(), timeout=10)
            r.encoding = 'utf-8'
            h = r.text
            tm = re.search(r'<title>([^<]*)</title>', h)
            if tm:
                name = re.sub(r'(在线观看|在线播放)$', '', tm.group(1).strip().split(' - ')[0]).strip()
                if name:
                    vod['vod_name'] = name
            im = re.search(r'data-src=["\']([^"\']+)["\']', h)
            if im:
                vod['vod_pic'] = im.group(1)
        except Exception:
            pass
        return {'list': [vod]}

    def searchContent(self, key, quick=False, pg="1"):
        try:
            r = requests.get('%s/s/%s/page/%s.html' % (self.site_url, quote(key), pg), headers=self.getHeader(), timeout=10)
            r.encoding = 'utf-8'
            return {'list': self._items(r.text)}
        except Exception:
            return {'list': []}

    def playerContent(self, flag, id, vipFlags=None):
        url = str(id) if id else str(flag)
        try:
            r = requests.get(url, headers=self.getHeader(), timeout=10)
            r.encoding = 'utf-8'
            h = r.text
            m = re.search(r"rawUrl\s*=\s*['\"]([^'\"]+\.m3u8[^'\"]*)['\"]", h)
            if not m:
                m = re.search(r"https?://[^\s$#'\"]+\.m3u8(?:\?[^\s#'\"]*)?", h, re.I)
            if not m:
                m = re.search(r"https?://[^\s$#'\"]+\.mp4(?:\?[^\s#'\"]*)?", h, re.I)
            if m:
                url = m.group(1) if m.lastindex else m.group(0)
        except Exception:
            pass
        return {'parse': 0, 'url': url, 'header': self.getHeader()}

    def localProxy(self, param):
        return {}