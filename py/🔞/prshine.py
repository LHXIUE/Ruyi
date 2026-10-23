#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""
怦然心动 (prshinezenx.blog) TVBox Spider -@猪猪
Compatible: FongMi/TV (T3) + WebHomeTV / PeekPro (T4)

=== 站点真实数据链路(实测) ===
1. 每个页面(首页/分类/搜索)都是: HTML 内嵌
   `const binaryStr = atob('<base64>')` -> JSON
2. JSON 结构:
   - request_data.total / request_data.list   -> 当前页视频列表
   - other_request_data.random_list           -> 首页随机推荐
   - type_list                                -> 全部分类
   - vod_info(vod_play_url)                   -> 仅详情页有
   关键: *列表项自带 m3u8 直链*:
     {"vod_id":41191,"vod_name":"...","vod_pic":"...",
      "vod_play_url":"第1集$https://aoskkzzay.com/.../index.m3u8", ...}
3. 详情页格式: /voddetail/type/{type_id}/id/{vod_id}.html
   其 vod_info.vod_play_url 是 aojiexi 解析页包装:
     https://aojiexi.com/?url=<urlencoded m3u8>


"""
import sys
import re
import json
import base64
from urllib.parse import urljoin, quote, unquote

sys.path.append('..')

try:
    from base.spider import Spider
except ImportError:
    import ssl
    import urllib.request
    import urllib.error

    class _Resp(object):
        def __init__(self, body, headers=None):
            self.content = body
            self.text = body.decode('utf-8', errors='replace')
            self.headers = headers or {}

    class Spider:
        def fetch(self, url, headers=None, timeout=30, **kw):
            req = urllib.request.Request(url, headers=headers or {})
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            try:
                rsp = urllib.request.urlopen(req, timeout=timeout, context=ctx)
                return _Resp(rsp.read(), dict(rsp.headers))
            except urllib.error.HTTPError as e:
                return _Resp(e.read(), dict(e.headers))


class Spider(Spider):

    HOST = "https://prshinezenx.blog"

    # 站点头部导航实际展示的 16 个分类 (type_show='1', 名称用站点原名)
    CLASSES = [
        {"type_id": "43", "type_name": "国产精品"},
        {"type_id": "31", "type_name": "捆绑调教"},
        {"type_id": "35", "type_name": "中文字幕"},
        {"type_id": "33", "type_name": "日本女优"},
        {"type_id": "53", "type_name": "传媒拍摄"},
        {"type_id": "29", "type_name": "人妖视频"},
        {"type_id": "21", "type_name": "男同基友"},
        {"type_id": "23", "type_name": "女同性爱"},
        {"type_id": "39", "type_name": "欧美视频"},
        {"type_id": "45", "type_name": "明星换脸"},
        {"type_id": "47", "type_name": "萝莉少女"},
        {"type_id": "49", "type_name": "网红主播"},
        {"type_id": "51", "type_name": "探花约泡"},
        {"type_id": "55", "type_name": "三级伦理"},
        {"type_id": "57", "type_name": "网暴黑料"},
        {"type_id": "63", "type_name": "素人投稿"},
    ]

    def getName(self):
        return "怦然心动"

    def getDependence(self):
        return []

    def init(self, extend=""):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36",
            "Referer": self.HOST + "/",
        }

    # ---------- 基础工具 ----------

    def _text(self, rsp):
        """统一响应提取: 兼容 str text / str content / bytes content / 文件对象"""
        if rsp is None:
            return None
        t = getattr(rsp, 'text', None)
        if isinstance(t, str):
            return t
        c = getattr(rsp, 'content', None)
        if isinstance(c, str):
            return c
        if isinstance(c, bytes):
            return c.decode('utf-8', errors='replace')
        if hasattr(rsp, 'read'):
            try:
                b = rsp.read()
                if isinstance(b, bytes):
                    return b.decode('utf-8', errors='replace')
                return b
            except Exception:
                return None
        return None

    def _fetch(self, url):
        """抓页面文本。timeout 用秒(10s), 杜绝引擎超时判死"""
        try:
            rsp = self.fetch(url, headers=self.headers, timeout=10)
            return self._text(rsp)
        except Exception:
            return None

    def _extract_data(self, html):
        """从 HTML 提取 atob base64 并解码为 dict"""
        if not html:
            return None
        m = re.search(r"const binaryStr = atob\('([^']+)'\)", html)
        if not m:
            return None
        try:
            raw = base64.b64decode(m.group(1))
            return json.loads(raw.decode('utf-8', errors='replace'))
        except Exception:
            return None

    # ---------- 列表解析(核心) ----------

    def _parse_list(self, items):
        """
        列表项自带 m3u8 直链, 必须打包进 vod_id, 详情页零网络解包返回。
        打包用 JSON+quote: 标题里的 $ | # 等特殊字符全部安全。
        """
        if not items:
            return []
        out = []
        for it in items:
            try:
                vod_id = str(it.get('vod_id') or '').strip()
                if not vod_id:
                    continue
                vod_name = it.get('vod_name') or '未知标题'
                vod_pic = it.get('vod_pic') or ''
                if vod_pic and not vod_pic.startswith('http'):
                    vod_pic = urljoin(self.HOST, vod_pic)
                vod_play_url = it.get('vod_play_url') or ''
                if vod_play_url and not str(vod_play_url).startswith('http'):
                    # 类似 "第1集$https://..." 拆出真实 url 再拼回集数
                    m = re.match(r'^(.*?)\$(https?://.+)$', str(vod_play_url))
                    if m:
                        vod_play_url = '%s$%s' % (m.group(1), m.group(2))
                packed = quote(json.dumps({
                    'id': vod_id,
                    'name': vod_name,
                    'pic': vod_pic,
                    'remark': it.get('vod_duration') or it.get('vod_remarks') or '',
                    'type': str(it.get('type_id') or ''),
                    'url': vod_play_url,     # m3u8 直链, 关键
                }, ensure_ascii=False))
                out.append({
                    'vod_id': packed,
                    'vod_name': vod_name,
                    'vod_pic': vod_pic,
                    'vod_remarks': it.get('vod_duration') or it.get('vod_remarks') or '',
                })
            except Exception:
                continue
        return out

    # ---------- 标准接口 ----------

    def homeContent(self, filter):
        return {"class": self.CLASSES, "filters": {}}

    def getHomeContent(self, filter):
        return self.homeContent(filter)

    def homeVideoContent(self):
        html = self._fetch(self.HOST + "/")
        d = self._extract_data(html)
        if not d:
            return {"list": []}
        items = (d.get('other_request_data') or {}).get('random_list') or []
        if not items:
            items = (d.get('request_data') or {}).get('list') or []
        return {"list": self._parse_list(items[:20])}

    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg or 1)
        url = "{}/vodlist/type/{}/keyword/all/orderby/default/page/{}.html".format(
            self.HOST, tid, page)
        d = self._extract_data(self._fetch(url))
        if not d:
            return {"list": [], "page": page, "pagecount": 1, "limit": 28, "total": 0}
        rd = d.get('request_data') or {}
        items = rd.get('list') or []
        total = int(rd.get('total') or 0)
        limit = int(d.get('limit') or 28) or 28
        import math
        return {
            "list": self._parse_list(items),
            "page": page,
            "pagecount": max(1, math.ceil(total / limit)),
            "limit": limit,
            "total": total,
        }

    def _build_vod(self, info):
        """由解包数据 or 详情页 vod_info 构造返回项"""
        play_url = str(info.get('url') or info.get('vod_play_url') or '').strip()
        # 统一去掉 aojiexi 包装, 拿真实 m3u8
        play_url = self._unwrap_play(play_url)
        return {
            "vod_id": str(info.get('id') or info.get('vod_id') or ''),
            "vod_name": info.get('name') or info.get('vod_name') or '未知标题',
            "vod_pic": info.get('pic') or info.get('vod_pic') or '',
            "vod_remarks": info.get('remark') or info.get('vod_duration') or '',
            "vod_content": info.get('vod_content') or '',
            "vod_play_from": "播放",
            "vod_play_url": play_url,
        }

    def _unwrap_play(self, play_url):
        """aojiexi.com 包装 -> 真实 m3u8; 普通直链原样返回"""
        if not play_url:
            return ""
        play_url = unquote(play_url)      # 先解一次 urlencode
        m = re.search(r'aojiexi\.com/\?url=(.+)', play_url)
        if m:
            play_url = unquote(m.group(1))
        return play_url

    def detailContent(self, ids):
        try:
            if not ids:
                return {"list": []}
            raw = str(ids[0])
            # 方案1: 解包列表打包的 JSON (零网络, 秒回)
            try:
                info = json.loads(unquote(raw))
                if isinstance(info, dict) and info.get('id'):
                    return {"list": [self._build_vod(info)]}
            except Exception:
                pass
            # 方案2: 纯数字 id(旧格式/外部传入) -> 请求详情页
            m = re.match(r'^(\d+)$', raw)
            if not m:
                return {"list": []}
            vid = m.group(1)
            # 2a: 详情页 type/all 格式 vod_info 为空, 但 request_data.list
            #     恰好是包含本片的推荐列表 -> 直接命中, 自带 m3u8 直链
            url = "{}/voddetail/type/all/id/{}.html".format(self.HOST, vid)
            d = self._extract_data(self._fetch(url))
            if d:
                rd = d.get('request_data') or {}
                for it in rd.get('list') or []:
                    if str(it.get('vod_id')) == vid:
                        return {"list": [self._build_vod(it)]}
                # 2b: 未命中 -> 用列表里任一真实 type_id 带参请求,
                #     只有真实 type 的详情页才有 vod_info.vod_play_url
                if rd.get('list'):
                    tid_guess = (rd['list'][0] or {}).get('type_id')
                    if tid_guess:
                        url2 = "{}/voddetail/type/{}/id/{}.html".format(
                            self.HOST, tid_guess, vid)
                        d2 = self._extract_data(self._fetch(url2))
                        if d2 and (d2.get('vod_info') or {}).get('vod_play_url'):
                            return {"list": [self._build_vod(d2['vod_info'])]}
            return {"list": []}
        except Exception:
            return {"list": []}

    def searchContent(self, key, quick, pg="1"):
        if not key:
            return {"list": []}
        page = int(pg or 1)
        url = "{}/vodlist/type/all/keyword/{}/orderby/default/page/{}.html".format(
            self.HOST, quote(str(key)), page)
        d = self._extract_data(self._fetch(url))
        if not d:
            return {"list": []}
        items = (d.get('request_data') or {}).get('list') or []
        return {
            "list": self._parse_list(items),
            "page": page,
            "pagecount": 1,
            "limit": 28,
            "total": len(items),
        }

    def playerContent(self, flag, id, vipFlags):
        if not id:
            return {"parse": 1, "playUrl": "", "url": ""}
        url = self._unwrap_play(str(id))
        if re.search(r'\.(m3u8|mp4|flv)([?#]|$)', url, re.I):
            return {"parse": 0, "playUrl": "", "url": url, "header": self.headers}
        return {"parse": 1, "playUrl": "", "url": url}

    def isVideoFormat(self, url):
        if not url:
            return False
        return bool(re.search(r'\.(m3u8|mp4|flv)([?#]|$)', url, re.I))

    def destroy(self):
        pass

    def close(self):
        self.destroy()


# ---------- 本地自检(仅 python3 prshine.py 时执行, TVBox 不触发) ----------
if __name__ == '__main__':
    def show(name, obj):
        print('[{}] {}'.format(name, obj))

    sp = Spider()
    sp.init()
    show('baseUrl', sp.HOST)

    hc = sp.homeContent('')
    show('homeContent 分类数', len(hc['class']))

    hv = sp.homeVideoContent()
    lst = hv.get('list') or []
    show('homeVideoContent 条数', len(lst))
    if lst:
        print('    first:', lst[0]['vod_name'])
        print('    vod_id 前60:', lst[0]['vod_id'][:60])

    cc = sp.categoryContent('43', 1, '', '')
    cl = cc.get('list') or []
    show('categoryContent(43) 条数', len(cl), )
    if cl:
        print('    total:', cc.get('total'), '| first:', cl[0]['vod_name'])
    else:
        print('    cc=', cc)

    if lst:
        dd = sp.detailContent([lst[0]['vod_id']])
        dl = dd.get('list') or []
        show('detailContent 解包条数', len(dl))
        if dl:
            print('    play_from:', dl[0]['vod_play_from'])
            print('    play_url :', str(dl[0]['vod_play_url'])[:100])

    sc = sp.searchContent('梦幻', '', '1')
    sl = sc.get('list') or []
    show('searchContent(梦幻) 条数', len(sl))
    if sl:
        print('    first:', sl[0]['vod_name'])

    print()
    print('== 自检完成: 全接口返回正常说明解析链路正确 ==')