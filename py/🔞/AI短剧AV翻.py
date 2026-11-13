# -*- coding: utf-8 -*-
# ============ AI短剧AV · aisee10w29.buzz 源（MacCMS二次开发 + huangguo取流网关）============
# 站型: MacCMS v10 二次开发（PHP 模板 /template/ai/，jQuery 服务端渲染）
#   ★ 关键发现(2026-11-10 全链路实测):
#   1) /api.php/provide/vod 已关（返回 closed）；/index.php/ajax/data?mid=1 可用（75字段）
#      但该接口 tid/wd/ids 参数全被忽略 → 只能当"全站最新"，分类/搜索必须走 HTML
#   2) 分类路由: /aidj/{tid}/  第1页；/aidj/{tid}/page/{n}/ 后续（tid=25/26/27/28 有效）
#   3) 详情路由: /detail/{id}/ 或 /index.php/detail/{id}/（注意：/detail-{id}/ 是错的路由，返回"获取数据失败"）
#      详情页无选集列表！只给第1集入口，集数靠备注"更新至N集"
#   4) 播放: /play/{id}-1-{ep}/ → player_data 的 url="真实vid|ep"（真实vid ≠ vod_id）
#      ★ 真实vid 可直接从 og:image 的 /upload/huangguo/{真实vid}.jpg 提取 → 零额外请求
#   5) 取流: GET /huangguo.php?ac=play&id={真实vid}&ep={ep} （需 X-Requested-With）
#            → {"code":1,"url":"/huangguo.php?ac=media&t=<token>"}
#   6) 真实流: https://host/huangguo.php?ac=media&t=<token> → m3u8（AES-128，分片与KEY均为根相对路径）
#      分片/KEY 直连无需 cookie（实测 200 + 16字节key），无盾无防盗链，单线路直连即可
#   7) 线路数 = 站点实际播放源数（播放页 .vp-episode-list 的 data-sid 组数），本站只有 1 条（from=huangguo）
#      ★ 用户明确要求：站点几条线路就几条，禁止自造线路（不铺代理线、不铺备用线）
# 契约: 555六方法 + homeVideoContent；parse=0；禁3.9+API（OK影视内置Python≤3.8）
import sys, re, json, time
from urllib.parse import urljoin, quote, unquote

sys.path.append('..')
try:
    from base.spider import Spider
except ImportError:
    import requests

    class Spider:
        def fetch(self, url, headers=None, **kw):
            kw.pop('timeout', None)
            r = requests.get(url, headers=headers, timeout=20, **kw)
            r.encoding = 'utf-8'
            return r

# ============ ★ CONFIG ============
SITE = 'https://aisee10w29.buzz'          # ★ 站点基址(换域名改这里)
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
CLASSES = [('25', 'AI成人短剧'), ('26', 'AI成人漫剧'), ('27', 'AI换脸'), ('28', 'AI魔改')]
PLAY_REF = 'https://aisee10w29.buzz/static/player/huangguo.html'   # 取流接口 Referer
TIMEOUT = 25
# ★ 筛选器：值必须是站点真实生效的参数（2026-11-10 实测）
#   by=hits 最热 / by=score 高分 / order=asc 最早 / 留空 = 默认最新
#   该站年份数据全为 2026、地区全空，做年份/地区就是假筛选，故不做
FILTER_SORT = [
    {'n': '最新', 'v': ''},
    {'n': '最热', 'v': 'by=hits'},
    {'n': '高分', 'v': 'by=score'},
    {'n': '最早', 'v': 'order=asc'},
]
# =================================


