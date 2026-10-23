# -*- coding: utf-8 -*-
# 381613.swav002.buzz — OK影视 / TvBox Python 源@猪猪
# 基于 PyramidStore (CatVod) Spider 接口
# 站点类型：苹果CMS (MacCMS) v10 + SWAV模板
# 实际 URL 路由：/swav/index.php/vod/{type|detail|play|search}/...

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
        sys.stderr.write("[SWAV] " + str(msg) + "\n")
        sys.stderr.flush()
    except Exception:
        pass


class Spider(Spider):

    HOST = "https://381613.swav002.buzz"
    PREFIX = "/swav"
    BASE = HOST + PREFIX + "/index.php/vod"

    # ── 分类（从站点实际 HTML 提取的真实 ID） ──
    CATE = {
        "精品推荐": "49",
        "高清直播": "50",
        "欧美做爱": "51",
        "国产偷拍": "54",
        "黑料网曝": "55",
        "同性恋": "56",
        "国产探花": "57",
        "国产人妻": "58",
        "调教SM": "59",
        "制服诱惑": "60",
        "麻豆工厂": "61",
        "乱伦视频": "62",
        "AI换脸": "63",
        "国产专区": "77",
        "主播做爱": "64",
        "传媒出品": "65",
        "探花约炮": "66",
        "自拍偷拍": "67",
        "欧美视频": "68",
        "动漫视频": "69",
        "女同性恋": "70",
        "男同性恋": "71",
        "网爆黑料": "73",
        "高精插B": "74",
        "调教视频": "75",
        "国产主播": "96",
        "国产视频": "95",
        "网曝黑料": "94",
        "国产传媒": "97",
        "网红头条": "99",
        "明星换脸": "100",
        "抖阴视频": "101",
        "激情动漫": "102",
        "SM调教": "103",
        "韩国主播": "104",
        "AV解说": "116",
        "VR视角": "105",
        "制服诱惑2": "115",
        "人妖系列": "106",
        "伦理三级": "114",
        "中文字幕": "107",
        "日本有码": "108",
        "强奸乱伦": "112",
        "日本无码": "109",
        "欧美无码": "110",
        "女优明星": "111",
        "萝莉少女": "113",
    }

    UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

    # ── 预编译正则 ──

    # 列表项：提取 <li> 块中的详情链接
    # 实际结构：<li><a class="thumbnail" href="/swav/index.php/vod/detail/id/123.html">...<img data-original="...">...</a><div class="video-info"><h5><a href="...">标题</a></h5><p class="vodtitle">...</p></div></li>
    RE_LIST_LI = re.compile(
        r'<li>\s*<a\s+[^>]*href="[^"]*vod/detail/id/(\d+)\.html"[^>]*>(.*?)</a>'
        r'\s*<div\s+class="video-info">(.*?)</div>\s*</li>',
        re.S | re.I
    )
    # 备用：更宽松的 <li> 块匹配
    RE_LIST_LI_LOOSE = re.compile(
        r'<li>\s*<a\s+[^>]*href="[^"]*vod/detail/id/(\d+)\.html"[^>]*>(.*?)</li>',
        re.S | re.I
    )
    # 最简匹配：只要有 detail 链接就提取
    RE_DETAIL_LINK = re.compile(
        r'href="[^"]*vod/detail/id/(\d+)\.html"[^>]*>',
        re.I
    )
    RE_IMG_DATA_ORIG = re.compile(
        r'data-original="([^"]*)"',
        re.I
    )
    RE_IMG_SRC = re.compile(
        r'<img[^>]*\bsrc="([^"]*)"',
        re.S | re.I
    )
    RE_IMG_ALT = re.compile(
        r'alt="([^"]*)"',
        re.I
    )
    RE_H5_TEXT = re.compile(
        r'<h5[^>]*>(.*?)</h5>',
        re.S | re.I
    )
    RE_VODTITLE = re.compile(
        r'<p\s+class="vodtitle"[^>]*>(.*?)</p>',
        re.S | re.I
    )
    RE_REM_TAG = re.compile(r'<[^>]+>')

    # 分页
    RE_PAGE_TOTAL = re.compile(r'data-total="(\d+)"', re.I)
    RE_PAGE_LINK = re.compile(r'vod/type/id/\d+/page/(\d+)\.html', re.I)

    # 详情页
    RE_DETAIL_BREADCRUMB = re.compile(
        r'<div\s+class="breadcrumbs"[^>]*>.*?<span>(.*?)</span>',
        re.S | re.I
    )
    RE_DETAIL_POSTER = re.compile(
        r'<div\s+class="detail-poster"[^>]*>.*?<img[^>]*\bsrc="([^"]*)"',
        re.S | re.I
    )
    RE_DETAIL_NAME = re.compile(r'片名[：:]\s*([^<]+)', re.S)
    RE_DETAIL_TYPE = re.compile(r'类型[：:]\s*([^<]+)', re.S)
    RE_DETAIL_UPDATE = re.compile(r'更新[：:]\s*(\d{4}-\d{2}-\d{2})', re.S)
    RE_OG_IMAGE = re.compile(r'<meta[^>]*og:image[^>]*content="([^"]+)"', re.I)
    RE_OG_TITLE = re.compile(r'<meta[^>]*og:title[^>]*content="([^"]+)"', re.I)

    # 播放列表
    # 实际结构：<li><a href="/swav/index.php/vod/play/id/123/sid/1/nid/1.html" title="第1集">在线播放</a></li>
    RE_PLAY_LINK = re.compile(
        r'<a[^>]*href="[^"]*vod/play/id/(\d+)/sid/(\d+)/nid/(\d+)\.html"[^>]*'
        r'(?:\stitle="([^"]*)")?[^>]*>(.*?)</a>',
        re.S | re.I
    )
    RE_PLAY_LIST_UL = re.compile(
        r'<ul\s+class="[^"]*detail-play-list[^"]*"[^>]*>(.*?)</ul>',
        re.S | re.I
    )

    # 播放器数据
    RE_PLAYER_AAAA = re.compile(r'player_aaaa\s*=\s*(\{)', re.S)

    # 媒体直链
    RE_MEDIA_M3U8 = re.compile(r'(https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)', re.I)
    RE_MEDIA_MP4 = re.compile(r'(https?://[^\s"\'<>]+\.mp4[^\s"\'<>]*)', re.I)

    # AES
    RE_AES_KEY = re.compile(r'key\s*[:=]\s*["\']([A-Za-z0-9]{16})["\']')

    def __init__(self):
        pass

    def getName(self):
        return "SW特级片"

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
            # 首页无视频列表，从"精品推荐"分类取数据
            url = self.BASE + "/type/id/49.html"
            html = self._fetch_html(url)
            if not html:
                return result
            videos = self._parse_list_html(html)
            _log("首页(精品推荐)解析到 " + str(len(videos)) + " 条")
            result = {'list': videos[:30]}
        except Exception as e:
            _log("首页异常: " + str(e))
        return result

    # ════════════ 分类列表 ════════════

    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg) if pg else 1
        result = {'list': [], 'page': page, 'pagecount': 1, 'limit': 30, 'total': 0}

        # 实际分页 URL：/swav/index.php/vod/type/id/{tid}.html 或 /swav/index.php/vod/type/id/{tid}/page/{page}.html
        if page <= 1:
            url = self.BASE + "/type/id/{0}.html".format(tid)
        else:
            url = self.BASE + "/type/id/{0}/page/{1}.html".format(tid, page)

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
        # 实际详情 URL：/swav/index.php/vod/detail/id/{vod_id}.html
        url = self.BASE + "/detail/id/{0}.html".format(vod_id)
        html = self._fetch_html(url)
        if not html or len(html) < 200:
            raise Exception("详情页获取失败")

        # 标题：优先面包屑 <span>，其次 片名字段，最后 og:title
        title = self._m(self.RE_DETAIL_BREADCRUMB, html)
        if not title:
            title = self._m(self.RE_DETAIL_NAME, html)
        if not title:
            title = self._m(self.RE_OG_TITLE, html)
        title = self.RE_REM_TAG.sub('', title).strip() if title else "未知"

        # 封面图：优先 detail-poster 中的 <img src>
        pic = self._m(self.RE_DETAIL_POSTER, html)
        if not pic:
            pic = self._m(self.RE_OG_IMAGE, html)
        pic = self._fix_url(pic)

        # 信息字段
        type_name = self._m(self.RE_DETAIL_TYPE, html).strip()
        update_date = self._m(self.RE_DETAIL_UPDATE, html)

        vod = {
            "vod_id": vod_id, "vod_name": title, "vod_pic": pic,
            "type_name": type_name, "vod_year": update_date, "vod_area": "",
            "vod_remarks": "", "vod_actor": "", "vod_director": "",
            "vod_content": "",
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
            # 实际搜索 URL：/swav/index.php/vod/search.html?wd={key} 或 /swav/index.php/vod/search/page/{page}/wd/{key}.html
            if page <= 1:
                url = self.BASE + "/search.html?wd={0}".format(encoded_key)
            else:
                url = self.BASE + "/search/page/{0}/wd/{1}.html".format(page, encoded_key)

            _log("搜索URL: " + url)
            html = self._fetch_html(url)
            if not html or len(html) < 500:
                return result
            videos = self._parse_list_html(html)
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
        # 实际播放 URL：/swav/index.php/vod/play/id/{vod_id}/sid/{sid}/nid/{nid}.html
        play_url = self.BASE + "/play/id/{0}/sid/{1}/nid/{2}.html".format(vod_id, sid, nid)

        try:
            _log("播放URL: " + play_url)
            html = self._fetch_html(play_url)
            if not html:
                return {"parse": 1, "url": play_url, "header": ""}

            # 解析 player_aaaa JSON
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

    # ════════════ 辅助：列表解析 ════════════

    def _parse_list_html(self, html):
        """
        解析列表页 HTML，提取视频信息。
        实际 HTML 结构：
        <li>
          <a class="thumbnail" href="/swav/index.php/vod/detail/id/123.html" ...>
            <img class="loadi" data-original="https://pic.jpg" src="/swav/template/swav/image/loading.svg">
          </a>
          <div class="video-info">
            <h5><a href="...detail/id/123.html">标题文字</a></h5>
            <p class="vodtitle">分类 - <span class="title">2026-08-21观看: 49</span></p>
          </div>
        </li>
        """
        videos = []
        seen = set()

        # 策略1：完整 <li> 块匹配（含 video-info）
        for m in self.RE_LIST_LI.finditer(html):
            vid = m.group(1)
            if vid in seen:
                continue

            a_inner = m.group(2)
            info_inner = m.group(3)

            # 标题：从 <h5> 中提取
            name = ""
            h5 = self.RE_H5_TEXT.search(info_inner)
            if h5:
                name = self.RE_REM_TAG.sub('', h5.group(1)).strip()

            # 图片：data-original 优先
            pic = ""
            p = self.RE_IMG_DATA_ORIG.search(a_inner)
            if p:
                pic = self._fix_url(p.group(1).strip())
            if not pic:
                p = self.RE_IMG_SRC.search(a_inner)
                if p:
                    pic_url = p.group(1).strip()
                    if 'loading.svg' not in pic_url:
                        pic = self._fix_url(pic_url)

            # 备注：从 vodtitle 中提取
            remarks = ""
            vt = self.RE_VODTITLE.search(info_inner)
            if vt:
                txt = self.RE_REM_TAG.sub('', vt.group(1)).strip()
                if txt:
                    remarks = txt[:50]

            if not name:
                continue
            seen.add(vid)
            videos.append({
                "vod_id": str(vid), "vod_name": name,
                "vod_pic": pic, "vod_remarks": remarks
            })

        # 策略2：宽松 <li> 块匹配
        if not videos:
            _log("策略1未匹配，尝试宽松匹配")
            for m in self.RE_LIST_LI_LOOSE.finditer(html):
                vid = m.group(1)
                if vid in seen:
                    continue

                full_block = m.group(0)
                inner = m.group(2) + m.group(0)  # 合并搜索范围

                # 标题：从 alt 或 title 属性提取
                name = ""
                alt = self.RE_IMG_ALT.search(full_block)
                if alt:
                    name = alt.group(1).strip()
                if not name:
                    # 从链接文本提取
                    text = self.RE_REM_TAG.sub(' ', full_block).strip()
                    # 去掉广告等无关文本
                    if text and len(text) < 200:
                        name = text[:80]

                # 图片
                pic = ""
                p = self.RE_IMG_DATA_ORIG.search(full_block)
                if p:
                    pic = self._fix_url(p.group(1).strip())
                if not pic:
                    p = self.RE_IMG_SRC.search(full_block)
                    if p:
                        pic_url = p.group(1).strip()
                        if 'loading.svg' not in pic_url and 'template' not in pic_url:
                            pic = self._fix_url(pic_url)

                # 备注
                remarks = ""
                vt = self.RE_VODTITLE.search(full_block)
                if vt:
                    txt = self.RE_REM_TAG.sub('', vt.group(1)).strip()
                    if txt:
                        remarks = txt[:50]

                if not name:
                    continue
                seen.add(vid)
                videos.append({
                    "vod_id": str(vid), "vod_name": name,
                    "vod_pic": pic, "vod_remarks": remarks
                })

        # 策略3：最简匹配 — 只要有 detail 链接就提取
        if not videos:
            _log("策略2未匹配，尝试最简匹配")
            for m in self.RE_DETAIL_LINK.finditer(html):
                vid = m.group(1)
                if vid in seen:
                    continue
                # 向前向后取一段上下文提取标题和图片
                start = max(0, m.start() - 500)
                end = min(len(html), m.end() + 1000)
                ctx = html[start:end]

                name = ""
                alt = self.RE_IMG_ALT.search(ctx)
                if alt:
                    name = alt.group(1).strip()
                if not name:
                    h5 = self.RE_H5_TEXT.search(ctx)
                    if h5:
                        name = self.RE_REM_TAG.sub('', h5.group(1)).strip()

                pic = ""
                p = self.RE_IMG_DATA_ORIG.search(ctx)
                if p:
                    pic = self._fix_url(p.group(1).strip())

                if not name:
                    continue
                seen.add(vid)
                videos.append({
                    "vod_id": str(vid), "vod_name": name,
                    "vod_pic": pic, "vod_remarks": ""
                })

        if not videos:
            _log("列表解析: 所有策略均未匹配到视频")
        return videos

    def _parse_pagecount(self, html):
        # 优先从 data-total 属性提取
        m = self.RE_PAGE_TOTAL.search(html)
        if m:
            try:
                return int(m.group(1))
            except Exception:
                pass
        # 从分页链接中提取最大页码
        pages = self.RE_PAGE_LINK.findall(html)
        if pages:
            nums = [int(p) for p in pages if p.isdigit() and int(p) > 0]
            if nums:
                return max(nums)
        return 0

    # ════════════ 辅助：详情页播放列表 ════════════

    def _parse_play_list(self, html, vod_id):
        """
        解析详情页播放列表。
        实际 HTML 结构：
        <ul class="detail-play-list clearfix ...">
          <div class="random-link">
            <li><a href="/swav/index.php/vod/play/id/123/sid/1/nid/1.html" title="第1集">在线播放</a></li>
            <li><a href="/swav/index.php/vod/play/id/123/sid/1/nid/1.html" title="第1集">备用线路一</a></li>
            ...
          </div>
        </ul>
        """
        # 优先在播放列表 UL 内搜索，避免海报区误匹配
        play_html = html
        ul_matches = self.RE_PLAY_LIST_UL.findall(html)
        if ul_matches:
            play_html = " ".join(ul_matches)

        # 提取所有播放链接
        play_matches = self.RE_PLAY_LINK.findall(play_html)
        if not play_matches:
            # 回退：搜索整个 HTML
            play_matches = self.RE_PLAY_LINK.findall(html)
        if not play_matches:
            _log("未找到播放链接")
            return "默认线路", "播放$" + vod_id + "___1___1"

        # 按 source_name 分组（每条链接的文本就是线路名）
        # 结构：(vod_id, sid, nid, title_attr, link_text)
        sources = {}  # source_name -> [(ep_key, vod_id, sid, nid, ep_name)]
        for vid, sid, nid, title_attr, link_text in play_matches:
            ep_name = title_attr.strip() if title_attr else ""
            if not ep_name:
                try:
                    ep_name = "第" + str(int(nid)) + "集"
                except Exception:
                    ep_name = "播放"

            src_name = self.RE_REM_TAG.sub('', link_text).strip()
            if not src_name:
                src_name = "默认线路"

            if src_name not in sources:
                sources[src_name] = []
            # 去重：同一线路同一集数只保留一条
            ep_key = ep_name + "_" + sid + "_" + nid
            existing_keys = [e[0] for e in sources[src_name]]
            if ep_key not in existing_keys:
                sources[src_name].append((ep_key, vid, sid, nid, ep_name))

        if not sources:
            return "默认线路", "播放$" + vod_id + "___1___1"

        play_from_list = []
        play_url_list = []

        for src_name, eps in sources.items():
            items = []
            for _, vid, sid, nid, ep_name in eps:
                items.append("{0}${1}___{2}___{3}".format(ep_name, vid, sid, nid))
            if items:
                play_from_list.append(src_name)
                play_url_list.append("#".join(items))

        if play_from_list:
            return "$$$".join(play_from_list), "$$$".join(play_url_list)

        return "默认线路", "播放$" + vod_id + "___1___1"

    # ════════════ 辅助：播放器 JSON 提取 ════════════

    def _extract_player_data(self, html):
        """提取 player_aaaa JSON 对象（平衡括号匹配）"""
        m = self.RE_PLAYER_AAAA.search(html)
        if m:
            start = m.end() - 1  # 花括号起始位置
            obj = self._extract_json(html, start)
            if obj:
                _log("Player JSON keys: " + str(list(obj.keys())))
                return obj

        # 回退：简单正则
        for name in ('player_aaaa', 'player_data', 'player_config', 'MacPlayer'):
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
