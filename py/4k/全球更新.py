# -*- coding: utf-8 -*-
"""
全球追更 TVBox 爬虫源（dr_py / T4 接口源）
==================================================================
由网页「全球追更」改造而来，复用其三条数据链路：
  1) 榜单聚合   : https://ratefuse.cn/api/charts/public （豆瓣/IMDb/烂番茄/Metacritic/Letterboxd/TMDB/Trakt）
  2) 流媒体追更 : https://api.tmdb.org/3 的 discover + on_the_air / airing_today（按平台/排序/类型筛选）
  3) 网盘资源   : 自部署盘搜 http://61.147.247.66:52440 与 https://so.252035.xyz 及觅搜 www.mipan.so
vod_id 统一编码为 tmdb:{movie|tv}:{tmdb_id}，分类 type_id 为 gz|{平台} 与 chart|{榜单平台}。

【详情页选集（本版重点修复）】
原版详情页把「网盘整包」当成剧集列出来（标题是「庆余年(两季合集)【4K…】$https://pan.quark.cn/s/…」），
所以壳里看不到真正的「第 1 集 / 第 2 集」选集。本版改为：
  * 集号、剧集名、播出日期来自 TMDB 季/集数据。一次请求批量取回多季
    （append_to_response=season/1,season/2,…；TMDB 会静默忽略不存在的季，可放心批量）；
  * 每集对应网盘里的哪一份资源，由资源标题/备注里的集数标记反推：
    「更EP31」「更新至05集」「更04」「全36集」「36集完结」「S01E01 - E05」「S01E02」「第1集」「S01全」等，
    解析成「季范围 + 集区间」后与 TMDB 集号求交集，取画质最好且确实覆盖该集的资源；
  * 资源标记只覆盖到第 N 集时，N 之后的集会自动落到「覆盖到最近的那一包」，保证每集都有可点地址；
  * 网盘接口抖动导致检索失败、或某集暂时没有可用资源时，该集写成「点播时再检索」的播放 ID，
    点播那一刻再联网检索该集对应的资源，保证详情页永远有逐集选集。

已知限制：
  - 网盘（夸克/阿里/UC/迅雷/115…）与磁力/电驴资源返回的是分享链接，能否直接播放取决于
    壳子是否带网盘播放能力（如 WebHTV、影视网盘插件）；原生 TVBox 只能播 magnet/ed2k（雷插件）与直链。
  - 网盘检索接口偶发 400/超时/空结果，已做多源合并 + 退避重试 + 结果缓存。
"""
import json
import math
import re
import sys
import time
import types
from urllib.parse import urlencode, urlparse, parse_qsl, urlunparse, quote, unquote

# ---------------------------------------------------------------- T4 运行时适配
# 影视仓/羊壳/海阔/蜂蜜壳/鱼壳提供 base.spider；其它环境（本地自检）注入一个最小基类，
# 保证本文件在任意 Python 3 里都能被 import + 实例化。
try:
    import base.spider as _base_spider  # noqa: F401
except Exception:  # pragma: no cover - 仅本地自检环境
    _base_pkg = types.ModuleType('base')
    _base_pkg.__path__ = []
    _base_mod = types.ModuleType('base.spider')

    class _StubSpider(object):
        def __init__(self):
            self.s = None

    _base_mod.Spider = _StubSpider
    _base_pkg.spider = _base_mod
    sys.modules['base'] = _base_pkg
    sys.modules['base.spider'] = _base_mod

from base.spider import Spider

# ---------------------------------------------------------------- requests 降级
try:
    import requests
except ImportError:  # pragma: no cover - 无 requests 的环境用 urllib 兜底
    import ssl as _ssl
    import urllib.error as _urllib_error
    import urllib.parse as _urllib_parse
    import urllib.request as _urllib_request

    class _UrllibResponse(object):
        def __init__(self, status, headers, body, url):
            self.status_code = status
            self.status = status
            self.headers = headers
            self.content = body
            self.url = url
            self.encoding = 'utf-8'
            self.apparent_encoding = 'utf-8'
            charset = ''
            m = re.search(br'charset=["\']?([\w-]+)', body[:2048], re.I)
            if m:
                charset = m.group(1).decode('ascii', 'ignore')
            try:
                self.text = body.decode(charset or 'utf-8', 'replace')
            except Exception:
                self.text = body.decode('utf-8', 'replace')

        def json(self):
            return json.loads(self.text or '{}')

        def iter_content(self, size=8192):
            yield self.content[:size] if size else self.content

        def close(self):
            pass

    class _UrllibSession(object):
        def __init__(self):
            self.headers = {}
            self.proxies = {}

        def get(self, url, **kw):
            return self._request('GET', url, **kw)

        def post(self, url, **kw):
            return self._request('POST', url, **kw)

        def _request(self, method, url, **kw):
            headers = dict(self.headers)
            headers.update(kw.get('headers') or {})
            payload = kw.get('data')
            body = None
            if isinstance(payload, dict):
                body = _urllib_parse.urlencode(payload).encode('utf-8')
            elif isinstance(payload, (bytes, bytearray)):
                body = bytes(payload)
            elif isinstance(payload, str):
                body = payload.encode('utf-8')
            req = _urllib_request.Request(url, data=body, headers=headers, method=method)
            handlers = [_urllib_request.HTTPSHandler(context=_ssl._create_unverified_context())]
            proxies = kw.get('proxies') or self.proxies or {}
            if proxies:
                handlers.append(_urllib_request.ProxyHandler(proxies))
            opener = _urllib_request.build_opener(*handlers)
            try:
                with opener.open(req, timeout=kw.get('timeout') or 20) as resp:
                    return _UrllibResponse(resp.getcode(), dict(resp.headers or {}), resp.read(), resp.geturl())
            except _urllib_error.HTTPError as e:
                return _UrllibResponse(e.code, dict(e.headers or {}), e.read() or b'', url)
            except Exception:
                return _UrllibResponse(0, {}, b'', url)

    class _RequestsShim(object):
        Session = _UrllibSession

    requests = _RequestsShim()

DEFAULT_CONFIG = {
    'chart_api': 'https://ratefuse.cn/api/charts/public',
    'tmdb_api': 'https://api.tmdb.org/3',
    'tmdb_key': '2894d9a1baf7812b451de03c801b0281',
    'tmdb_poster': 'https://images.tmdb.org/t/p/w500',
    'pan_bases': ['http://61.147.247.66:52440', 'https://so.252035.xyz'],
    'mipan_api': 'https://www.mipan.so',
    'ua': ('Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 '
           '(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36'),
    'charts_ttl': 600,
    'max_pan_items': 60,
    'cache_ttl': 300,
    'page_limit': 20,
    'max_special_eps': 50,
    'max_season_eps': 300,
}

HEADERS = {
    'User-Agent': DEFAULT_CONFIG['ua'],
    'Accept': 'application/json, text/plain, */*',
    'Referer': 'https://ratefuse.cn/',
}