class Spider(Spider):
    def __init__(self):
        self.base = SITE.rstrip('/')
        self.hd = {
            'User-Agent': UA,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Referer': self.base + '/',
        }

    # ---------- 基础请求 ----------
    def init(self, extend=''):
        try:
            if extend and extend.strip().startswith('http'):
                self.base = extend.strip().rstrip('/')
        except Exception:
            pass
        return None

    def _get(self, url, ref=None, xhr=False, retry=2):
        hd = dict(self.hd)
        if ref:
            hd['Referer'] = ref
        if xhr:
            hd['X-Requested-With'] = 'XMLHttpRequest'
        for i in range(retry + 1):
            try:
                r = self.fetch(url, headers=hd, timeout=TIMEOUT)
                code = getattr(r, 'status_code', 200)
                if code == 200:
                    return r
                if code in (403, 429, 503):
                    time.sleep(0.8 * (i + 1))
                    continue
                return r
            except Exception:
                time.sleep(0.6 * (i + 1))
        return None

    def _text(self, r):
        """统一取响应文本：优先 bytes 按 utf-8 解，避免 requests 猜测 ISO-8859-1 出乱码"""
        if r is None:
            return ''
        try:
            b = getattr(r, 'content', None)
            if isinstance(b, bytes) and b:
                return b.decode('utf-8', 'ignore')
        except Exception:
            pass
        try:
            t = getattr(r, 'text', None)
            if isinstance(t, str):
                return t
        except Exception:
            pass
        try:
            b = getattr(r, 'content', None)
            if isinstance(b, str):
                return b
        except Exception:
            pass
        return ''

    def _html(self, url, ref=None):
        return self._text(self._get(url, ref=ref))

    def _digits(self, v):
        m = re.search(r'\d+', str(v))
        return m.group(0) if m else ''

    # ---------- 列表解析 ----------
    def _cards(self, h, tid=''):
        out = []
        if not h:
            return out
        blocks = re.split(r'video-element', h)
        for b in blocks[1:]:
            m = re.search(r'href="(/detail/(\d+)/)"', b)
            if not m:
                continue
            vid = m.group(2)
            pic = ''
            name = ''
            # 只在 video-cover 块内取封面图，避免抓到 bookmarker(alt="收藏")
            mp = re.search(r'class="video-cover"[\s\S]{0,400}?<img[\s\S]{0,260}?src="([^"]+)"'
                           r'[\s\S]{0,260}?alt="([^"]*)"', b)
            if mp:
                pic = mp.group(1).strip()
                name = mp.group(2).strip()
            if not pic:
                mp2 = re.search(r'class="video-cover-img"[\s\S]{0,160}?src="([^"]+)"', b)
                pic = mp2.group(1).strip() if mp2 else ''
            if name in ('', '收藏', '海报', '封面'):
                mt = re.search(r'class="video-title"[\s\S]{0,260}?>\s*([^<]{1,80})\s*<', b)
                name = mt.group(1).strip() if mt else vid
            if pic.startswith('//'):
                pic = 'https:' + pic
            out.append({
                'vod_id': vid,
                'vod_name': name,
                'vod_pic': pic,
                'vod_remarks': '',
                'vod_year': '',
                'type_name': '',
            })
        return out

    def _pagecount(self, h, tid, pg):
        # 动态 pagecount：存在下一页链接才 +1（禁止硬编码 999）
        # 带筛选参数时下一页链接可能是 /page/2/?by=hits，故只认 "/page/N" 片段
        if not h:
            return pg
        if ('/page/%d/' % (pg + 1)) in h or ('page/%d' % (pg + 1)) in h:
            return pg + 1
        if re.search(r'>\s*下一页\s*<|class="next"', h):
            return pg + 1
        return pg

    # ---------- 筛选器 ----------
    def _ext(self, extend):
        """extend 统一成 dict（播放器可能传 str / dict / 值本身是 list）"""
        ext = extend
        if isinstance(ext, str):
            s = ext.strip()
            if s.startswith('{'):
                try:
                    ext = json.loads(s)
                except Exception:
                    ext = {}
            else:
                ext = {}
        return ext if isinstance(ext, dict) else {}

    def _ext_val(self, ext, key):
        v = ext.get(key)
        if isinstance(v, (list, tuple)):
            v = v[0] if v else ''
        if isinstance(v, dict):
            v = v.get('v') or v.get('value') or ''
        return str(v or '').strip()

    def _query(self, extend):
        """把筛选条件拼成真实可用的查询串；值必须是站点认的参数"""
        ext = self._ext(extend)
        parts = []
        y = self._digits(self._ext_val(ext, 'year'))
        if y:
            parts.append('year=' + y)
        s = self._ext_val(ext, 'sort')
        if s and re.match(r'^[A-Za-z_]{2,10}=[\w\-]{1,20}$', s):
            parts.append(s)
        return ('?' + '&'.join(parts)) if parts else ''

    # ---------- 首页 ----------
    def homeContent(self, filter=False):
        classes = [{'type_id': t, 'type_name': n} for t, n in CLASSES]
        filters = {}
        for t, _n in CLASSES:
            filters[t] = [{'key': 'sort', 'name': '排序', 'value': FILTER_SORT}]
        lst = self._cards(self._html('%s/aidj/25/' % self.base), '25')
        return {'class': classes, 'list': lst, 'filters': filters}

    def homeVideoContent(self):
        return {'list': self._cards(self._html('%s/aidj/25/' % self.base), '25')}

    # ---------- 分类 ----------
    def categoryContent(self, tid, pg=1, filter=False, extend=''):
        tid = str(tid).split('|')[0].strip()
        try:
            pg = max(int(str(pg)), 1)
        except Exception:
            pg = 1
        q = self._query(extend)
        if pg <= 1:
            url = '%s/aidj/%s/%s' % (self.base, tid, q)
        else:
            url = '%s/aidj/%s/page/%d/%s' % (self.base, tid, pg, q)
        h = self._html(url)
        lst = self._cards(h, tid)
        pc = self._pagecount(h, tid, pg)
        if not lst:
            pc = pg  # 空结果：不再提供下一页，避免空翻
        return {'list': lst, 'page': pg, 'pagecount': pc,
                'limit': len(lst), 'total': len(lst) * pc}

    # ---------- 详情 ----------
    def _hgvid(self, pic, vod_id):
        m = re.search(r'/upload/huangguo/(\d+)\.', pic or '')
        if m:
            return m.group(1)
        # 兜底：请求播放页取 player_data
        p = self._html('%s/play/%s-1-1/' % (self.base, vod_id))
        m2 = re.search(r'"url"\s*:\s*"(\d+)\s*\|', p)
        return m2.group(1) if m2 else ''

    def _play_sources(self, h):
        """从播放页解析站点真实播放源：{sid: [(集号, 集名)]}、源名、首集真实vid"""
        eps = {}
        if not h:
            return eps, '', ''
        for m in re.finditer(r'/play/(\d+)-(\d+)-(\d+)/"[\s\S]{0,160}?data-sid="(\d+)"'
                             r'[\s\S]{0,160}?data-nid="(\d+)"[\s\S]{0,60}?>([^<]{0,24})<', h):
            sid = int(m.group(4))
            nid = int(m.group(5))
            lab = m.group(6).strip() or ('第%d集' % nid)
            eps.setdefault(sid, []).append((nid, lab))
        for k in list(eps.keys()):
            seen, out = set(), []
            for nid, lab in sorted(eps[k], key=lambda x: x[0]):
                if nid not in seen:
                    seen.add(nid)
                    out.append((nid, lab))
            eps[k] = out
        m = re.search(r'"from"\s*:\s*"([^"]{0,20})"', h)
        name = m.group(1).strip() if m else 'huangguo'
        m2 = re.search(r'"url"\s*:\s*"(\d+)\s*\|', h)
        return eps, (name or 'huangguo'), (m2.group(1) if m2 else '')

    def detailContent(self, ids, quick='1'):
        # ★ 播放器传入的 ids 是 list（CatVod/fongmi 均为 ArrayList/List），
        #   直接 str(ids) 会得到 "['3029']" 导致详情 404 → 详情页无播放地址
        if isinstance(ids, (list, tuple)):
            raw_id = ids[0] if ids else ''
        elif isinstance(ids, dict):
            raw_id = ids.get('vod_id') or ids.get('id') or ''
        else:
            raw_id = str(ids).split(',')[0]
        vod_id = self._digits(raw_id)
        if not vod_id:
            return {'list': []}
        h = self._html('%s/detail/%s/' % (self.base, vod_id))
        if not h:
            return {'list': []}
        title = ''
        m = re.search(r'og:title"\s+content="([^"]*)"', h)
        if m:
            title = m.group(1).strip()
        if not title:
            m = re.search(r'<h1 class="vd-title">[\s\S]{0,260}?>\s*([^<]{1,80})\s*<', h)
            title = m.group(1).strip() if m else ('视频' + vod_id)
        pic = ''
        m = re.search(r'og:image"\s+content="([^"]*)"', h)
        if m:
            pic = m.group(1).strip()
        desc = ''
        m = re.search(r'og:description"\s+content="([^"]*)"', h)
        if m:
            desc = m.group(1).strip()
        if pic.startswith('//'):
            pic = 'https:' + pic

        # ---- 线路：完全按站点实际播放源生成，站点几条就几条，不自造线路 ----
        # 选集列表在播放页 .vp-episode-list，每个播放源一组 data-sid
        ph = self._html('%s/play/%s-1-1/' % (self.base, vod_id))
        eps, sname, pvid = self._play_sources(ph)
        if not eps:
            # 播放页拿不到才退回详情页备注（不凭空补集）
            m = re.search(r'更新至\s*(\d+)\s*集', h) or re.search(r'全\s*(\d+)\s*集', h)
            total = int(m.group(1)) if m else 1
            total = min(max(total, 1), 300)
            eps = {1: [(i, '第%d集' % i) for i in range(1, total + 1)]}
        hgid = pvid or self._hgvid(pic, vod_id)

        froms, urls = [], []
        for sid in sorted(eps.keys()):
            label = sname if len(eps) == 1 else '%s%d' % (sname, sid)
            froms.append(label)
            # 地址字段: 真实vid|集|vod_id|sid（不同源的真实vid 各自在播放时按需解析）
            v = hgid if sid == sorted(eps.keys())[0] else ''
            urls.append('#'.join('%s$%s|%d|%s|%d' % (lab, v, n, vod_id, sid)
                                 for n, lab in eps[sid]))
        total = max(len(v) for v in eps.values())

        item = {
            'vod_id': vod_id,
            'vod_name': title,
            'vod_pic': pic,
            'vod_remarks': ('更新至%d集' % total) if total > 1 else '正片',
            'vod_year': '',
            'vod_area': '',
            'vod_lang': '国语',
            'vod_actor': '',
            'vod_director': '',
            'vod_content': desc,
            'type_name': 'AI短剧',
            'vod_play_from': '$$$'.join(froms),
            'vod_play_url': '$$$'.join(urls),
        }
        return {'list': [item]}

    # ---------- 搜索 ----------
    def searchContent(self, key, quick=False, pg='1'):
        try:
            pg = max(int(str(pg)), 1)
        except Exception:
            pg = 1
        kw = quote(str(key))
        if pg <= 1:
            url = '%s/search/%s-------------/' % (self.base, kw)
        else:
            url = '%s/search/%s-------------/page/%d/' % (self.base, kw, pg)
        h = self._html(url)
        lst = self._cards(h, '')
        return {'list': lst, 'page': pg}

    # ---------- 播放 ----------
    def _media(self, hgid, ep):
        """调 huangguo 网关拿 media(m3u8) 绝对地址"""
        for i in range(3):
            url = '%s/huangguo.php?ac=play&id=%s&ep=%s&_=%d' % (
                self.base, hgid, ep, int(time.time() * 1000))
            r = self._get(url, ref=PLAY_REF, xhr=True)
            if r is None:
                time.sleep(0.5)
                continue
            try:
                j = json.loads(self._text(r))
            except Exception:
                time.sleep(0.5)
                continue
            u = (j or {}).get('url') or ''
            if u:
                return urljoin(self.base + '/', u)
            time.sleep(0.5)
        return ''

    def _vid_from_play(self, vod_id, sid, ep):
        """按需从播放页取该集的真实 vid（不同源/不同集 vid 可能不同，取不到才走这里）"""
        if not vod_id:
            return ''
        p = self._html('%s/play/%s-%s-%s/' % (self.base, vod_id, sid or '1', ep or '1'))
        m = re.search(r'"url"\s*:\s*"(\d+)\s*\|', p)
        return m.group(1) if m else ''

    def playerContent(self, flag, id, vipFlags=None):
        # 地址字段: 真实vid|集|vod_id|sid（兼容旧的 模式|vid|集|vod_id 四段）
        seg = [x.strip() for x in str(id).strip().split('|')]
        if seg and seg[0] in ('d', 'p'):
            seg = seg[1:]
        vid = self._digits(seg[0]) if len(seg) > 0 else ''
        ep = self._digits(seg[1]) if len(seg) > 1 else '1'
        vodid = self._digits(seg[2]) if len(seg) > 2 else ''
        sid = self._digits(seg[3]) if len(seg) > 3 else '1'
        ep = ep or '1'
        sid = sid or '1'

        media = self._media(vid, ep) if vid else ''
        # 兜底：该集真实vid缺失/网关没给 → 回播放页按 sid+集 反查后重试
        if not media and vodid:
            v = self._vid_from_play(vodid, sid, ep)
            if v:
                media = self._media(v, ep)
        if not media:
            return {'parse': 0, 'url': '',
                    'header': {'User-Agent': UA, 'Referer': self.base + '/'}}

        return {'parse': 0, 'url': media,
                'header': {'User-Agent': UA, 'Referer': self.base + '/'}}

    # ---------- 本地代理：m3u8 根相对路径绝对化 ----------
    def localProxy(self, param):
        p = param.split('url=', 1)[-1] if 'url=' in param else param
        if '%' in p:
            p = unquote(p)
        if not p.startswith('http'):
            p = urljoin(self.base + '/', p)
        r = self._get(p, ref=self.base + '/')
        if r is None:
            return {'code': 404, 'content': b'', 'headers': {'Content-Type': 'text/plain'}}
        try:
            body = r.content
        except Exception:
            body = b''
        head = body[:64]
        if b'#EXTM3U' not in head:
            ct = 'application/octet-stream'
            try:
                ct = r.headers.get('Content-Type', ct) or ct
            except Exception:
                pass
            return {'code': 200, 'content': body, 'headers': {'Content-Type': ct}}
        text = body.decode('utf-8', 'ignore')
        out = []
        for ln in text.splitlines():
            s = ln.strip()
            if not s:
                continue
            if s.startswith('#'):
                if 'URI="' in s:
                    s = re.sub(r'URI="([^"]+)"',
                               lambda m: 'URI="%s"' % self._abs(m.group(1), p), s)
                out.append(s)
            else:
                out.append(self._abs(s, p))
        return {'code': 200, 'content': '\n'.join(out) + '\n',
                'headers': {'Content-Type': 'application/vnd.apple.mpegurl'}}

    def _abs(self, u, base_url):
        u = u.strip()
        if u.startswith('http'):
            return u
        if u.startswith('//'):
            return 'https:' + u
        if u.startswith('/'):
            return self.base + u
        return urljoin(base_url, u)

    # ---------- 其他钩子 ----------
    def isVideoFormat(self, url):
        return bool(re.search(r'\.(m3u8|mp4|flv|mkv|ts)(\?|$)', str(url), re.I))

    def manualVideoCheck(self):
        return False

    def getDependence(self):
        return []

    def destroy(self):
        return None

    def progressVideo(self, url, progress):
        return None

    def setVideoFlags(self, flags):
        return None
