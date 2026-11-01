# -*- coding: utf-8 -*-
# 追更 (原生版) — 把网页版「追更.html」缝进集多本地包的原生 py 源
# 数据与网页版同源 (2026-11-01 照 追更.html 协议移植):
# - 追更区: TMDB discover (api.tmdb.org, 网页同款 key), 8 平台 networks
#   + 4 排序 (追更模式/今日播出/最新上线/综合热度) + 4 类型 (剧集/电影/动漫/综艺)
# - 榜单区: RateFuse https://ratefuse.cn/api/charts/public 动态拉取建分类
# - 详情: 只搜玩偶一家 (2026-11-01 用户改定, 盘搜/觅搜已撤): 照网页版玩偶源
#   协议 — wogg 系多域名竞速锁定, MacCMS 搜索页取前 3 条结果进详情页抠网盘
#   链接 (.module-row-info p + 全页 anchor), 请求头 UA 只写 Mozilla/5.0 且
#   Referer 带请求地址本身 (照 wo 本人 req, 缺了会被防护拦)
# - 播放: 分享链接带提取码 (?pwd=) 加 push:// 前缀交 push_agent 接管 (parse:0);
#   裸链接真机实测会被 WebHTV 直喂 Exo 拿分享页 HTML 报解析失败,
#   只把码写在选集名里 Push 也看不到 (2026-11-01 AV 报告 6/10 教训)
# 请求层自有包装: 显式 timeout + 重试 + TMDB 双域名兜底 (本壳 base.fetch 默认仅 5 秒)
import json
import re
import time
from datetime import date
from urllib.parse import quote, urlencode, urljoin, unquote
from urllib.request import Request, build_opener, ProxyHandler, getproxies

from base.spider import Spider as BaseSpider

TMDB_KEY = '2894d9a1baf7812b451de03c801b0281'
TMDB_BASES = ['https://api.tmdb.org/3', 'https://api.themoviedb.org/3']
TMDB_IMG = 'https://image.tmdb.org/t/p/w342'
CHARTS_API = 'https://ratefuse.cn/api/charts/public'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'

# ---- 玩偶 (wogg 系 MacCMS 站) ----
WO_DOMAINS = ['https://woggpan.888484.xyz', 'https://woggpan.xxooo.cf',
              'https://www.wogg.net', 'https://wogg.xxooo.cf']
WO_CONF_TPL = '/vodsearch/-------------.html?wd={kw}&page={p}'
WO_TEMPLATES = [
    '/index.php/vod/search/page/{p}/wd/{kw}.html',
    '/vodsearch/-------------.html?wd={kw}&page={p}',
    '/index.php/vod/search/wd/{kw}.html',
    '/vodsearch/{kw}----------{p}---.html',
    '/index.php/vod/search.html?wd={kw}',
    '/search.html?wd={kw}',
]
WO_PAN_RE = re.compile(
    r'pan\.baidu\.com|pan\.quark\.cn|aliyundrive\.com|alipan\.com|pan\.xunlei\.com'
    r'|115\.com|115cdn\.com|123\d{0,4}\.(?:com|cn|net)|123pan\.(?:com|cn)'
    r'|cloud\.189\.cn|caiyun\.139\.com|yun\.139\.com|drive\.uc\.cn|pan\.uc\.cn'
    r'|magnet:\?|ed2k://', re.I)
WO_URL_RE = re.compile(r'https?://[^\s<>\"\'\)]+|magnet:\?[^\s<>\"\'\)]+|ed2k://[^\s<>\"\'\)]+')