# 追更平台（network 取自网页 GZ_PLATFORMS）
PLATFORMS = [
    ('domestic', '国内聚合', '2007|1419|1330|1605|1631'),
    ('netflix', 'Netflix', '213'),
    ('hbo', 'HBO Max', '49'),
    ('disney', 'Disney+', '2739'),
    ('appletv', 'Apple TV+', '2552'),
    ('amazon', 'Amazon Prime', '1024'),
    ('hulu', 'Hulu', '453'),
    ('paramount', 'Paramount+', '4330'),
]
PLATFORM_ORDER = ['豆瓣', 'IMDb', 'Rotten Tomatoes', 'Metacritic', 'Letterboxd', 'TMDB', 'Trakt']

SORTS = [
    ('📅 追更模式', 'next_episode'),
    ('📆 今日播出', 'daily_airing'),
    ('🆕 最新上线', 'first_air_date.desc'),
    ('⭐ 综合热度', 'popularity.desc'),
]
TYPES = [
    ('🎥 电视剧集', 'tv'),
    ('🎬 电影作品', 'movie'),
    ('🌸 动漫动画', 'anime'),
    ('🎤 综艺节目', 'variety'),
]

DISK_TYPES = [
    ('quark', '夸克'), ('aliyun', '阿里'), ('baidu', '百度'), ('uc', 'UC'),
    ('tianyi', '天翼'), ('xunlei', '迅雷'), ('123', '123'), ('115', '115'),
    ('mobile', '移动'), ('pikpak', 'PikPak'), ('guangya', '光鸭'),
    ('magnet', '磁力'), ('ed2k', '电驴'),
]
DISK_ORDER = [t for t, _ in DISK_TYPES]
DISK_NAME = dict(DISK_TYPES)

VIDEO_EXT_RE = re.compile(r'\.(m3u8|mp4|flv|mkv|avi|mov|ts|m4v|webm)(\?|#|$)', re.I)
# 年份，用于区分「庆余年 (2019)」(第一季) 与「庆余年2 (2024)」(第二季)
YEAR_RE = re.compile(r'(?<!\d)((?:19|20)\d{2})(?!\d)')
# 网盘分享链接域名：由壳的网盘插件接管，不做直链实测
NETDISK_HOST_RE = re.compile(
    r'pan\.quark\.cn|pan\.baidu\.com|drive\.uc\.cn|pan\.xunlei\.com|anxia\.com|'
    r'cloud\.189\.cn|www\.aliyundrive\.com|www\.aliyun\.com|pan\.123pan\.com|'
    r'123684\.com|www\.weiyipan\.com|pan\.mypikpak\.com|pikpak\.com|pan\.gaoyun\.com|'
    r'pan\.other031\.com|file\.yunsuo\.com|yun\.139\.com|pan\.titan\.com|pan\.ncloud\.net', re.I)

# 播放 ID 前缀：gz: 已解析好的地址；gzl: 点播时再检索
ID_READY = 'gz:'
ID_LAZY = 'gzl:'

CN_NUM = {'零': 0, '一': 1, '二': 2, '两': 2, '三': 3, '四': 4, '五': 5,
          '六': 6, '七': 7, '八': 8, '九': 9, '十': 10}
# 中文数字字符集（注意要包含「两」「零」，否则「两季合集」这类标题会漏判）
CN_CHARS = '0-9零一二三四五六七八九十两'

# 有声书/小说/电子书类资源不是视频，不能当剧集播放，直接剔除
NOVEL_RE = re.compile(r'有声|小说|有声书|有声读物|全本|精校|配音|播音|评书|'
                       r'\.txt|\.epub|\.pdf|\.mobi|\.doc', re.I)


def _has_cjk(s):
    return bool(re.search(r'[\u4e00-\u9fff]', s or ''))


def _cn_int(text):
    """把「一/两/十/十二」这类中文数字转成整数，失败返回 None。"""
    s = str(text or '').strip()
    if not s:
        return None
    if s.isdigit():
        return int(s)
    if s in CN_NUM:
        return CN_NUM[s]
    if len(s) == 2 and s[0] == '十' and s[1] in CN_NUM:
        return 10 + CN_NUM[s[1]]
    if len(s) == 2 and s[1] == '十' and s[0] in CN_NUM:
        return CN_NUM[s[0]] * 10
    if len(s) == 3 and s[1] == '十':
        a, b = CN_NUM.get(s[0]), CN_NUM.get(s[2])
        if a is not None and b is not None:
            return a * 10 + b
    return None


def _tmdb_pic(path):
    """把 TMDB 图片相对路径拼成统一前缀；相对路径以 / 开头只拼一个斜杠。"""
    p = str(path or '').strip()
    if not p:
        return ''
    if re.match(r'^(https?:)?//', p, re.I):
        return _fix_pic(p)
    if not p.startswith('/'):
        p = '/' + p
    return DEFAULT_CONFIG['tmdb_poster'] + p


def _fix_pic(pic):
    """统一 TMDB 图片前缀：image(s).tmdb.org/t/p/<尺寸>/ 形式的地址、
    以及以 / 开头的 TMDB 相对路径，都改写成 DEFAULT_CONFIG['tmdb_poster']
    （默认 https://images.tmdb.org/t/p/w500）；非 TMDB 外链原样保留。"""
    if not pic:
        return ''
    pic = pic.replace('&' + 'amp;', '&').strip()
    if pic.startswith('//'):
        pic = 'https:' + pic
    m = re.match(r'^https?://(?:images?\.tmdb\.org)/t/p/[^/]+(/.*)$', pic, re.I)
    if m:
        return DEFAULT_CONFIG['tmdb_poster'] + m.group(1)
    if re.match(r'^https?://', pic, re.I):
        return pic
    if pic.startswith('/'):
        return DEFAULT_CONFIG['tmdb_poster'] + pic
    return pic


def _first_line(s):
    return str(s or '').split('\n')[0].strip()


def _clean_name(s):
    s = _first_line(s)
    s = re.sub(r'^[^\u4e00-\u9fa5A-Za-z0-9《]+', '', s)
    s = s.replace('✨', '').strip()
    return s


def _is_url(text):
    t = str(text or '').strip()
    if not t:
        return False
    return (t.startswith(('http://', 'https://', 'magnet:', 'ed2k://'))
            or t.startswith(ID_READY) or t.startswith(ID_LAZY))


def _first_arg(v):
    if isinstance(v, (list, tuple)):
        return str(v[0]).strip() if v else ''
    return str(v or '').strip()


