# -*- coding: utf-8 -*-
# cra.bbyy8.bond — TvBox Python 源
# 基于 PyramidStore (CatVod) Spider 接口
# 站点类型：苹果CMS (MacCMS) v10 + mac_wsypc_pc 模板
# URL 路由：/cn/home/web/index.php/vod/{type|detail|play|search|show}/...@猪猪

import sys
sys.path.append('..')
from base.spider import Spider
import json
import re
from urllib.parse import quote, unquote

try:
    from Crypto.Cipher import AES
    import base64
    _HAS_CRYPTO = True
except Exception:
    _HAS_CRYPTO = False


def _log(msg):
    try:
        sys.stderr.write("[BBYY] " + str(msg) + "\n")
        sys.stderr.flush()
    except Exception:
        pass


class Spider(Spider):

    HOST = "https://cra.bbyy8.bond"
    PREFIX = "/cn/home/web"
    BASE = HOST + PREFIX + "/index.php/vod"

    # ── 分类（从站点实际 HTML 提取的真实 ID） ──
    CATE = {
        "自拍视频": "20",
        "强奸乱伦": "21",
        "无码视频": "22",
        "有码视频": "23",
        "人妻熟女": "24",
        "制服诱惑": "25",
        "口交颜射": "26",
        "SM重味": "27",
        "日韩视频": "28",
        "欧美视频": "29",
        "动漫视频": "30",
        "伦理影片": "31",
    }

    UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

    # ── 预编译正则 ──

    # 列表项（首页 + 分类页通用结构）：
    # <li><a href="...vod/play/id/XXX/sid/1/nid/1.html" ...><img data-original="..." title="..."><label>...</label></a><div class="txt"><h3>...</h3><span class="des">...</span></div></li>
    RE_LIST_LI = re.compile(
        r'<li><a\s+[^>]*href="[^"]*vod/play/id/(\d+)/sid/(\d+)/nid/(\d+)\.html"[^>]*>(.*?)</a>'
        r'\s*<div\s+class="txt">(.*?)</div>\s*</li>',
        re.S | re.I
    )
    # 首页变体：<a class="picm" ...>
    RE_LIST_LI_PICM = re.compile(
        r'<li>\s*<a\s+class="picm"\s+href="[^"]*vod/play/id/(\d+)/sid/(\d+)/nid/(\d+)\.html"[^>]*>(.*?)</a>'
        r'\s*<div\s+class="txt">(.*?)</div>\s*</li>',
        re.S | re.I
    )
    # 搜索页结构：<div class="player-info-img"><a href="..."><img src="..." title="..."></a></div><div class="player-info-x">...
    RE_SEARCH_ITEM = re.compile(
        r'<div\s+class="player-info-img">\s*<a\s+href="[^"]*vod/play/id/(\d+)/sid/(\d+)/nid/(\d+)\.html"[^>]*>(.*?)</a>\s*</div>'
        r'\s*<div\s+class="player-info-x">(.*?)</div>',
        re.S | re.I
    )

    RE_IMG_DATA_ORIG = re.compile(r'data-original="([^"]*)"', re.I)
    RE_IMG_SRC = re.compile(r'<img[^>]*\bsrc="([^"]*)"', re.S | re.I)
    RE_TITLE_ATTR = re.compile(r'title="([^"]*)"', re.I)
    RE_ALT_ATTR = re.compile(r'alt="([^"]*)"', re.I)
    RE_LABEL = re.compile(r'<label[^>]*>([^<]+)</label>', re.S | re.I)
    RE_H3_TEXT = re.compile(r'<h3[^>]*>(.*?)</h3>', re.S | re.I)
    RE_DES = re.compile(r'<span\s+class="des">([^<]+)</span>', re.S | re.I)
    RE_REM_TAG = re.compile(r'<[^>]+>')

    # 分页：<span class="page">1</span>/1631  或  <span class="count">48921</span>
    RE_PAGE_CUR = re.compile(r'<span\s+class="page">(\d+)</span>/(\d+)', re.I)
    RE_PAGE_TOTAL = re.compile(r'data-total="(\d+)"', re.I)

    # 详情页：限定在 vodinfos 区域内，排除 logo h1
    RE_DETAIL_H1 = re.compile(r'class="vodinfos"[^>]*>\s*<h1[^>]*>(.*?)</h1>', re.S | re.I)
    RE_DETAIL_POSTER = re.compile(
        r'class="vodimg"[^>]*>.*?<img[^>]*\bsrc="([^"]*)"',
        re.S | re.I
    )
    RE_DETAIL_TYPE = re.compile(r'<em>类型[：:]?</em><a[^>]*>([^<]+)</a>', re.S)
    RE_DETAIL_YEAR = re.compile(r'<em>年代[：:]?</em>(\d{4})', re.S)
    RE_DETAIL_UPDATE = re.compile(r'<em>更新时间[：:]?</em>(\d{4}-\d{2}-\d{2})', re.S)
    RE_DETAIL_ACTOR = re.compile(r'<em>主演[：:]?</em>([^<]+)', re.S)
    RE_DETAIL_DIRECTOR = re.compile(r'<em>导演[：:]?</em>([^<]+)', re.S)
    RE_DETAIL_AREA = re.compile(r'<em>国家/地区[：:]?</em>([^<]+)', re.S)
    RE_DETAIL_BRIEF = re.compile(r'class="brief"[^>]*>.*?<em>介绍[：:]?</em>(.*?)(?:</div>|<div)', re.S | re.I)
    RE_OG_IMAGE = re.compile(r'<meta[^>]*og:image[^>]*content="([^"]+)"', re.I)
    RE_OG_TITLE = re.compile(r'<meta[^>]*og:title[^>]*content="([^"]+)"', re.I)

    # 播放线路标签：<li class="on" ...><a ...>线路名</a></li>
    RE_PLAY_SOURCE = re.compile(
        r'<li[^>]*class="[^"]*on[^"]*"[^>]*>\s*<a[^>]*>(.*?)</a>',
        re.S | re.I
    )
    # 播放列表：<div class="playerlist ..."><ul ...><a class="btn" href="...">第1集</a></ul></div>
    RE_PLAY_LIST_DIV = re.compile(
        r'class="playerlist[^"]*"[^>]*>(.*?)</div>',
        re.S | re.I
    )
    RE_PLAY_EP = re.compile(
        r'<a\s+class="btn"[^>]*href="[^"]*vod/play/id/(\d+)/sid/(\d+)/nid/(\d+)\.html"[^>]*>(.*?)</a>',
        re.S | re.I
    )

    # 播放器数据：player_data = {...}
    RE_PLAYER_DATA = re.compile(r'player_data\s*=\s*(\{)', re.S)
    RE_PLAYER_AAAA = re.compile(r'player_aaaa\s*=\s*(\{)', re.S)

    # 媒体直链
    RE_MEDIA_M3U8 = re.compile(r'(https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)', re.I)
    RE_MEDIA_MP4 = re.compile(r'(https?://[^\s"\'<>]+\.mp4[^\s"\'<>]*)', re.I)

    # AES
    RE_AES_KEY = re.compile(r'key\s*[:=]\s*["\']([A-Za-z0-9]{16})["\']')

    def __init__(self):
        pass

    def getName(self):
        return "BBYY影视"

    def init(self, extend=""):
        pass

    # ════════════ 请求 ════════════

    def _headers(self):
        return {
            "User-Agent": self.UA,
            "Referer": self.HOST + self.PREFIX + "/",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }

    def _play_header(self):
        return {
            "User-Agent": self.UA,
            "Referer": self.HOST + self.PREFIX + "/",
            "Origin": self.HOST,
        }

    def _fetch_html(self, url):
        try:
            rsp = self.fetch(url, headers=self._headers(), timeout=10)
            try:
                ct = rsp.headers.get('Content-Type', '').lower()
                if 'charset' not in ct:
                    rsp.encoding = 'utf-8'
            except Exception:
                pass
            return rsp.text
        except Exception as e:
            _log("请求失败(" + url + "): " + str(e))
            return ""

    # ════════════ 首页 ════════════

    def homeContent(self, filter):
        result = {}
        classes = [{'type_name': n, 'type_id': self.CATE[n]} for n in self.CATE]
        result['class'] = classes
        if filter:
            result['filters'] = {cid: [] for cid in self.CATE.values()}
        return result

    def homeVideoContent(self):
        result = {'list': []}
        try:
            html = self._fetch_html(self.HOST + self.PREFIX + "/")
            if not html:
                return result
            videos = self._parse_list_html(html)
            _log("首页解析到 " + str(len(videos)) + " 条")
            result = {'list': videos[:30]}
        except Exception as e:
            _log("首页异常: " + str(e))
        return result

    # ════════════ 分类列表 ════════════

    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg) if pg else 1
        result = {'list': [], 'page': page, 'pagecount': 1, 'limit': 30, 'total': 0}

        # 第1页用 type，后续页用 show
        if page <= 1:
            url = self.BASE + "/type/id/{0}.html".format(tid)
        else:
            url = self.BASE + "/show/id/{0}/page/{1}.html".format(tid, page)

        _log("分类URL: " + url)
        html = self._fetch_html(url)
        if not html or len(html) < 500:
            _log("分类页HTML为空或过短")
            return result

        videos = self._parse_list_html(html)
        _log("分类 " + str(tid) + " 第 " + str(page) + " 页解析到 " + str(len(videos)) + " 条")
        result['list'] = videos

        pagecount = self._parse_pagecount(html)
        result['pagecount'] = pagecount if pagecount else 9999
        result['total'] = 999999
        return result

    # ════════════ 详情 ════════════

    def detailContent(self, array):
        try:
            return self._detail_inner(array)
        except Exception as e:
            _log("详情异常: " + str(e))
            vod_id = str(array[0]) if array else ""
            return {
                'list': [{
                    "vod_id": vod_id, "vod_name": "解析异常", "vod_pic": "",
                    "type_name": "", "vod_year": "", "vod_area": "", "vod_remarks": "",
                    "vod_actor": "", "vod_director": "", "vod_content": str(e)[:200],
                    "vod_play_from": "默认线路",
                    "vod_play_url": "播放$" + vod_id + "___1___1"
                }]
            }

    def _detail_inner(self, array):
        vod_id = str(array[0])
        url = self.BASE + "/detail/id/{0}.html".format(vod_id)
        html = self._fetch_html(url)
        if not html or len(html) < 200:
            raise Exception("详情页获取失败")

        # 标题
        title = self._m(self.RE_DETAIL_H1, html)
        if not title:
            title = self._m(self.RE_OG_TITLE, html)
        title = self.RE_REM_TAG.sub('', title).strip() if title else "未知"

        # 封面图
        pic = self._m(self.RE_DETAIL_POSTER, html)
        if not pic:
            pic = self._m(self.RE_OG_IMAGE, html)
        pic = self._fix_url(pic)

        # 信息字段
        type_name = self._m(self.RE_DETAIL_TYPE, html).strip()
        year = self._m(self.RE_DETAIL_YEAR, html).strip()
        update_date = self._m(self.RE_DETAIL_UPDATE, html).strip()
        actor = self._m(self.RE_DETAIL_ACTOR, html).strip()
        director = self._m(self.RE_DETAIL_DIRECTOR, html).strip()
        area = self._m(self.RE_DETAIL_AREA, html).strip()

        # 简介
        content = ""
        m = self.RE_DETAIL_BRIEF.search(html)
        if m:
            content = self.RE_REM_TAG.sub('', m.group(1)).strip()
            if len(content) > 500:
                content = content[:500] + '...'

        vod = {
            "vod_id": vod_id, "vod_name": title, "vod_pic": pic,
            "type_name": type_name, "vod_year": year, "vod_area": area,
            "vod_remarks": update_date, "vod_actor": actor, "vod_director": director,
            "vod_content": content,
        }
        vod["vod_play_from"], vod["vod_play_url"] = self._parse_play_list(html, vod_id)
        _log("详情完成: " + title + " | 线路: " + vod["vod_play_from"])
        return {'list': [vod]}

    # ════════════ 搜索 ════════════

    def searchContent(self, key, quick, pg="1"):
        page = int(pg) if pg else 1
        result = {'list': []}
        try:
            encoded_key = quote(key)
            # 搜索 URL：/vod/search.html?wd={key} 或 /vod/search/page/{page}/wd/{key}.html
            if page <= 1:
                url = self.BASE + "/search.html?wd={0}".format(encoded_key)
            else:
                url = self.BASE + "/search/page/{0}/wd/{1}.html".format(page, encoded_key)

            _log("搜索URL: " + url)
            html = self._fetch_html(url)
            if not html or len(html) < 500:
                return result
            videos = self._parse_search_html(html)
            _log('搜索 "' + key + '" 第 ' + str(page) + ' 页解析到 ' + str(len(videos)) + ' 条')
            result = {'list': videos}
        except Exception as e:
            _log("搜索异常: " + str(e))
        return result

    # ════════════ 播放解析 ════════════

    def playerContent(self, flag, id, vipFlags):
        parts = id.split("___")
        if len(parts) < 3:
            return {"parse": 0, "url": id, "header": ""}

        vod_id, sid, nid = parts[0], parts[1], parts[2]
        play_url = self.BASE + "/play/id/{0}/sid/{1}/nid/{2}.html".format(vod_id, sid, nid)

        try:
            _log("播放URL: " + play_url)
            html = self._fetch_html(play_url)
            if not html:
                return {"parse": 1, "url": play_url, "header": ""}

            # 解析 player_data / player_aaaa JSON
            player_json = self._extract_player_data(html)
            if player_json:
                real_url = player_json.get('url', '')
                if real_url:
                    encrypt = player_json.get('encrypt', 0)
                    if encrypt == 1:
                        real_url = unquote(real_url)
                    elif encrypt == 2 and _HAS_CRYPTO:
                        real_url = self._aes_decrypt(real_url, html)
                    elif encrypt == 2 and not _HAS_CRYPTO:
                        try:
                            real_url = unquote(real_url)
                        except Exception:
                            pass

                    _log("播放器解析成功, encrypt=" + str(encrypt) + ", url=" + real_url[:80])
                    return {
                        "parse": 0, "playUrl": "", "url": real_url,
                        "header": json.dumps(self._play_header())
                    }

            # 直接搜索媒体直链
            media_url = self._extract_media_url(html)
            if media_url:
                _log("媒体直链: " + media_url[:80])
                return {
                    "parse": 0, "url": media_url,
                    "header": json.dumps(self._play_header())
                }

            _log("未找到播放链接，fallback到网页解析")
        except Exception as e:
            _log("播放异常: " + str(e))

        return {"parse": 1, "url": play_url, "header": ""}

    # ════════════ 辅助：列表解析（首页 + 分类页） ════════════

    def _parse_list_html(self, html):
        """
        解析列表页 HTML。
        结构：<li><a href="...vod/play/id/XXX/sid/1/nid/1.html"><img data-original="..." title="..."><label>...</label></a><div class="txt"><h3>...</h3><span class="des">...</span></div></li>
        """
        videos = []
        seen = set()

        def _extract_item(vid, sid, nid, a_inner, txt_inner):
            if vid in seen:
                return None
            # 标题：优先 title 属性，其次 h3 文本，最后 alt
            name = ""
            t = self.RE_TITLE_ATTR.search(a_inner)
            if t:
                name = t.group(1).strip()
            if not name:
                t = self.RE_H3_TEXT.search(txt_inner)
                if t:
                    name = self.RE_REM_TAG.sub('', t.group(1)).strip()
            if not name:
                t = self.RE_ALT_ATTR.search(a_inner)
                if t:
                    name = t.group(1).strip()
            if not name:
                return None

            # 图片：data-original 优先，src 次选（排除占位图）
            pic = ""
            p = self.RE_IMG_DATA_ORIG.search(a_inner)
            if p:
                pic = self._fix_url(p.group(1).strip())
            if not pic:
                p = self.RE_IMG_SRC.search(a_inner)
                if p:
                    pic_url = p.group(1).strip()
                    if 'pic.png' not in pic_url and 'loading' not in pic_url and 'template' not in pic_url:
                        pic = self._fix_url(pic_url)

            # 备注：label 优先（日期），des 次选（播放次数）
            remarks = ""
            l = self.RE_LABEL.search(a_inner)
            if l:
                remarks = l.group(1).strip()
            if not remarks:
                d = self.RE_DES.search(txt_inner)
                if d:
                    remarks = d.group(1).strip()

            seen.add(vid)
            return {
                "vod_id": str(vid), "vod_name": name,
                "vod_pic": pic, "vod_remarks": remarks
            }

        # 策略1：picm 变体（首页）
        for m in self.RE_LIST_LI_PICM.finditer(html):
            v = _extract_item(m.group(1), m.group(2), m.group(3), m.group(4), m.group(5))
            if v:
                videos.append(v)

        # 策略2：标准 <li> 块（分类页）
        if not videos:
            for m in self.RE_LIST_LI.finditer(html):
                v = _extract_item(m.group(1), m.group(2), m.group(3), m.group(4), m.group(5))
                if v:
                    videos.append(v)

        # 策略3：最宽松匹配 — 只要有 play 链接就提取
        if not videos:
            _log("标准策略未匹配，尝试宽松匹配")
            loose = re.compile(
                r'<li[^>]*>.*?href="[^"]*vod/play/id/(\d+)/sid/(\d+)/nid/(\d+)\.html"[^>]*>(.*?)</li>',
                re.S | re.I
            )
            for m in loose.finditer(html):
                vid = m.group(1)
                if vid in seen:
                    continue
                full = m.group(0)
                name = ""
                t = self.RE_TITLE_ATTR.search(full)
                if t:
                    name = t.group(1).strip()
                if not name:
                    t = self.RE_H3_TEXT.search(full)
                    if t:
                        name = self.RE_REM_TAG.sub('', t.group(1)).strip()
                if not name:
                    continue
                pic = ""
                p = self.RE_IMG_DATA_ORIG.search(full)
                if p:
                    pic = self._fix_url(p.group(1).strip())
                remarks = ""
                l = self.RE_LABEL.search(full)
                if l:
                    remarks = l.group(1).strip()
                seen.add(vid)
                videos.append({
                    "vod_id": str(vid), "vod_name": name,
                    "vod_pic": pic, "vod_remarks": remarks
                })

        if not videos:
            _log("列表解析: 所有策略均未匹配到视频")
        return videos

    # ════════════ 辅助：搜索结果解析 ════════════

    def _parse_search_html(self, html):
        """
        搜索页结构：
        <div class="player-info-img"><a href="...vod/play/id/XXX/..."><img src="..." title="..."></a></div>
        <div class="player-info-x"><div class="player-info-l"><h3>标题</h3>...</div></div>
        """
        videos = []
        seen = set()

        for m in self.RE_SEARCH_ITEM.finditer(html):
            vid = m.group(1)
            if vid in seen:
                continue
            a_inner = m.group(4)
            info_inner = m.group(5)

            # 标题：优先 title 属性，其次 h3
            name = ""
            t = self.RE_TITLE_ATTR.search(a_inner)
            if t:
                name = t.group(1).strip()
            if not name:
                t = self.RE_H3_TEXT.search(info_inner)
                if t:
                    name = self.RE_REM_TAG.sub('', t.group(1)).strip()
            if not name:
                t = self.RE_ALT_ATTR.search(a_inner)
                if t:
                    name = t.group(1).strip()
            if not name:
                continue

            # 图片：src 直接取（搜索页不用懒加载）
            pic = ""
            p = self.RE_IMG_SRC.search(a_inner)
            if p:
                pic_url = p.group(1).strip()
                if 'pic.png' not in pic_url and 'loading' not in pic_url:
                    pic = self._fix_url(pic_url)
            if not pic:
                p = self.RE_IMG_DATA_ORIG.search(a_inner)
                if p:
                    pic = self._fix_url(p.group(1).strip())

            seen.add(vid)
            videos.append({
                "vod_id": str(vid), "vod_name": name,
                "vod_pic": pic, "vod_remarks": ""
            })

        # 回退：用通用列表解析
        if not videos:
            videos = self._parse_list_html(html)

        return videos

    # ════════════ 辅助：分页 ════════════

    def _parse_pagecount(self, html):
        # 优先：<span class="page">1</span>/1631
        m = self.RE_PAGE_CUR.search(html)
        if m:
            try:
                return int(m.group(2))
            except Exception:
                pass
        # 次选：data-total
        m = self.RE_PAGE_TOTAL.search(html)
        if m:
            try:
                return int(m.group(1))
            except Exception:
                pass
        return 0

    # ════════════ 辅助：详情页播放列表 ════════════

    def _parse_play_list(self, html, vod_id):
        """
        解析详情页播放列表。
        结构：
        <div class="play-nav"><ul class="playname"><li class="on"><a>线路名</a></li></ul></div>
        <div class="playerlist back-tab"><ul><a class="btn" href="...">第1集</a></ul></div>
        """
        # 提取线路名
        sources = self.RE_PLAY_SOURCE.findall(html)
        source_names = []
        for s in sources:
            name = self.RE_REM_TAG.sub('', s).strip()
            if name:
                source_names.append(name)

        # 提取播放列表区域
        play_div = self._m(self.RE_PLAY_LIST_DIV, html)
        if not play_div:
            play_div = html

        # 提取集数链接
        ep_matches = self.RE_PLAY_EP.findall(play_div)
        if not ep_matches:
            ep_matches = self.RE_PLAY_EP.findall(html)

        if not ep_matches:
            _log("未找到播放链接")
            return "默认线路", "播放$" + vod_id + "___1___1"

        # 构建播放列表
        # 该站点通常单线路单集，但支持多集
        items = []
        for vid, sid, nid, ep_name in ep_matches:
            ep_name = ep_name.strip()
            if not ep_name:
                try:
                    ep_name = "第" + str(int(nid)) + "集"
                except Exception:
                    ep_name = "播放"
            items.append("{0}${1}___{2}___{3}".format(ep_name, vid, sid, nid))

        # 去重
        seen_items = set()
        unique_items = []
        for item in items:
            if item not in seen_items:
                seen_items.add(item)
                unique_items.append(item)

        if source_names:
            play_from = "$$$".join(source_names)
            # 如果线路数 > 1 但集数只有一组，复制集数给每条线路
            if len(source_names) > 1 and len(unique_items) <= len(ep_matches):
                play_url = "$$$".join(["#".join(unique_items)] * len(source_names))
            else:
                play_url = "#".join(unique_items)
        else:
            play_from = "默认线路"
            play_url = "#".join(unique_items)

        return play_from, play_url

    # ════════════ 辅助：播放器 JSON 提取 ════════════

    def _extract_player_data(self, html):
        """提取 player_data / player_aaaa JSON 对象（平衡括号匹配）"""
        for pattern in (self.RE_PLAYER_DATA, self.RE_PLAYER_AAAA):
            m = pattern.search(html)
            if m:
                start = m.end() - 1
                obj = self._extract_json(html, start)
                if obj:
                    _log("Player JSON keys: " + str(list(obj.keys())))
                    return obj

        # 回退：简单正则
        for name in ('player_data', 'player_aaaa', 'player_config', 'MacPlayer'):
            pat = re.compile(name + r'\s*=\s*(\{[^}]+\})', re.S)
            m = pat.search(html)
            if m:
                try:
                    return json.loads(m.group(1))
                except Exception:
                    pass
        return {}

    def _extract_json(self, text, start):
        """从 start 位置（花括号）开始提取平衡的 JSON 对象"""
        if start >= len(text) or text[start] != '{':
            return None
        depth = 0
        in_string = False
        escape = False
        for i in range(start, len(text)):
            c = text[i]
            if escape:
                escape = False
                continue
            if c == '\\':
                escape = True
                continue
            if c == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except Exception:
                        return None
        return None

    def _extract_media_url(self, html):
        m = self.RE_MEDIA_M3U8.search(html)
        if not m:
            m = self.RE_MEDIA_MP4.search(html)
        return m.group(1) if m else ""

    def _aes_decrypt(self, encrypted, html):
        try:
            key_match = self.RE_AES_KEY.search(html)
            key = key_match.group(1) if key_match else "28fd7d0f7dac4156"
            cipher = AES.new(key.encode(), AES.MODE_ECB)
            decrypted = cipher.decrypt(base64.b64decode(encrypted))
            pad = decrypted[-1]
            return decrypted[:-pad].decode('utf-8', errors='ignore')
        except Exception:
            return encrypted

    # ════════════ 通用 ════════════

    def _fix_url(self, url):
        if not url:
            return ""
        url = url.strip()
        if url.startswith('//'):
            return 'https:' + url
        if url.startswith('/'):
            return self.HOST + url
        return url

    def _m(self, regex, text):
        m = regex.search(text)
        return m.group(1) if m else ""

    def isVideoFormat(self, url):
        pass

    def manualVideoCheck(self):
        pass

    def localProxy(self, param):
        return [200, "video/MP2T", "", ""]
