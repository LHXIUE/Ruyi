# -*- coding: utf-8 -*-
# uil.zjss9.click — TvBox Python 源
# 基于 PyramidStore (CatVod) Spider 接口
# 站点类型：苹果CMS (MacCMS) v10 + bakai_pc 模板
# 特征：详情页JS重定向到播放页，播放页同时承载详情+播放器数据
# URL 路由：/cn/home/web/index.php/vod/{type|play|search}/...@猪猪

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
        sys.stderr.write("[ZJSS] " + str(msg) + "\n")
        sys.stderr.flush()
    except Exception:
        pass


class Spider(Spider):

    HOST = "https://uil.zjss9.click"
    PREFIX = "/cn/home/web"
    BASE = HOST + PREFIX + "/index.php/vod"

    # ── 分类（从站点实际 HTML 提取的真实 ID） ──
    CATE = {
        "亚洲情色": "20",
        "制服师生": "21",
        "卡通动漫": "22",
        "三级伦理": "23",
        "偷拍自拍": "25",
        "中文字幕": "26",
        "强奸乱伦": "24",
        "欧美性爱": "27",
        "人妻熟女": "28",
        "无码专区": "29",
    }

    UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

    # ── 预编译正则 ──

    # 列表项（bakai_pc 模板 video-card 结构）：
    # <div class="video-card-image">
    #   <a class="play-icon" href="...vod/play/id/XXX/sid/1/nid/1.html">...</a>
    #   <a href="...vod/play/id/XXX/sid/1/nid/1.html"><img src="..." alt="..." data-original="..."></a>
    #   <div class="time">分类名</div>
    # </div>
    # <div class="video-card-body">
    #   <div class="video-title"><a href="...">标题</a></div>
    #   <div class="video-view">233 次观看  2026-08-20</div>
    # </div>
    RE_VIDEO_CARD = re.compile(
        r'<div\s+class="video-card-image">\s*'
        r'<a\s+class="play-icon"\s+href="[^"]*vod/play/id/(\d+)/sid/(\d+)/nid/(\d+)\.html"[^>]*>.*?</a>\s*'
        r'<a\s+href="[^"]*vod/play/id/\1/sid/\2/nid/\3\.html"[^>]*>\s*'
        r'<img[^>]*\bsrc="([^"]*)"[^>]*\balt="([^"]*)"[^>]*>.*?</a>\s*'
        r'(?:<div\s+class="time">([^<]*)</div>)?'
        r'.*?</div>\s*'
        r'<div\s+class="video-card-body">(.*?)</div>\s*</div>\s*</div>',
        re.S | re.I
    )
    # 备用：更宽松的匹配
    RE_VIDEO_CARD_LOOSE = re.compile(
        r'<div\s+class="video-card-image">.*?'
        r'href="[^"]*vod/play/id/(\d+)/sid/(\d+)/nid/(\d+)\.html".*?'
        r'<img[^>]*\bsrc="([^"]*)"[^>]*\balt="([^"]*)"',
        re.S | re.I
    )
    RE_IMG_SRC = re.compile(r'<img[^>]*\bsrc="([^"]*)"', re.S | re.I)
    RE_IMG_DATA_ORIG = re.compile(r'data-original="([^"]*)"', re.I)
    RE_ALT_ATTR = re.compile(r'alt="([^"]*)"', re.I)
    RE_TITLE_ATTR = re.compile(r'title="([^"]*)"', re.I)
    RE_TIME_DIV = re.compile(r'<div\s+class="time">([^<]*)</div>', re.S | re.I)
    RE_VIDEO_TITLE = re.compile(r'<div\s+class="video-title">.*?<a[^>]*>(.*?)</a>', re.S | re.I)
    RE_VIDEO_VIEW = re.compile(r'<div\s+class="video-view">(.*?)</div>', re.S | re.I)
    RE_REM_TAG = re.compile(r'<[^>]+>')

    # 分页：<ul class="pagination ..."> 中提取最大页码
    RE_PAGINATION = re.compile(
        r'<ul\s+class="pagination[^"]*"[^>]*>(.*?)</ul>',
        re.S | re.I
    )
    RE_PAGE_NUM = re.compile(r'/vod/type/id/\d+/page/(\d+)\.html', re.I)

    # 播放页（详情页 JS 重定向到此）：
    # 标题：<div class="single-video-title box mb-3"><h2><a>标题</a></h2>
    RE_PLAY_TITLE = re.compile(
        r'class="single-video-title[^"]*"[^>]*>\s*<h2[^>]*>(.*?)</h2>',
        re.S | re.I
    )
    # 封面：<img class="float-left img-fluid" src="...">
    RE_PLAY_POSTER = re.compile(
        r'<img\s+class="float-left img-fluid"[^>]*\bsrc="([^"]*)"',
        re.S | re.I
    )
    # 分类：所属分类:<a ...><strong>分类名</strong></a>
    RE_PLAY_TYPE = re.compile(r'所属分类\s*[:：]\s*<a[^>]*><strong>([^<]+)</strong>', re.S)
    # 发布时间：发布于 2026-08-20 01:10:10
    RE_PLAY_DATE = re.compile(r'发布于\s*(\d{4}-\d{2}-\d{2})', re.S)
    # 简介
    RE_PLAY_BRIEF = re.compile(r'class="(?:brief|intro|content|desc)[^"]*"[^>]*>(.*?)</div>', re.S | re.I)
    # 播放列表区域：<div ... id="playlist_1"> ... </div>
    RE_PLAYLIST_DIV = re.compile(
        r'id="playlist_\d+"[^>]*>(.*?)</div>',
        re.S | re.I
    )
    # 播放线路名：<h6>（CkPlayer-H5播放器）专辑列表 :</h6>
    RE_PLAY_SOURCE = re.compile(r'<h6[^>]*>\s*[(（]([^)）]+)[)）]\s*专辑列表', re.S | re.I)
    # 集数链接
    RE_PLAY_EP = re.compile(
        r'href="[^"]*vod/play/id/(\d+)/sid/(\d+)/nid/(\d+)\.html"[^>]*>(.*?)</a>',
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

    # og 标签
    RE_OG_IMAGE = re.compile(r'<meta[^>]*og:image[^>]*content="([^"]+)"', re.I)
    RE_OG_TITLE = re.compile(r'<meta[^>]*og:title[^>]*content="([^"]+)"', re.I)

    def __init__(self):
        pass

    def getName(self):
        return "ZJSS影视"

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

        # 分页 URL：/vod/type/id/{tid}.html 或 /vod/type/id/{tid}/page/{page}.html
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
        # 详情页 JS 重定向到播放页，直接请求播放页
        # 播放页同时包含视频信息和播放器数据
        url = self.BASE + "/play/id/{0}/sid/1/nid/1.html".format(vod_id)
        html = self._fetch_html(url)
        if not html or len(html) < 200:
            raise Exception("播放页获取失败")

        # 标题
        title = self._m(self.RE_PLAY_TITLE, html)
        if not title:
            title = self._m(self.RE_OG_TITLE, html)
        title = self.RE_REM_TAG.sub('', title).strip() if title else "未知"

        # 封面图
        pic = self._m(self.RE_PLAY_POSTER, html)
        if not pic:
            pic = self._m(self.RE_OG_IMAGE, html)
        pic = self._fix_url(pic)

        # 信息字段
        type_name = self._m(self.RE_PLAY_TYPE, html).strip()
        update_date = self._m(self.RE_PLAY_DATE, html).strip()

        # 简介
        content = ""
        m = self.RE_PLAY_BRIEF.search(html)
        if m:
            content = self.RE_REM_TAG.sub('', m.group(1)).strip()
            if len(content) > 500:
                content = content[:500] + '...'

        vod = {
            "vod_id": vod_id, "vod_name": title, "vod_pic": pic,
            "type_name": type_name, "vod_year": update_date, "vod_area": "",
            "vod_remarks": "", "vod_actor": "", "vod_director": "",
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

    # ════════════ 辅助：列表解析 ════════════

    def _parse_list_html(self, html):
        """
        解析列表页 HTML（首页 + 分类页 + 搜索页通用）。
        bakai_pc 模板结构：
        <div class="video-card-image">
          <a class="play-icon" href="...vod/play/id/XXX/sid/1/nid/1.html">...</a>
          <a href="...vod/play/id/XXX/sid/1/nid/1.html"><img src="..." alt="标题" data-original="..."></a>
          <div class="time">分类名</div>
        </div>
        <div class="video-card-body">
          <div class="video-title"><a href="...">标题</a></div>
          <div class="video-view">233 次观看  2026-08-20</div>
        </div>
        """
        videos = []
        seen = set()

        # 策略1：完整 video-card 匹配
        for m in self.RE_VIDEO_CARD.finditer(html):
            vid, sid, nid, img, alt, time_text, body = m.groups()
            if vid in seen:
                continue

            name = alt.strip() if alt else ""
            if not name:
                # 从 video-title 中提取
                t = self.RE_VIDEO_TITLE.search(body)
                if t:
                    name = self.RE_REM_TAG.sub('', t.group(1)).strip()

            # 图片：src 优先（bakai_pc 模板 src 即真实图片），data-original 备选
            pic = self._fix_url(img.strip()) if img else ""
            if not pic:
                p = self.RE_IMG_DATA_ORIG.search(m.group(0))
                if p:
                    pic = self._fix_url(p.group(1).strip())

            # 备注：time div 中的分类名
            remarks = time_text.strip() if time_text else ""

            if not name:
                continue
            seen.add(vid)
            videos.append({
                "vod_id": str(vid), "vod_name": name,
                "vod_pic": pic, "vod_remarks": remarks
            })

        # 策略2：宽松匹配（只提取关键信息）
        if not videos:
            _log("策略1未匹配，尝试宽松匹配")
            for m in self.RE_VIDEO_CARD_LOOSE.finditer(html):
                vid, sid, nid, img, alt = m.groups()
                if vid in seen:
                    continue

                name = alt.strip() if alt else ""
                if not name:
                    continue

                pic = self._fix_url(img.strip()) if img else ""

                # 尝试从后续 HTML 中提取 time div
                rest = html[m.end():m.end() + 500]
                t = self.RE_TIME_DIV.search(rest)
                remarks = t.group(1).strip() if t else ""

                seen.add(vid)
                videos.append({
                    "vod_id": str(vid), "vod_name": name,
                    "vod_pic": pic, "vod_remarks": remarks
                })

        if not videos:
            _log("列表解析: 所有策略均未匹配到视频")
        return videos

    # ════════════ 辅助：分页 ════════════

    def _parse_pagecount(self, html):
        # 从 pagination UL 中提取最大页码
        m = self.RE_PAGINATION.search(html)
        if m:
            pag_html = m.group(1)
            nums = self.RE_PAGE_NUM.findall(pag_html)
            if nums:
                try:
                    return max(int(n) for n in nums if n.isdigit())
                except Exception:
                    pass
        # 回退：全页搜索
        nums = self.RE_PAGE_NUM.findall(html)
        if nums:
            try:
                return max(int(n) for n in nums if n.isdigit())
            except Exception:
                pass
        return 0

    # ════════════ 辅助：播放列表 ════════════

    def _parse_play_list(self, html, vod_id):
        """
        解析播放页中的播放列表。
        bakai_pc 结构：
        <div ... id="playlist_1">
          <h6>（CkPlayer-H5播放器）专辑列表 :</h6>
          <p class="tags">
            <span><a href="...vod/play/id/XXX/sid/1/nid/1.html">第1集</a></span>
            ...
          </p>
        </div>
        """
        # 提取线路名
        source_names = []
        for m in self.RE_PLAY_SOURCE.finditer(html):
            name = m.group(1).strip()
            if name:
                source_names.append(name)

        # 提取播放列表区域（id="playlist_X"）
        playlist_areas = self.RE_PLAYLIST_DIV.findall(html)
        if not playlist_areas:
            # 回退：搜索 "专辑列表" 后的区域
            idx = html.find("专辑列表")
            if idx > 0:
                playlist_areas = [html[idx:idx + 5000]]

        # 在播放列表区域内搜索集数链接
        all_eps = []
        for area in playlist_areas:
            eps = self.RE_PLAY_EP.findall(area)
            if eps:
                all_eps.extend(eps)

        if not all_eps:
            # 最终回退：搜索整个 HTML 但只取 vid 匹配的
            eps = self.RE_PLAY_EP.findall(html)
            for vid, sid, nid, ep_name in eps:
                if vid == vod_id:
                    all_eps.append((vid, sid, nid, ep_name))

        if not all_eps:
            _log("未找到播放链接")
            return "默认线路", "播放$" + vod_id + "___1___1"

        # 构建播放列表，去重
        seen_eps = set()
        items = []
        for vid, sid, nid, ep_name in all_eps:
            ep_name = self.RE_REM_TAG.sub('', ep_name).strip()
            if not ep_name:
                try:
                    ep_name = "第" + str(int(nid)) + "集"
                except Exception:
                    ep_name = "播放"
            ep_key = "{0}_{1}_{2}_{3}".format(vid, sid, nid, ep_name)
            if ep_key not in seen_eps:
                seen_eps.add(ep_key)
                items.append("{0}${1}___{2}___{3}".format(ep_name, vid, sid, nid))

        if not items:
            return "默认线路", "播放$" + vod_id + "___1___1"

        play_from = "$$$".join(source_names) if source_names else "默认线路"
        play_url = "#".join(items)

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