PLATFORMS = [
    ('gz_domestic', '国内聚合', '2007|1419|1330|1605|1631'),
    ('gz_netflix', 'Netflix', '213'),
    ('gz_hbo', 'HBO Max', '49'),
    ('gz_disney', 'Disney+', '2739'),
    ('gz_appletv', 'Apple TV+', '2552'),
    ('gz_amazon', 'Amazon Prime', '1024'),
    ('gz_hulu', 'Hulu', '453'),
    ('gz_paramount', 'Paramount+', '4330'),
]
NET_OF = {tid: net for tid, _n, net in PLATFORMS}
SORTS = [
    {'n': '📅 追更模式', 'v': 'next_episode'},
    {'n': '📆 今日播出', 'v': 'daily_airing'},
    {'n': '🆕 最新上线', 'v': 'first_air_date.desc'},
    {'n': '⭐ 综合热度', 'v': 'popularity.desc'},
]
TYPES = [
    {'n': '🎥 电视剧集', 'v': 'tv'},
    {'n': '🎬 电影作品', 'v': 'movie'},
    {'n': '🌸 动漫动画', 'v': 'anime'},
    {'n': '🎤 综艺节目', 'v': 'variety'},
]
DISK_TYPES = [
    ('quark', '夸克'), ('aliyun', '阿里'), ('baidu', '百度'), ('uc', 'UC'),
    ('tianyi', '天翼'), ('xunlei', '迅雷'), ('123', '123'), ('115', '115'),
    ('mobile', '移动'), ('pikpak', 'PikPak'), ('guangya', '光鸭'),
    ('magnet', '磁力'), ('ed2k', '电驴'),
]
DISK_LABEL = dict(DISK_TYPES)
PLAYABLE = {'quark', 'aliyun', 'baidu', 'uc', 'tianyi', 'xunlei', '123', '115', 'mobile', 'pikpak', 'guangya'}


def wo_disk_type(url):
    u = url or ''
    if re.search(r'pan\.quark\.cn', u, re.I):
        return 'quark'
    if re.search(r'pan\.baidu\.com', u, re.I):
        return 'baidu'
    if re.search(r'aliyundrive\.com|alipan\.com', u, re.I):
        return 'aliyun'
    if re.search(r'drive\.uc\.cn|pan\.uc\.cn', u, re.I):
        return 'uc'
    if re.search(r'pan\.xunlei\.com', u, re.I):
        return 'xunlei'
    if re.search(r'115\.com|115cdn\.com', u, re.I):
        return '115'
    if re.search(r'cloud\.189\.cn', u, re.I):
        return 'tianyi'
    if re.search(r'caiyun\.139\.com|yun\.139\.com', u, re.I):
        return 'mobile'
    if re.search(r'123\d{0,4}\.(?:com|cn|net)|123pan\.(?:com|cn)', u, re.I):
        return '123'
    if u.lower().startswith('magnet:'):
        return 'magnet'
    if u.lower().startswith('ed2k:'):
        return 'ed2k'
    return 'other'