class Spider(Spider):
    def __init__(self):
        try:
            super().__init__()
        except Exception:
            pass
        self.s = getattr(self, 's', None) or requests.Session()
        self.session = self.s
        self.sess = self.s
        self._charts_cache = []
        self._charts_ts = 0.0
        self._tmdb_cache = {}
        self._pan_cache = {}

    # ------------------------------------------------------------------ 基础
    def init(self, extend=None):
        return HEADERS

    def getName(self):
        return '全球追更'

    def getDependence(self):
        return []

    def _get_text(self, url, timeout=20):
        h = dict(HEADERS)
        r = None
        fetch = getattr(self, 'fetch', None)
        if callable(fetch):
            try:
                r = fetch(url, headers=h)
            except TypeError:
                try:
                    r = fetch(url, headers=h, timeout=timeout)
                except Exception:
                    r = None
            except Exception:
                r = None
        if isinstance(r, str):
            return r
        txt = getattr(r, 'text', None) if r is not None else None
        if txt:
            return txt
        try:
            r2 = self.s.get(url, headers=h, timeout=timeout)
            r2.encoding = r2.apparent_encoding or 'utf-8'
            txt = r2.text
        except Exception as e:
            print('get fail:', url, e)
            txt = ''
        return txt or ''

    def _get_json(self, url, timeout=20, retries=1):
        last = None
        for i in range(retries + 1):
            try:
                txt = self._get_text(url, timeout=timeout)
                if txt.strip():
                    return json.loads(txt)
                last = ValueError('empty body')
            except Exception as e:
                last = e
            time.sleep(0.4 * (i + 1))
        raise last if last else ValueError('request failed')

    def _post_json(self, url, payload, timeout=30):
        h = dict(HEADERS)
        h['Content-Type'] = 'application/json'
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        r = self.s.post(url, data=body, headers=h, timeout=timeout)
        r.encoding = r.apparent_encoding or 'utf-8'
        return json.loads(r.text or '{}')

    def _ext(self, extend, key, default=''):
        if not extend:
            return default
        try:
            if isinstance(extend, str):
                extend = json.loads(extend)
        except Exception:
            return default
        if isinstance(extend, dict):
            v = extend.get(key)
            return v if v not in (None, '') else default
        return default

    # --------------------------------------------------------------- 数据源
    def _charts(self):
        now = time.time()
        if self._charts_cache and now - self._charts_ts < DEFAULT_CONFIG['charts_ttl']:
            return self._charts_cache
        try:
            data = self._get_json(DEFAULT_CONFIG['chart_api'], timeout=25)
            if isinstance(data, list) and data:
                self._charts_cache = [c for c in data if isinstance(c, dict) and c.get('visible') is not False]
                self._charts_ts = now
        except Exception as e:
            print('charts error:', e)
        return self._charts_cache

    def _chart_platforms(self, charts):
        seen = [c.get('platform') for c in charts if c.get('platform')]
        uniq = []
        for p in seen:
            if p not in uniq:
                uniq.append(p)
        head = [p for p in PLATFORM_ORDER if p in uniq]
        tail = [p for p in uniq if p not in PLATFORM_ORDER]
        return head + tail

    def _tmdb(self, path, params=None, timeout=20):
        q = {'api_key': DEFAULT_CONFIG['tmdb_key'], 'language': 'zh-CN'}
        if params:
            q.update(params)
        url = DEFAULT_CONFIG['tmdb_api'] + path + '?' + urlencode(q)
        return self._get_json(url, timeout=timeout)

    def _tmdb_cached(self, path, params=None, timeout=20):
        key = path + '|' + json.dumps(params or {}, sort_keys=True, ensure_ascii=False)
        now = time.time()
        hit = self._tmdb_cache.get(key)
        if hit and now - hit[0] < DEFAULT_CONFIG['cache_ttl']:
            return hit[1]
        data = self._tmdb(path, params, timeout=timeout)
        self._tmdb_cache[key] = (now, data)
        return data

    # ------------------------------------------------------------------ 首页
    def homeContent(self, filter=False):
        result = {'class': [], 'filters': {}}
        try:
            charts = self._charts()
            for pid, name, _net in PLATFORMS:
                result['class'].append({'type_id': 'gz|' + pid, 'type_name': name})
            for p in self._chart_platforms(charts):
                result['class'].append({'type_id': 'chart|' + p, 'type_name': p + '榜单'})
            if filter:
                filters = {}
                for pid, _name, _net in PLATFORMS:
                    filters['gz|' + pid] = [
                        {'key': 'sort', 'name': '排序', 'value': [{'n': n, 'v': v} for n, v in SORTS]},
                        {'key': 'type', 'name': '类型', 'value': [{'n': n, 'v': v} for n, v in TYPES]},
                    ]
                for p in self._chart_platforms(charts):
                    lst = sorted([c for c in charts if c.get('platform') == p],
                                 key=lambda c: (c.get('sort_order') if isinstance(c.get('sort_order'), int) else 9999,
                                                str(c.get('chart_name') or '')))
                    vals = [{'n': str(c.get('chart_name') or '未命名榜单'), 'v': str(c.get('chart_name') or '')}
                            for c in lst if c.get('chart_name')]
                    if vals:
                        filters['chart|' + p] = [{'key': 'chart', 'name': '榜单', 'value': vals}]
                result['filters'] = filters
        except Exception as e:
            print('homeContent error:', e)
        return result

    def homeVideoContent(self):
        try:
            cc = self.categoryContent('gz|domestic', 1, False, {'sort': 'next_episode', 'type': 'tv'})
            return {'list': cc.get('list') or []}
        except Exception as e:
            print('homeVideoContent error:', e)
            return {'list': []}

    # ------------------------------------------------------------------ 分类
    def _vod_from_entry(self, item, remark=''):
        media = 'tv' if str(item.get('media_type')) == 'tv' else 'movie'
        return {
            'vod_id': 'tmdb:%s:%s' % (media, item.get('tmdb_id') or item.get('id') or ''),
            'vod_name': item.get('title') or item.get('name') or '',
            'vod_pic': _fix_pic(item.get('poster') or ''),
            'vod_remarks': remark,
        }

    def _vod_from_tmdb_item(self, it, media):
        date = it.get('first_air_date') or it.get('release_date') or ''
        rate = it.get('vote_average') or 0
        remark = '%s · %s' % (('%.1f分' % rate) if rate else '', date) if (rate or date) else ('剧集' if media == 'tv' else '电影')
        poster = it.get('poster_path')
        return {
            'vod_id': 'tmdb:%s:%s' % (media, it.get('id')),
            'vod_name': it.get('name') or it.get('title') or '',
            'vod_pic': _tmdb_pic(poster),
            'vod_remarks': remark.strip(' ·'),
        }

    def _category_gz(self, platform_id, pg, extend):
        plat = next((p for p in PLATFORMS if p[0] == platform_id), PLATFORMS[0])
        sort = self._ext(extend, 'sort', 'next_episode')
        vtype = self._ext(extend, 'type', 'tv')
        media = 'movie' if vtype == 'movie' else 'tv'
        nets = [n for n in plat[2].split('|') if n]
        endpoint = '/discover/movie' if media == 'movie' else '/discover/tv'
        base = {'page': pg, 'sort_by': ('popularity.desc' if sort in ('daily_airing', 'next_episode') else sort)}
        if vtype == 'anime':
            base['with_genres'] = '16'
        if vtype == 'variety':
            base['with_genres'] = '10764|10767'
        if sort == 'daily_airing':
            today = time.strftime('%Y-%m-%d')
            if media == 'tv':
                base['air_date.gte'] = today
                base['air_date.lte'] = today
            else:
                base['primary_release_date.gte'] = today
                base['primary_release_date.lte'] = today
        items = []
        pages = []
        for net in nets:
            try:
                data = self._tmdb(endpoint, dict(base, with_networks=net))
                items.extend(data.get('results') or [])
                pages.append(int(data.get('total_pages') or 1))
            except Exception as e:
                print('gz net fail:', net, e)
        # 「追更模式 / 今日播出」优先用 TMDB 的播出接口（语义更贴近追更），无结果再退回 discover
        if media == 'tv' and sort in ('daily_airing', 'next_episode') and not items:
            airing = '/tv/airing_today' if sort == 'daily_airing' else '/tv/on_the_air'
            try:
                data = self._tmdb(airing, {'page': pg})
                got = [it for it in (data.get('results') or []) if self._match_network(it, nets)]
                if got:
                    items = got
                    pages = [int(data.get('total_pages') or 1)]
            except Exception as e:
                print('gz airing fail:', airing, e)
        seen = set()
        fresh = []
        for it in items:
            iid = str(it.get('id') or '')
            if not iid or iid in seen:
                continue
            seen.add(iid)
            fresh.append(it)
        if sort == 'popularity.desc':
            fresh.sort(key=lambda x: -(x.get('popularity') or 0))
        else:
            fresh.sort(key=lambda x: str(x.get('first_air_date') or x.get('release_date') or ''), reverse=True)
        page_items = fresh[:20]
        page_total = max(pages) if pages else 1
        return {
            'list': [self._vod_from_tmdb_item(it, media) for it in page_items],
            'page': pg,
            'pagecount': min(page_total, 500),
            'limit': 20,
            'total': len(page_items),
        }

    def _match_network(self, item, nets):
        """按 network id 过滤 airing_today / on_the_air 的结果。"""
        ids = set()
        for n in (item.get('networks') or []):
            if isinstance(n, dict) and n.get('id') is not None:
                ids.add(str(n.get('id')))
        return bool(ids & set(str(x) for x in nets))

    def _category_chart(self, platform, pg, extend):
        charts = self._charts()
        lst = sorted([c for c in charts if c.get('platform') == platform],
                     key=lambda c: (c.get('sort_order') if isinstance(c.get('sort_order'), int) else 9999,
                                    str(c.get('chart_name') or '')))
        limit = DEFAULT_CONFIG['page_limit']
        if not lst:
            return self._page_result([], pg, limit)
        target = self._ext(extend, 'chart', '')
        chart = next((c for c in lst if str(c.get('chart_name')) == target), lst[0])
        entries = sorted([e for e in (chart.get('entries') or []) if isinstance(e, dict)],
                         key=lambda e: e.get('rank') if isinstance(e.get('rank'), int) else 9999)
        vods = [self._vod_from_entry(e, '第%s名' % (e.get('rank') if e.get('rank') not in (None, '') else '-')) for e in entries]
        total = len(vods)
        pages = max(1, int(math.ceil(total / float(limit))))
        start = (pg - 1) * limit
        return self._page_result(vods[start:start + limit], pg, limit, pages, total)

    def _page_result(self, vods, pg, limit, pages=None, total=None):
        if pages is None:
            pages = max(1, int(math.ceil((total or 0) / float(limit))))
        return {'list': vods, 'page': pg, 'pagecount': pages, 'limit': limit,
                'total': total if total is not None else len(vods)}

    def categoryContent(self, tid, pg=1, filter=False, extend=None):
        tid = str(tid or '')
        try:
            pg = int(pg) if str(pg).isdigit() else 1
        except Exception:
            pg = 1
        try:
            if tid.startswith('gz|'):
                return self._category_gz(tid.split('|', 1)[1], pg, extend)
            if tid.startswith('chart|'):
                return self._category_chart(tid.split('|', 1)[1], pg, extend)
        except Exception as e:
            print('categoryContent error:', tid, e)
        return self._page_result([], pg, DEFAULT_CONFIG['page_limit'])

    # ------------------------------------------------------------ 选集解析
    def _parse_span(self, text):
        """从资源标题/备注解析「季范围 + 集区间」。

        返回 dict：seasons(季号集合，None=不限季)、ep_lo/ep_hi(集区间，None=未知)、
        total(声明的总集数)、complete(是否整季/全集)。
        """
        raw = str(text or '')
        info = {'seasons': None, 'ep_lo': None, 'ep_hi': None, 'total': None,
                'complete': False, 'special': False}

        # S01E01 - E05 / S01E02
        m = re.search(r'S(\d{1,2})\s*E(\d{1,3})\s*[-~–—]\s*E?(\d{1,3})', raw, re.I)
        if m:
            info['seasons'] = {int(m.group(1))}
            info['ep_lo'] = int(m.group(2))
            info['ep_hi'] = int(m.group(3))
            return info
        m = re.search(r'S(\d{1,2})\s*E(\d{1,3})', raw, re.I)
        if m:
            info['seasons'] = {int(m.group(1))}
            info['ep_lo'] = int(m.group(2))
            info['ep_hi'] = int(m.group(2))
            return info

        # 季范围
        seasons = set()
        for pat in (r'S(\d{1,2})(?!\s*E)(?!\d)', r'Season\s*(\d{1,2})',
                    r'第\s*([' + CN_CHARS + r']{1,3})\s*[季部]'):
            for mm in re.finditer(pat, raw, re.I):
                v = _cn_int(mm.group(1))
                if v is not None and v >= 0:
                    seasons.add(v)
        m = re.search(r'(\d{1,2})\s*[-~–—]\s*(\d{1,2})\s*季', raw)
        if m:
            seasons |= set(range(int(m.group(1)), int(m.group(2)) + 1))
        m = re.search(r'全\s*([' + CN_CHARS + r']{1,3})\s*季', raw)
        if m:
            v = _cn_int(m.group(1))
            if v:
                seasons |= set(range(1, v + 1))
        m = re.search(r'([' + CN_CHARS + r']{1,3})\s*季\s*合集', raw)
        if m:
            v = _cn_int(m.group(1))
            if v:
                seasons |= set(range(1, v + 1))
        # 「特别版 / 特别篇 / Specials」对应 TMDB 的 season 0（番外/外传不算，
        # 因为小说《附带番外》也会命中，会把小说误当成特别篇）
        special = bool(re.search(r'特别版|特别篇|Specials?\b', raw, re.I))
        if seasons:
            info['seasons'] = seasons
        info['special'] = special

        # 集区间
        for pat, kind in (
            (r'更\s*EP\s*(\d{1,3})', 'upto'),
            (r'更新\s*EP\s*(\d{1,3})', 'upto'),
            (r'更新\s*至\s*(\d{1,3})\s*集', 'upto'),
            (r'更新\s*(\d{1,3})\s*集', 'upto'),
            (r'更\s*E\s*P?\s*(\d{1,3})', 'upto'),
            (r'第\s*([' + CN_CHARS + r']{1,3})\s*集', 'single'),
            (r'全\s*(\d{1,3})\s*集', 'total'),
            (r'(\d{1,3})\s*集\s*完结', 'total'),
            (r'(\d{1,3})\s*集\s*全', 'total'),
            (r'(\d{1,3})\s*集', 'total'),
            (r'更\s*(\d{1,3})(?!\d)', 'upto'),
            (r'EP\s*(\d{1,3})', 'upto'),
            (r'更新\s*(\d{1,3})(?!\d)', 'upto'),
        ):
            mm = re.search(pat, raw, re.I)
            if not mm:
                continue
            n = _cn_int(mm.group(1))
            if n is None:
                continue
            if kind == 'single':
                info['ep_lo'] = n
                info['ep_hi'] = n
            elif kind == 'total':
                info['ep_lo'] = 1
                info['ep_hi'] = n
                info['total'] = n
                info['complete'] = True
            else:
                info['ep_lo'] = 1
                info['ep_hi'] = n
            break
        if info['ep_lo'] is None and re.search(r'全集|完结|COMPLETE|S(\d{1,2})\s*全', raw, re.I):
            info['ep_lo'] = 1
            info['ep_hi'] = None
            info['complete'] = True
        return info

    def _tmdb_tag(self, text):
        m = re.search(r'\{tmdb-(\d+)\}', str(text or ''))
        return int(m.group(1)) if m else None

    def _title_season(self, title, show_name):
        """「庆余年2」这类剧名后紧跟数字的，数字通常就是季号。

        只认「剧名+数字」紧贴写法（不认年份），避免把「庆余年 2019」当成第 20 季。
        """
        name = str(show_name or '').strip()
        if not name:
            return None
        m = re.search(re.escape(name) + r'(\d{1,2})(?!\d)', str(title or ''))
        return int(m.group(1)) if m else None

    def _pick_for_episode(self, items, show_name, season_no, ep_no, season_total, tmdb_id, season_year=0):
        """在网盘资源里为 (季, 集) 挑一份最合适的。

        先按「季归属」分层（tier），同层再按画质/集数吻合度打分。
        分层能保证「第 1 季专属包」永远排在「两季合集包」前面，
        不会被合集的高画质标签喧宾夺主。

        season_year 是该季在 TMDB 上的首播年份，用来区分「庆余年(2019)」和「庆余年2 (2024)」。
        """
        best = None
        best_key = None
        for it in items:
            tag = it.get('tmdb_tag')
            if tag is not None and tmdb_id is not None and tag != tmdb_id:
                continue  # 明确标注了别的剧
            title = it.get('title') or ''
            span = it.get('span') or {}
            seasons = span.get('seasons')
            special = bool(span.get('special'))
            t_season = self._title_season(title, show_name)
            if t_season is not None and t_season != season_no:
                continue  # 「庆余年2」是第二季，不该出现在第一季
            if season_no == 0:
                # 特别篇：优先「特别版/特别篇」专属包；没有就退到第一季的包
                # （网盘里「第1季+特别版」这类包通常把番外一起打包了）
                if not (special or (seasons and (0 in seasons or 1 in seasons)) or not seasons):
                    continue
            elif seasons:
                if season_no not in seasons:
                    continue
            lo, hi = span.get('ep_lo'), span.get('ep_hi')
            if lo is not None and ep_no < lo:
                continue  # 这一包从更后面才开始
            covered = (hi is None) or (ep_no <= hi)
            total = span.get('total')

            # ── tier：季归属的确定性 ──────────────────────────────
            if season_no == 0:
                if special or (seasons and 0 in seasons):
                    tier = 4                  # 明确是特别篇
                elif seasons and 1 in seasons:
                    tier = 3                  # 第一季包里通常带番外
                else:
                    tier = 1
            elif seasons == {season_no}:
                tier = 4                      # 明确只属于本季
            elif t_season is not None:
                tier = 3                      # 剧名带季号（庆余年2）
            elif seasons:
                tier = 2                      # 多季合集里包含本季
            else:
                tier = 1                      # 没写季，靠年份/集数判断
            if seasons and season_no in seasons and len(seasons) > 1:
                tier = min(tier, 2)

            # ── score：同层内部比较 ──────────────────────────────
            score = 0.0
            score += self._quality_score(it.get('quality') or title) * 2.0
            if lo is not None and hi is not None and lo == hi == ep_no:
                score += 60.0                 # 精确命中单集
            if total and season_total:
                score += 30.0 if total == season_total else -15.0
            if hi is not None and hi == ep_no:
                score += 25.0                 # 刚好更新到这一集
            if not covered:
                score -= 40.0                 # 只覆盖到更早的集数
            # 年份佐证：资源标题里的年份对上本季首播年 → 更可信
            years = set(int(y) for y in YEAR_RE.findall(str(it.get('raw') or title)))
            if years and season_year:
                if season_year in years:
                    score += 30.0
                    tier = min(tier + 1, 4) if tier < 3 else tier
                else:
                    score -= 45.0
                    tier = max(tier - 1, 1)
            if it.get('disk') in ('magnet', 'ed2k'):
                score += 12.0                 # 磁力/电驴原生壳也能播
            if tag is not None and tmdb_id is not None and tag == tmdb_id:
                score += 40.0
            score += self._relevance(title, show_name) * 0.2

            key = (tier, score)
            if best_key is None or key > best_key:
                best_key = key
                best = it
        return best

    # ------------------------------------------------------------------ 详情
    def _clean_title(self, raw):
        v = raw.get('name') or raw.get('title') or ''
        if _has_cjk(v):
            return v
        alts = (raw.get('alternative_titles') or {})
        for t in (alts.get('results') or alts.get('titles') or []):
            if t.get('iso_3166_1') == 'CN' and t.get('title'):
                return t['title']
        return v

    def _norm_disk(self, t):
        v = str(t or '').strip().lower()
        alias = {'quark': 'quark', 'uc': 'uc', 'ali': 'aliyun', 'aliyundrive': 'aliyun', 'xunlei': 'xunlei',
                 'cloud.189': 'tianyi', 'magnet': 'magnet', 'ed2k': 'ed2k', 'thunder': 'xunlei'}
        v = alias.get(v, v)
        return v if v in DISK_NAME else v

    def _norm_url(self, url):
        try:
            p = urlparse(url)
            return urlunparse((p.scheme, p.netloc.lower(), p.path, '', p.query, ''))
        except Exception:
            return str(url or '').strip()

    def _display_title(self, link, keyword):
        best = ''
        for k in ('note', 'title', 'name', 'work_title'):
            c = _clean_name(link.get(k))
            if len(c) > len(best):
                best = c
        return best or str(keyword or '盘搜资源')

    def _relevance(self, title, kw):
        kw = str(kw or '').strip()
        if not kw:
            return 50
        core = re.sub(r'^资源名称\s*[:：]\s*', '', str(title or '').strip())
        core = re.sub(r'^[\s🎬📺🔥✨⭐]+', '', core)
        m = re.match(r'^《([^》]{1,40})》', core)
        if m:
            core = m.group(1).strip()
        core = re.sub(r'^[【\[《]+', '', core).strip()
        if core == kw:
            return 100
        if core.startswith(kw):
            nxt = core[len(kw):len(kw) + 1]
            if not nxt or nxt in ' \t([【（·、:：-—/' or nxt.isdigit() or nxt in '第季集':
                return 95
            return 55
        if kw in str(title or ''):
            return 40
        return 5

    def _quality_score(self, text):
        t = str(text or '')
        w = {'DolbyVision': 16, 'HDR': 8, '4K': 4, '60FPS': 2, '高码': 1, '1080P': 0.5, 'SDR': 0.25}
        score = 0
        if re.search(r'dolby\s*vision|杜比', t, re.I) or re.search(r'\bDV\b', t):
            score += w['DolbyVision']
        if re.search(r'HDR', t, re.I):
            score += w['HDR']
        if re.search(r'4K|2160p', t, re.I):
            score += w['4K']
        if re.search(r'1080p', t, re.I):
            score += w['1080P']
        if '高码' in t:
            score += w['高码']
        if re.search(r'60\s*fps|60帧', t, re.I):
            score += w['60FPS']
        if re.search(r'\bSDR\b', t, re.I):
            score += w['SDR']
        return score

    def _norm_pan_results(self, merged, keyword):
        out = []
        seen = set()
        if not isinstance(merged, dict):
            return out
        for ty, links in merged.items():
            if not isinstance(links, list):
                continue
            dt = self._norm_disk(ty)
            for lk in links:
                if not isinstance(lk, dict):
                    continue
                url = str(lk.get('url') or lk.get('link') or lk.get('href') or '').strip()
                if not url:
                    continue
                key = dt + '|' + self._norm_url(url)
                if key in seen:
                    continue
                seen.add(key)
                note = str(lk.get('note') or '')
                title = self._display_title(lk, keyword)
                raw = ' '.join([note, str(lk.get('title') or ''), str(lk.get('name') or '')])
                if NOVEL_RE.search(raw) or NOVEL_RE.search(title):
                    continue  # 有声书/小说不是剧集
                out.append({
                    'key': key,
                    'disk': dt,
                    'url': url,
                    'pwd': str(lk.get('password') or lk.get('pass') or '').strip(),
                    'title': title,
                    'note': note,
                    'raw': raw,
                    'tmdb_tag': self._tmdb_tag(raw),
                    'span': self._parse_span(raw),
                    'quality': raw,
                })
        return out

    def _pan_search_base(self, keyword):
        payload = {
            'kw': keyword,
            'res': 'merge',
            'src': 'all',
        }
        for base in DEFAULT_CONFIG['pan_bases']:
            try:
                data = self._post_json(base.rstrip('/') + '/api/search', payload, timeout=18)
                merged = ((data.get('data') or {}).get('merged_by_type') or {}) if isinstance(data, dict) else {}
                got = self._norm_pan_results(merged, keyword)
                if got:
                    return got
            except Exception as e:
                print('pan base fail:', base, e)
        return []

    def _pan_search_mipan(self, keyword):
        try:
            base = DEFAULT_CONFIG['mipan_api']
            h = {'Accept': 'application/json', 'Referer': base + '/', 'User-Agent': DEFAULT_CONFIG['ua']}
            r = self.s.get(base + '/api/token', headers=h, timeout=12)
            token = (r.json() or {}).get('token')
            if not token:
                return []
            h2 = dict(h)
            h2['Content-Type'] = 'application/json'
            h2['X-Mipan-Token'] = token
            r2 = self.s.post(base + '/api/search',
                             data=json.dumps({'kw': keyword}, ensure_ascii=False).encode('utf-8'),
                             headers=h2, timeout=20)
            data = json.loads(r2.text or '{}')
            root = data.get('data') if isinstance(data.get('data'), dict) else data
            merged = (root or {}).get('merged_by_type')
            if not merged and isinstance((root or {}).get('results'), list):
                merged = {}
                for item in root['results']:
                    links = item.get('links') if isinstance(item.get('links'), list) else [item]
                    for lk in links:
                        if isinstance(lk, dict):
                            ty = self._norm_disk(lk.get('type') or item.get('type') or 'other')
                            merged.setdefault(ty, []).append(dict(item, **lk))
            return self._norm_pan_results(merged or {}, keyword)
        except Exception as e:
            print('mipan error:', e)
            return []

    def _pan_search(self, keyword, refresh=False):
        """检索网盘资源：多源合并 + 去重 + 缓存（接口本身不稳定，尽量多拿几个源）。"""
        keyword = str(keyword or '').strip()
        if not keyword:
            return []
        now = time.time()
        hit = self._pan_cache.get(keyword)
        if hit and not refresh and now - hit[0] < DEFAULT_CONFIG['cache_ttl']:
            return hit[1]
        items = []
        seen = set()
        for src in (self._pan_search_base, self._pan_search_mipan):
            try:
                got = src(keyword)
            except Exception as e:
                print('pan src fail:', e)
                got = []
            for it in got:
                if it['key'] in seen:
                    continue
                seen.add(it['key'])
                items.append(it)
            if len(items) >= 30:
                break
        items = [x for x in items if x['disk'] in DISK_NAME]
        items.sort(key=lambda x: (-(1 if self._relevance(x['title'], keyword) >= 90 else 0),
                                  -self._quality_score(x['quality'] or x['title']),
                                  -self._relevance(x['title'], keyword)))
        items = items[:DEFAULT_CONFIG['max_pan_items']]
        self._pan_cache[keyword] = (now, items)
        return items

    def _add_pwd(self, url, pwd, disk):
        url = str(url or '').strip()
        pwd = str(pwd or '').strip()
        if not url or not pwd:
            return url
        if re.match(r'^(magnet:|ed2k://)', url, re.I):
            return url
        if re.search(r'(?:[?&#])(pwd|password|passcode|code)=', url, re.I):
            return url
        param = 'password' if disk == '115' else 'pwd'
        try:
            p = urlparse(url)
            q = dict(parse_qsl(p.query, keep_blank_values=True))
            q[param] = pwd
            return urlunparse((p.scheme, p.netloc, p.path, p.params, urlencode(q), p.fragment))
        except Exception:
            sep = '&' if '?' in url else '?'
            return url + sep + param + '=' + pwd

    def _encode_id(self, url):
        """播放 ID 里不能出现裸 # / $，统一编码后加前缀。"""
        return ID_READY + quote(str(url or ''), safe='')

    def _lazy_id(self, title, season_no, ep_no):
        return ID_LAZY + quote(str(title or ''), safe='') + '~%d~%d' % (int(season_no), int(ep_no))

    def _parse_lazy_id(self, play_id):
        s = str(play_id or '').strip()
        if not s.startswith(ID_LAZY):
            return None
        parts = s[len(ID_LAZY):].split('~')
        if len(parts) != 3:
            return None
        try:
            return unquote(parts[0]), int(parts[1]), int(parts[2])
        except Exception:
            return None

    def _build_pack_lines(self, keyword):
        """按网盘类型列出整包资源（作为全集/资源线路保留）。"""
        items = self._pan_search(keyword)
        if not items:
            return [], []
        groups = {}
        for it in items:
            groups.setdefault(it['disk'], []).append(it)
        ordered = [d for d in DISK_ORDER if d in groups] + [d for d in groups if d not in DISK_ORDER]
        froms = []
        urls = []
        for disk in ordered:
            eps = []
            used = {}
            for it in groups[disk]:
                link = self._add_pwd(it['url'], it['pwd'], disk)
                name = re.sub(r'[#$]+', ' ', it['title']).strip() or keyword
                if name in used:
                    used[name] += 1
                    name = '%s %d' % (name, used[name])
                else:
                    used[name] = 1
                eps.append('%s$%s' % (name, self._encode_id(link)))
            if eps:
                froms.append(DISK_NAME.get(disk, disk))
                urls.append('#'.join(eps))
        return froms, urls

    def _tv_seasons(self, tid):
        """取回剧集每一季的分集清单（含集名、播出日期）。"""
        raw = self._tmdb_cached('/tv/%s' % tid, {'append_to_response': 'alternative_titles,credits'})
        meta = raw.get('seasons') or []
        today = time.strftime('%Y-%m-%d')
        wanted = []
        for s in meta:
            sn = s.get('season_number')
            if sn is None:
                continue
            count = int(s.get('episode_count') or 0)
            if sn == 0 and count > DEFAULT_CONFIG['max_special_eps']:
                continue  # 特别篇集数过多（如 300 集），不铺进选集
            wanted.append((int(sn), s))
        if not wanted:
            return raw, []
        nums = [sn for sn, _ in wanted]
        try:
            data = self._tmdb_cached('/tv/%s' % tid,
                                     {'append_to_response': ','.join('season/%d' % n for n in nums)},
                                     timeout=30)
        except Exception as e:
            print('season fetch fail:', e)
            return raw, []
        seasons = []
        for sn, s in wanted:
            sd = data.get('season/%d' % sn) or {}
            season_air = s.get('air_date') or ''
            season_aired = bool(season_air) and season_air <= today
            eps = []
            for e in (sd.get('episodes') or []):
                no = e.get('episode_number')
                if no is None:
                    continue
                air = e.get('air_date') or ''
                if air:
                    if air > today:
                        continue  # 未播出的集不进选集
                elif not season_aired:
                    continue  # 整季都没播，别把待播集列出来
                eps.append({'no': int(no), 'name': e.get('name') or '',
                            'air': air, 'overview': e.get('overview') or ''})
            if not eps:
                eps = self._episodes_from_count(s) if season_aired else []
            if not eps:
                continue
            eps = eps[:DEFAULT_CONFIG['max_season_eps']]
            year = 0
            for e in eps:
                if e.get('air'):
                    year = int(e['air'][:4])
                    break
            if not year and season_air:
                year = int(season_air[:4])
            seasons.append({'no': sn, 'name': s.get('name') or ('第%d季' % sn),
                            'total': int(s.get('episode_count') or len(eps)), 'year': year,
                            'episodes': eps})
        # 最新季在前，方便追更；特别篇排最后
        seasons.sort(key=lambda x: (x['no'] == 0, -x['no']))
        return raw, seasons

    def _episodes_from_count(self, s):
        """季详情缺失时按集数兜底，保证该季仍有选集。"""
        count = int(s.get('episode_count') or 0)
        if not count:
            return []
        return [{'no': i, 'name': '', 'air': s.get('air_date') or '', 'overview': ''}
                for i in range(1, count + 1)]

    def _ep_label(self, e):
        label = '第%02d集' % e['no']
        nm = _clean_name(e.get('name') or '')
        if nm and nm not in ('第%d集' % e['no'], '第%02d集' % e['no'], 'Episode %d' % e['no']):
            label = '%s %s' % (label, nm[:16])
        return re.sub(r'[#$]+', ' ', label).strip()

    def _build_tv_play(self, name, tid, seasons, items):
        """按季生成逐集选集线路。"""
        froms = []
        urls = []
        for season in seasons:
            sn = season['no']
            total = season.get('total') or len(season['episodes'])
            year = season.get('year') or 0
            eps = []
            for e in season['episodes']:
                ep_no = e['no']
                hit = self._pick_for_episode(items, name, sn, ep_no, total, tid, year)
                if hit:
                    link = self._add_pwd(hit['url'], hit['pwd'], hit['disk'])
                    eps.append('%s$%s' % (self._ep_label(e), self._encode_id(link)))
                else:
                    eps.append('%s$%s' % (self._ep_label(e), self._lazy_id(name, sn, ep_no)))
            if eps:
                froms.append('特别篇' if sn == 0 else '第%d季' % sn)
                urls.append('#'.join(eps))
        return froms, urls

    def detailContent(self, ids):
        vod = {}
        try:
            vid = ids[0] if isinstance(ids, (list, tuple)) and ids else (ids if isinstance(ids, str) else '')
            vid = str(vid or '')
            m = re.match(r'^tmdb:(tv|movie):(\d+)$', vid)
            if not m:
                return {'list': []}
            media, tid = m.group(1), int(m.group(2))
            raw = self._tmdb_cached('/%s/%s' % (media, tid), {'append_to_response': 'alternative_titles,credits'})
            name = self._clean_title(raw)
            credits = raw.get('credits') or {}
            actors = [c.get('name') for c in (credits.get('cast') or [])[:8] if c.get('name')]
            directors = [c.get('name') for c in (credits.get('crew') or []) if c.get('name') and c.get('job') == 'Director'][:3]
            area = raw.get('origin_country') or []
            date = raw.get('first_air_date') or raw.get('release_date') or ''
            rate = raw.get('vote_average') or 0
            remarks = []
            if rate:
                remarks.append('%.1f分' % rate)
            status_map = {'Returning Series': '连载中', 'Ended': '已完结',
                          'Canceled': '已取消', 'In Production': '制作中', 'Planned': '待播'}
            if media == 'tv':
                total = raw.get('number_of_episodes') or 0
                last = raw.get('last_episode_to_air') or {}
                nxt = raw.get('next_episode_to_air') or {}
                if total:
                    remarks.append('全%s集' % total)
                if nxt:
                    remarks.append('待更 S%sE%s %s' % (nxt.get('season_number') or 0, nxt.get('episode_number') or 0, nxt.get('air_date') or ''))
                elif last:
                    remarks.append('至 S%sE%s' % (last.get('season_number') or 0, last.get('episode_number') or 0))
                st = raw.get('status') or ''
                remarks.append(status_map.get(st, st))
            else:
                remarks.append('电影')
            vod = {
                'vod_id': vid,
                'vod_name': name,
                'vod_pic': _tmdb_pic(raw.get('poster_path')),
                'vod_actor': ' '.join(actors),
                'vod_director': ' '.join(directors),
                'vod_area': '/'.join([str(a) for a in area]) if isinstance(area, list) else str(area or ''),
                'vod_remarks': ' · '.join([r for r in remarks if r]),
                'vod_year': date[:4],
                'vod_content': raw.get('overview') or '',
                'vod_play_from': '',
                'vod_play_url': '',
            }
            keyword = name or raw.get('original_name') or raw.get('original_title') or ''
            froms = []
            urls = []
            items = []
            if media == 'tv':
                try:
                    _raw, seasons = self._tv_seasons(tid)
                except Exception as e:
                    print('seasons error:', e)
                    seasons = []
                items = self._pan_search(keyword)
                if not items and raw.get('original_name'):
                    items = self._pan_search(raw.get('original_name'))
                froms, urls = self._build_tv_play(name, tid, seasons, items)
            else:
                items = self._pan_search(keyword)
                if not items and raw.get('original_title'):
                    items = self._pan_search(raw.get('original_title'))
            # 整包资源作为附加线路保留，避免丢失「全集/多画质」入口
            if items:
                pack_from, pack_urls = self._build_pack_lines(keyword)
                if pack_from:
                    froms = froms + pack_from
                    urls = urls + pack_urls
            vod['vod_play_from'] = '$$$'.join(froms)
            vod['vod_play_url'] = '$$$'.join(urls)
        except Exception as e:
            print('detailContent error:', e)
        return {'list': [vod] if vod else []}

    # ------------------------------------------------------------------ 播放
    def _probe_media(self, url):
        """校验地址能否作为直链交给播放器。

        - magnet: / ed2k: → 交壳的磁力/雷鸟插件，视为可播
        - 网盘分享链接（pan.quark.cn 等）→ 交壳的网盘插件，视为可播
        - .m3u8 → 必须实测返回 #EXTM3U
        - 其它直链 → 实测 Content-Type / 魔数，确认是媒体才放行
        """
        u = str(url or '')
        if re.match(r'^(magnet:|ed2k://)', u, re.I):
            return True
        if not u.startswith(('http://', 'https://')):
            return False
        if NETDISK_HOST_RE.search(u):
            return True  # 网盘分享链接，由壳的网盘能力接管
        if not VIDEO_EXT_RE.search(u):
            # 未知后缀：实测一次，确认不是 HTML 播放页再放行
            return self._probe_direct(u)
        try:
            r = self.s.get(u, headers=dict(HEADERS), timeout=12, stream=True)
            body = b''
            for chunk in r.iter_content(4096):
                body += chunk
                if len(body) > 8192:
                    break
            text = body.decode('utf-8', 'ignore')
            if '.m3u8' in u.lower():
                return '#EXTM3U' in text
            ctype = ''
            try:
                ctype = (r.headers.get('Content-Type') or '').lower()
            except Exception:
                ctype = ''
            if b'ftyp' in body[4:12] or 'video/' in ctype or 'mpegurl' in ctype:
                return True
            return r.status_code == 200 and '#EXTM3U' in text
        except Exception as e:
            print('probe fail:', u, e)
            return False

    def _probe_direct(self, url):
        """未知后缀的直链实测：确认返回的是媒体而不是 HTML 播放页。"""
        try:
            r = self.s.get(url, headers=dict(HEADERS), timeout=12, stream=True)
            body = b''
            for chunk in r.iter_content(4096):
                body += chunk
                if len(body) > 8192:
                    break
            ctype = ''
            try:
                ctype = (r.headers.get('Content-Type') or '').lower()
            except Exception:
                ctype = ''
            text = body.decode('utf-8', 'ignore')
            if '#EXTM3U' in text:
                return True
            if b'ftyp' in body[4:12]:
                return True
            if 'video/' in ctype or 'mpegurl' in ctype or 'application/vnd.apple' in ctype:
                return True
            return False
        except Exception as e:
            print('probe direct fail:', url, e)
            return False

    def playerContent(self, flag, id, vipFlags=None):
        try:
            a = _first_arg(flag)
            b = _first_arg(id)
            # 标准调用是 (线路名, 播放ID)；部分壳把两个参数反了，按形态自适应
            if not b and a:
                play_id = a
            elif _is_url(b) or not _is_url(a):
                play_id = b
            else:
                play_id = a
            if not play_id:
                return {'parse': 1, 'jx': 0, 'playUrl': '', 'url': '', 'header': dict(HEADERS)}
            url = self._resolve_play_id(play_id)
            if not url:
                return {'parse': 1, 'jx': 0, 'playUrl': '', 'url': '', 'header': dict(HEADERS)}
            parse = 0 if self._probe_media(url) else 1
            return {'parse': parse, 'jx': 0, 'playUrl': url, 'url': url, 'header': dict(HEADERS)}
        except Exception as e:
            print('playerContent error:', e)
            return {'parse': 1, 'jx': 0, 'playUrl': '', 'url': '', 'header': dict(HEADERS)}

    def _resolve_play_id(self, play_id):
        """把播放 ID 解析成最终地址；必要时按集实时检索网盘。"""
        s = str(play_id or '').strip()
        if not s:
            return ''
        if s.startswith(ID_LAZY):
            lazy = self._parse_lazy_id(s)
            if not lazy:
                return ''
            title, season_no, ep_no = lazy
            items = self._pan_search(title, refresh=True)
            hit = self._pick_for_episode(items, title, season_no, ep_no, 0, None)
            if hit:
                return self._add_pwd(hit['url'], hit['pwd'], hit['disk'])
            return ''
        if s.startswith(ID_READY):
            return unquote(s[len(ID_READY):])
        return s

    # ------------------------------------------------------------------ 搜索
    def searchContent(self, key, quick=False, pg=1):
        vods = []
        total_pages = 1
        try:
            key = str(key or '').strip()
            try:
                pg = int(pg) if str(pg).isdigit() else 1
            except Exception:
                pg = 1
            if key:
                data = self._tmdb_cached('/search/multi', {'query': key, 'page': pg})
                total_pages = min(int(data.get('total_pages') or 1), 500)
                items = [it for it in (data.get('results') or [])
                         if it.get('media_type') in ('tv', 'movie') and it.get('poster_path')]
                items.sort(key=lambda x: -(x.get('popularity') or 0))
                for it in items[:30]:
                    vods.append(self._vod_from_tmdb_item(it, it.get('media_type')))
        except Exception as e:
            print('searchContent error:', e)
        return {'list': vods, 'page': pg, 'pagecount': total_pages, 'limit': 30, 'total': len(vods)}

    # ------------------------------------------------------------- 其它契约
    def localProxy(self, param):
        return [404, 'text/plain', b'Not Found', {}]

    def isVideoFormat(self, url):
        u = str(url or '')
        if not u:
            return False
        if re.match(r'^(magnet:|ed2k://)', u, re.I):
            return True
        return bool(VIDEO_EXT_RE.search(u))

    def manualVideoCheck(self):
        return True

    def destroy(self):
        return None