class Spider(BaseSpider):
    def getName(self):
        return '追更'

    def init(self, extend=''):
        self.opener = build_opener(ProxyHandler(getproxies()))
        self._charts = None
        self._charts_at = 0
        self._wo_base = None

    # ---------------- 请求层 ----------------
    def _req(self, url, data=None, headers=None, timeout=15, tries=2):
        err = None
        for _ in range(tries):
            try:
                hd = {'User-Agent': UA}
                if headers:
                    hd.update(headers)
                body = None
                if data is not None:
                    body = json.dumps(data).encode('utf-8')
                    hd['Content-Type'] = 'application/json'
                req = Request(url, data=body, headers=hd)
                with self.opener.open(req, timeout=timeout) as r:
                    return r.read().decode('utf-8', 'replace')
            except Exception as e:
                err = e
                time.sleep(0.5)
        raise err

    def _json(self, url, data=None, headers=None, timeout=15, tries=2):
        return json.loads(self._req(url, data=data, headers=headers, timeout=timeout, tries=tries))

    def _tmdb(self, path, params=None):
        p = {'api_key': TMDB_KEY, 'language': 'zh-CN'}
        if params:
            p.update(params)
        qs = urlencode(p)
        err = None
        for base in TMDB_BASES:
            try:
                return self._json(base + path + '?' + qs, timeout=15, tries=1)
            except Exception as e:
                err = e
        raise err

    def _wo_get(self, url):
        # 照 wo 本人 req: UA 只写 Mozilla/5.0, Referer 带请求地址本身
        return self._req(url, headers={'User-Agent': 'Mozilla/5.0', 'Referer': url},
                         timeout=15, tries=1)

    # ---------------- 数据整形 ----------------
    def _vod(self, media, item):
        name = item.get('name') or item.get('title') or ''
        if not name:
            return None
        d = item.get('first_air_date') or item.get('release_date') or ''
        year = d[:4] if d else ''
        vote = item.get('vote_average') or 0
        rem = []
        if vote:
            rem.append('⭐%.1f' % vote)
        if year:
            rem.append(year)
        pic = item.get('poster_path') or ''
        return {
            'vod_id': 'tmdb:%s:%s' % (media, item.get('id')),
            'vod_name': name,
            'vod_pic': (TMDB_IMG + pic) if pic else '',
            'vod_remarks': ' · '.join(rem),
        }

    def _charts_list(self):
        if self._charts is not None and time.time() - self._charts_at < 600:
            return self._charts
        charts = []
        try:
            data = self._json(CHARTS_API, timeout=15)
            if isinstance(data, list):
                charts = [c for c in data if c.get('visible') is not False and c.get('entries')]
        except Exception:
            charts = []
        self._charts = charts
        self._charts_at = time.time()
        return charts

    def _classes(self):
        cls = [{'type_id': tid, 'type_name': name} for tid, name, _net in PLATFORMS]
        for i, c in enumerate(self._charts_list()):
            cls.append({'type_id': 'chart:%d' % i, 'type_name': c.get('chart_name') or ('榜单%d' % i)})
        return cls

    def _filters(self):
        f = {}
        for tid, _name, _net in PLATFORMS:
            f[tid] = [
                {'key': 's', 'name': '排序', 'value': SORTS},
                {'key': 't', 'name': '类型', 'value': TYPES},
            ]
        return f

    def _discover(self, tid, pg, extend):
        sort = (extend or {}).get('s') or 'next_episode'
        typ = (extend or {}).get('t') or 'tv'
        media = 'movie' if typ == 'movie' else 'tv'
        params = {'page': pg, 'with_networks': NET_OF[tid]}
        if typ == 'anime':
            params['with_genres'] = '16'
        elif typ == 'variety':
            params['with_genres'] = '10764|10767'
        today = date.today().isoformat()
        if sort == 'daily_airing':
            params['sort_by'] = 'popularity.desc'
            if media == 'tv':
                params['air_date.gte'] = today
                params['air_date.lte'] = today
            else:
                params['primary_release_date.gte'] = today
                params['primary_release_date.lte'] = today
        elif sort == 'first_air_date.desc':
            params['sort_by'] = 'primary_release_date.desc' if media == 'movie' else 'first_air_date.desc'
        else:
            params['sort_by'] = 'popularity.desc'
        data = self._tmdb('/discover/' + media, params)
        vods = []
        for item in data.get('results') or []:
            v = self._vod(media, item)
            if v:
                vods.append(v)
        return {'list': vods, 'page': int(data.get('page') or pg),
                'pagecount': int(data.get('total_pages') or pg),
                'limit': len(vods), 'total': int(data.get('total_results') or len(vods))}

    # ---------------- TVBox 接口 ----------------
    def homeContent(self, filter=False):
        result = {'class': self._classes()}
        if filter:
            result['filters'] = self._filters()
        try:
            result['list'] = self._discover('gz_domestic', 1, {}).get('list', [])
        except Exception:
            result['list'] = []
        return result

    def homeVideoContent(self):
        try:
            return self._discover('gz_domestic', 1, {})
        except Exception:
            return {'list': []}

    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg or 1)
        if tid.startswith('chart:'):
            charts = self._charts_list()
            try:
                chart = charts[int(tid.split(':')[1])]
            except Exception:
                return {'list': []}
            entries = chart.get('entries') or []
            size = 30
            total = len(entries)
            pagecount = max(1, (total + size - 1) // size)
            part = entries[(pg - 1) * size: pg * size]
            vods = []
            for e in part:
                media = e.get('media_type') or chart.get('media_type') or 'movie'
                if media not in ('tv', 'movie'):
                    media = 'movie'
                vods.append({
                    'vod_id': 'tmdb:%s:%s' % (media, e.get('tmdb_id')),
                    'vod_name': e.get('title') or '',
                    'vod_pic': e.get('poster') or '',
                    'vod_remarks': '第%s名' % e.get('rank'),
                })
            return {'list': vods, 'page': pg, 'pagecount': pagecount, 'limit': len(vods), 'total': total}
        try:
            return self._discover(tid, pg, extend or {})
        except Exception:
            return {'list': []}

    def searchContent(self, key, quick, pg=1):
        pg = int(pg or 1)
        try:
            data = self._tmdb('/search/multi', {'query': key, 'page': pg})
        except Exception:
            return {'list': []}
        vods = []
        for item in data.get('results') or []:
            media = item.get('media_type')
            if media not in ('tv', 'movie'):
                continue
            v = self._vod(media, item)
            if v:
                vods.append(v)
        return {'list': vods, 'page': pg,
                'pagecount': int(data.get('total_pages') or pg),
                'limit': len(vods), 'total': int(data.get('total_results') or len(vods))}

    # ---------------- 玩偶搜索 ----------------
    def _normalize_pan(self, merged):
        out, seen = [], set()
        merged = merged or {}
        order = [t for t, _l in DISK_TYPES if t in merged] + [t for t in merged if t not in DISK_LABEL]
        for t in order:
            if t not in PLAYABLE:
                continue
            links = merged.get(t)
            if not isinstance(links, list):
                continue
            for link in links:
                if not isinstance(link, dict):
                    continue
                url = str(link.get('url') or link.get('link') or link.get('href') or '').strip()
                if not url or url in seen:
                    continue
                seen.add(url)
                title = str(link.get('title') or link.get('name') or link.get('note') or '').strip() or url
                title = title.replace('\n', ' ').replace('$', ' ').replace('#', ' ')[:70]
                pwd = str(link.get('password') or link.get('pass') or '').strip()
                name = '[%s] %s' % (DISK_LABEL.get(t, t), title)
                if pwd:
                    name += ' [码 %s]' % pwd
                    # 提取码必须随链接一起交出去: 只写在名字里 Push 看不到
                    if 'pwd=' not in url:
                        url += ('&' if '?' in url else '?') + 'pwd=' + pwd
                out.append(name + '$' + url)
                if len(out) >= 80:
                    return out
        return out

    def _wo_jobs(self, kw):
        """玩偶搜索页 -> [(详情页url, 标题)]; 域名竞速: 先试已锁定域名, 出条目即锁定"""
        ekw = quote(kw)
        bases = ([self._wo_base] if self._wo_base else []) + [b for b in WO_DOMAINS if b != self._wo_base]
        templates = [WO_CONF_TPL] + [t for t in WO_TEMPLATES if t != WO_CONF_TPL]
        for tpl in templates:
            path = tpl.replace('{kw}', ekw).replace('{p}', '1')
            for base in bases:
                try:
                    html = self._wo_get(base + path)
                except Exception:
                    continue
                jobs = self._wo_parse_search(html, base)
                if jobs:
                    self._wo_base = base
                    return jobs
        return []

    def _wo_parse_search(self, html, base):
        if 'module-search-item' not in html and 'module-item' not in html:
            return []
        jobs, seen = [], set()
        # 结果块里的详情链接: 优先 /voddetail/ 与 /detail/ 形态
        for m in re.finditer(r'href="([^"]*(?:voddetail|/detail/)[^"]*)"([^>]*)>', html):
            href = m.group(1)
            if href in seen:
                continue
            seen.add(href)
            url = urljoin(base + '/', href)
            tmatch = re.search(r'title="([^"]*)"', m.group(2) or '')
            title = (tmatch.group(1) if tmatch else '').strip()
            if not title:
                seg = html[m.end():m.end() + 300]
                tm = re.search(r'(?:module-item-title|module-search-item-title|video-title)[^>]*>([^<]{2,80})<', seg)
                if not tm:
                    tm = re.search(r'<h[34][^>]*>(?:<a[^>]*>)?([^<]{2,80})<', seg)
                title = tm.group(1).strip() if tm else ''
            jobs.append((url, title))
            if len(jobs) >= 20:
                break
        return jobs

    def _wo_extract(self, html, job_title):
        """详情页 HTML -> merged_by_type (照网页版 woExtractMerged 的全页抠链)"""
        merged = {}
        text = re.sub(r'<script[\s\S]*?</script>|<style[\s\S]*?</style>', ' ', html or '')
        for m in WO_URL_RE.finditer(text):
            url = m.group(0).rstrip('.,;)')
            if not WO_PAN_RE.search(url):
                continue
            t = wo_disk_type(url)
            if t in ('magnet', 'ed2k', 'other'):
                continue
            pwd = ''
            pm = re.search(r'[?&](?:pwd|password)=([A-Za-z0-9]+)', url)
            if pm:
                pwd = pm.group(1)
            else:
                # 链接后 200 字符内找「提取码: xxxx」(去标签后的文本窗口)
                tail = re.sub(r'<[^>]+>', ' ', text[m.end():m.end() + 400])
                cm = re.search(r'(?:提取码|访问码|密码)\s*[:：]?\s*([A-Za-z0-9]{4,8})', tail)
                if cm:
                    pwd = cm.group(1)
            item = {'url': url, 'title': job_title}
            if pwd:
                item['password'] = pwd
            merged.setdefault(t, []).append(item)
        return merged

    def _search_wanou(self, kw):
        jobs = self._wo_jobs(kw)
        merged = {}
        for url, title in jobs[:3]:
            try:
                html = self._wo_get(url)
            except Exception:
                continue
            part = self._wo_extract(html, title or kw)
            for t, items in part.items():
                merged.setdefault(t, []).extend(items)
            if merged:
                break
        return self._normalize_pan(merged)

    def detailContent(self, ids):
        vid = ids[0] if ids else ''
        parts = vid.split(':')
        if len(parts) != 3 or parts[0] != 'tmdb':
            return {'list': []}
        media, tid = parts[1], parts[2]
        try:
            info = self._tmdb('/%s/%s' % (media, tid), {})
        except Exception:
            info = {}
        name = info.get('name') or info.get('title') or ''
        d = info.get('first_air_date') or info.get('release_date') or ''
        genres = ' '.join(g.get('name', '') for g in (info.get('genres') or []))
        vote = info.get('vote_average') or 0
        poster = info.get('poster_path') or ''
        eps = []
        if name:
            try:
                eps = self._search_wanou(name)
            except Exception:
                eps = []
        content = info.get('overview') or ''
        if not eps:
            content = ('（玩偶未搜到网盘资源）' + content) if content else '玩偶未搜到网盘资源，换个片名或稍后再试'
        vod = {
            'vod_id': vid,
            'vod_name': name,
            'vod_pic': (TMDB_IMG + poster) if poster else '',
            'vod_year': d[:4] if d else '',
            'vod_remarks': ('⭐%.1f' % vote) if vote else '',
            'vod_actor': '',
            'vod_director': '',
            'vod_content': content,
            'type_name': genres,
            'vod_play_from': '玩偶' if eps else '',
            'vod_play_url': '#'.join(eps),
        }
        return {'list': [vod]}

    def playerContent(self, flag, id, vipFlags):
        # 分享链接加 push:// 交 push_agent 接管; 裸链接会被壳子直喂播放器拿分享页 HTML
        url = id or ''
        if url.startswith('http') and not url.startswith('push://'):
            url = 'push://' + url
        return {'parse': 0, 'playUrl': '', 'url': url, 'header': ''}

    def localProxy(self, params):
        return None
