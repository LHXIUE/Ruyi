# -*- coding: utf-8 -*-
"""
天籁精选 - 兼容 FongMi/TV (T3) 与 WebHomeTV/PeekPro (T4)
站点: https://xn--0902-2tianlailat-qy21b.tianlai96.shop
类型: 聚合短视频/影视站 (12 源聚合，已过滤空子分类)
"""
import sys
import json
import re
import time

try:
    from concurrent.futures import ThreadPoolExecutor, as_completed
except Exception:
    ThreadPoolExecutor = None
    as_completed = None

sys.path.append('..')

try:
    from base.spider import Spider
except ImportError:
    import requests as rq
    class Spider:
        def fetch(self, url, headers=None, **kw):
            kw.pop('timeout', None)
            r = rq.get(url, headers=headers, timeout=15, **kw)
            try:
                r.encoding = 'utf-8'
            except Exception:
                pass
            return r


class Spider(Spider):

    def getName(self):
        return "天籁精选"

    def init(self, extend=""):
        self.host = "https://xn--0902-2tianlailat-qy21b.tianlai96.shop"
        self.header = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Referer': self.host + '/?mod=jump',
        }
        self.sources = {
            'sh': '雄狮',
            'jp': '精品',
            'Hsck': 'Hsck',
            'xnxx': 'Xnxx',
            'javxx': 'Javxx',
            'javdb': 'JavDB',
            'javbus': 'JavBus',
            'p91': '91',
            'p91404': '9109',
            '18av': '18AV',
            'supjav': 'SupJav',
            'xvs': 'XVS',
        }
        # 子分类（已过滤无内容的空分类）
        self.sub_filters = {
            'sh': [
                {'n': '全部', 'v': ''},
                {'n': '自拍视频', 'v': 'selfie'},
                {'n': '淫妻作乐', 'v': 'wife'},
                {'n': '热门探花', 'v': 'hot-flower'},
                {'n': '国产传媒', 'v': 'domestic'},
                {'n': '开放青年', 'v': 'open-youth'},
                {'n': 'JVID专区', 'v': 'jvid'},
                {'n': 'SWAG专区', 'v': 'swag'},
                {'n': '直播录屏', 'v': 'live'},
                {'n': 'AI换脸', 'v': 'ai-face'},
                {'n': '短视频', 'v': 'short'},
                {'n': '无码破解', 'v': 'uncensored'},
                {'n': '动漫卡通', 'v': 'anime'},
                {'n': '女性向纯爱', 'v': 'pure-love'},
                {'n': 'GIGA女战士', 'v': 'giga'},
                {'n': '男男视频', 'v': 'gay'},
            ],
            'jp': [
                {'n': '全部', 'v': ''},
                {'n': '偷拍自拍', 'v': '8'},
                {'n': '国产大制作', 'v': '9'},
                {'n': '乱伦毁三观', 'v': '10'},
                {'n': '嫖妓全过程', 'v': '11'},
                {'n': '淫乱学生妹', 'v': '12'},
                {'n': '黑料不打烊', 'v': '13'},
                {'n': '主播网红', 'v': '15'},
                {'n': '高清无码', 'v': '20'},
                {'n': '中文字幕', 'v': '21'},
            ],
            'Hsck': [
                {'n': '全部', 'v': ''},
                {'n': '无码中文字幕', 'v': '8'},
                {'n': '有码中文字幕', 'v': '9'},
                {'n': '日本无码', 'v': '10'},
                {'n': '日本有码', 'v': '7'},
                {'n': '骑兵破解', 'v': '26'},
                {'n': '国产视频', 'v': '15'},
                {'n': '欧美高清', 'v': '21'},
                {'n': '动漫剧情', 'v': '22'},
            ],
            'xnxx': [
                {'n': '全部', 'v': ''},
                {'n': '最近热播', 'v': 'index'},
                {'n': '热门女星', 'v': 'pornstars_list'},
                {'n': '月度榜单', 'v': 'month_list'},
            ],
            'javxx': [
                {'n': '全部', 'v': ''},
                {'n': '最新发布', 'v': 'new'},
                {'n': '有码', 'v': 'censored'},
                {'n': '无码', 'v': 'uncensored'},
                {'n': '无码泄露', 'v': 'uncensored-leaked'},
                {'n': 'FC2', 'v': 'makers/fc2'},
                {'n': 'HEYZO', 'v': 'makers/heyzo'},
                {'n': '1pondo', 'v': 'makers/1pondo'},
                {'n': 'Caribbeancom', 'v': 'makers/caribbeancom'},
                {'n': 'Caribbeancompr', 'v': 'makers/caribbeancompr'},
                {'n': '10musume', 'v': 'makers/10musume'},
                {'n': 'Pacopacomama', 'v': 'makers/pacopacomama'},
                {'n': 'C0930', 'v': 'makers/c0930'},
                {'n': 'H0930', 'v': 'makers/h0930'},
                {'n': 'H4610', 'v': 'makers/h4610'},
                {'n': 'Tokyo Hot', 'v': 'makers/tokyo-hot'},
                {'n': 'XXX AV', 'v': 'makers/xxx-av'},
                {'n': 'GACHIG', 'v': 'makers/gachig'},
                {'n': 'SIRO', 'v': 'tags/siro'},
                {'n': 'LUXU', 'v': 'tags/259luxu'},
                {'n': '200GANA', 'v': 'tags/200gana'},
                {'n': 'PRESTIGE', 'v': 'tags/prestige-premium'},
                {'n': 'ORECO', 'v': 'tags/230oreco'},
                {'n': 'S-CUTE', 'v': 'makers/s-cute'},
                {'n': 'ARA', 'v': 'tags/261ara'},
                {'n': '390JAC', 'v': 'tags/390jac'},
                {'n': '328HMDN', 'v': 'tags/328hmdn'},
                {'n': '女优', 'v': 'actress'},
            ],
            'javdb': [
                {'n': '全部', 'v': ''},
                {'n': '有码', 'v': 'censored'},
                {'n': '无码', 'v': 'uncensored'},
                {'n': '欧美', 'v': 'western'},
                {'n': '动漫', 'v': 'anime'},
            ],
            'javbus': [
                {'n': '全部', 'v': ''},
                {'n': '无码', 'v': 'uncensored'},
                {'n': '高清', 'v': 'genre/hd'},
                {'n': '字幕', 'v': 'genre/sub'},
            ],
            'p91': [
                {'n': '全部', 'v': ''},
                {'n': '最近更新', 'v': 'latest'},
                {'n': '高清视频', 'v': 'hd'},
                {'n': '最近加精', 'v': 'recent-favorite'},
                {'n': '当前最热', 'v': 'hot-list'},
                {'n': '最近得分', 'v': 'recent-rating'},
                {'n': '非付费', 'v': 'nonpaid'},
                {'n': '91原创', 'v': 'ori'},
                {'n': '10分钟以上', 'v': 'long-list'},
                {'n': '20分钟以上', 'v': 'longer-list'},
                {'n': '本月讨论', 'v': 'month-discuss'},
                {'n': '本月收藏', 'v': 'top-favorite'},
                {'n': '收藏最多', 'v': 'most-favorite'},
                {'n': '本月最热', 'v': 'top-list'},
                {'n': '上月最热', 'v': 'top-last'},
            ],
            'p91404': [
                {'n': '全部', 'v': ''},
                {'n': '最新', 'v': 'latest'},
                {'n': '高清', 'v': 'hd'},
                {'n': '最近加精', 'v': 'recent-favorite'},
                {'n': '当前最热', 'v': 'hot-list'},
                {'n': '91原创', 'v': 'ori'},
                {'n': '非付费', 'v': 'nonpaid'},
                {'n': '10分钟以上', 'v': 'long-list'},
                {'n': '20分钟以上', 'v': 'longer-list'},
                {'n': '本月讨论', 'v': 'month-discuss'},
                {'n': '本月收藏', 'v': 'top-favorite'},
                {'n': '收藏最多', 'v': 'most-favorite'},
                {'n': '本月最热', 'v': 'top-list'},
            ],
            '18av': [
                {'n': '全部', 'v': ''},
                {'n': '中文字幕', 'v': 'chinese'},
                {'n': '有码AV', 'v': 'censored'},
                {'n': '一本道', 'v': 'maker:32/一本道(1pondo)'},
                {'n': 'Caribbeancom', 'v': 'maker:30/カリビアンコム(Caribbeancom)'},
                {'n': 'Caribbeancompr', 'v': 'maker:40/カリビアンコムPPV(Caribbeancompr)'},
                {'n': '10musume', 'v': 'maker:31/天然むすめ(10musume)'},
                {'n': 'HEYZO', 'v': 'maker:17/HEYZO'},
                {'n': '东京热', 'v': 'maker:29/東京熱(Tokyo Hot)'},
                {'n': 'Gachinco', 'v': 'maker:35/ガチん娘！(Gachinco)'},
                {'n': 'Pacopacomama', 'v': 'maker:36/パコパコママ(pacopacomama)'},
                {'n': 'H4610', 'v': 'maker:34/エッチな4610'},
                {'n': '人妻斩0930', 'v': 'maker:38/人妻斬り0930'},
                {'n': 'XXX-AV', 'v': 'maker:126/トリプルエックス (XXX-AV)'},
                {'n': '素人AV', 'v': 'amateurjav'},
                {'n': '无码破解', 'v': 'reducing-mosaic'},
                {'n': '有码动画', 'v': 'CensoredAnimation'},
                {'n': '无码动画', 'v': 'UncensoredAnimation'},
                {'n': '3D动画', 'v': 'tdAnimation'},
                {'n': '国产自拍', 'v': 'dt'},
            ],
            'supjav': [
                {'n': '全部', 'v': ''},
                {'n': '热门', 'v': 'popular'},
                {'n': '有码', 'v': 'censored-jav'},
                {'n': '无码', 'v': 'uncensored-jav'},
                {'n': '素人', 'v': 'amateur'},
                {'n': '中文字幕', 'v': 'chinese-subtitles'},
                {'n': '无码破解', 'v': 'reducing-mosaic'},
                {'n': '英文字幕', 'v': 'english-subtitles'},
            ],
            'xvs': [
                {'n': '全部', 'v': ''},
                {'n': '最近更新', 'v': 'index'},
                {'n': '热门频道', 'v': 'channels_list'},
                {'n': '明星合集', 'v': 'pornstars_list'},
                {'n': '月份榜单', 'v': 'month_list'},
            ],
        }
        self._home_cache = []
        self._home_cache_time = 0

    def _txt(self, url, referer=None, timeout=30):
        headers = dict(self.header)
        if referer:
            headers['Referer'] = referer
        try:
            rsp = self.fetch(url, headers=headers, timeout=timeout)
            try:
                rsp.encoding = 'utf-8'
            except Exception:
                pass
            return rsp.text
        except Exception:
            return ""

    def _url(self, path):
        if path.startswith('http'):
            return path
        return self.host + path if path.startswith('/') else self.host + '/' + path

    def _decode_pic(self, pic):
        if not pic:
            return pic
        return pic.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"')

    def _parse_cards(self, page_html):
        videos = []
        cards = re.findall(r'<a[^>]*class="video-card"[^>]*>.*?</a>', page_html, re.S)
        for card in cards:
            href = re.search(r'href="([^"]+)"', card)
            img = re.search(r'src="([^"]+)"', card)
            title = re.search(r'<h3[^>]*>(.*?)</h3>', card, re.S)
            time_tag = re.search(r'<span[^>]*video-time[^>]*>(.*?)</span>', card, re.S)
            if not href or not title:
                continue
            href_val = href.group(1)
            m = re.search(r'u=([^&]+)&k=([^&]+)', href_val)
            if not m:
                continue
            source = m.group(1)
            vid = m.group(2)
            vod_id = source + "_" + vid
            title_clean = re.sub(r'<[^>]+>', '', title.group(1)).strip()
            pic = img.group(1) if img else ""
            pic = self._decode_pic(pic)
            remarks = time_tag.group(1).strip() if time_tag else ""
            videos.append({
                "vod_id": vod_id,
                "vod_name": title_clean,
                "vod_pic": pic,
                "vod_remarks": remarks,
            })
        return videos

    def _extract_m3u8_from_iframe(self, iframe_src):
        m = re.match(r'/player/index.php/([^/]+)/(.+)\?em=go', iframe_src)
        if not m:
            return ""
        encoded = m.group(2)
        try:
            import urllib.parse
            return urllib.parse.unquote(encoded)
        except Exception:
            return ""

    def _get_player_data(self, source, vid):
        api_url = self.host + "/?m=play_async&u=" + source + "&k=" + vid
        try:
            rsp = self.fetch(api_url, headers=self.header, timeout=15)
            data = rsp.json()
            if not data.get('success'):
                return None, None, None
            player = data.get('player', {}) or {}
            video = data.get('video', {}) or {}
            return player.get('type'), player.get('src'), video
        except Exception:
            return None, None, None

    def homeContent(self, filter):
        classes = []
        for k, v in self.sources.items():
            classes.append({"type_id": k, "type_name": v})
        filters = {}
        for src_key, sub_list in self.sub_filters.items():
            filters[src_key] = [
                {
                    "key": "sub",
                    "name": "子分类",
                    "value": sub_list,
                }
            ]
        return {"class": classes, "filters": filters}

    def homeVideoContent(self):
        now = int(time.time())
        if self._home_cache and now - self._home_cache_time < 300:
            return {"list": self._home_cache[:72]}

        main_sources = ['sh', 'jp', 'Hsck', 'xnxx']
        urls = [self.host + "/?m=list&u=" + tid + "&k=&p=1" for tid in main_sources]
        videos = []
        seen = set()

        def load(url):
            html = self._txt(url, timeout=12)
            return self._parse_cards(html)

        if ThreadPoolExecutor and as_completed:
            pool = ThreadPoolExecutor(max_workers=4)
            futures = [pool.submit(load, u) for u in urls]
            try:
                for fu in as_completed(futures, timeout=18):
                    for v in fu.result() or []:
                        vid = v.get("vod_id")
                        if vid and vid not in seen:
                            seen.add(vid)
                            videos.append(v)
                        if len(videos) >= 72:
                            break
            finally:
                pool.shutdown(wait=False)
        else:
            for url in urls:
                for v in load(url) or []:
                    vid = v.get("vod_id")
                    if vid and vid not in seen:
                        seen.add(vid)
                        videos.append(v)
                    if len(videos) >= 72:
                        break

        self._home_cache = videos[:72]
        self._home_cache_time = now
        return {"list": self._home_cache}

    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg or 1)
        ext = {}
        if extend:
            if isinstance(extend, dict):
                ext = extend
            elif isinstance(extend, str):
                try:
                    ext = json.loads(extend)
                except Exception:
                    ext = {}
        sub_cat = ext.get('sub', '')

        url = self.host + "/?m=list&u=" + tid
        if sub_cat:
            url += "&k=" + sub_cat
        url += "&p=" + str(pg)

        html = self._txt(url, timeout=30)
        videos = self._parse_cards(html)

        total_page = 1
        page_info = re.search(r'第\s*\d+\s*/\s*(\d+)\s*页', html)
        if page_info:
            total_page = int(page_info.group(1))

        return {
            "list": videos,
            "page": pg,
            "pagecount": total_page,
            "limit": 28,
            "total": total_page * 28,
        }

    def detailContent(self, ids):
        if isinstance(ids, str):
            ids = [ids]
        vod_id = ids[0]

        m = re.match(r'([^_]+)_(.+)', vod_id)
        if not m:
            return {"list": []}
        source = m.group(1)
        vid = m.group(2)

        ptype, psrc, video = self._get_player_data(source, vid)
        if video:
            title = video.get('title', '') or video.get('code', '')
            title = re.sub(r'\s*[-|]\s*[^-|]*\s*[-|]\s*天籁精选.*$', '', title).strip()
            pic = video.get('img', '') or video.get('pic', '')
            pic = self._decode_pic(pic)
            source_name = self.sources.get(source, source)
            vod = {
                "vod_id": vod_id,
                "vod_name": title or vod_id,
                "vod_pic": pic,
                "type_name": source_name,
                "vod_remarks": video.get('duration', ''),
                "vod_content": video.get('description', ''),
                "vod_actor": ', '.join(video.get('actors', [])) if isinstance(video.get('actors'), list) else '',
                "vod_director": ', '.join(video.get('maker', [])) if isinstance(video.get('maker'), list) else '',
                "vod_play_from": source_name,
                "vod_play_url": "第1集$" + vod_id,
            }
            return {"list": [vod]}

        play_url = self.host + "/?m=play&u=" + source + "&k=" + vid
        html = self._txt(play_url, timeout=30)
        if not html:
            return {"list": []}

        title = ""
        title_match = re.search(r'<title>(.*?)</title>', html, re.S)
        if title_match:
            title = title_match.group(1).strip()
            title = re.sub(r'\s*[-|]\s*[^-|]*\s*[-|]\s*天籁精选.*$', '', title).strip()

        source_name = self.sources.get(source, source)
        vod = {
            "vod_id": vod_id,
            "vod_name": title or vod_id,
            "vod_pic": "",
            "type_name": source_name,
            "vod_remarks": "",
            "vod_content": "",
            "vod_play_from": source_name,
            "vod_play_url": "第1集$" + vod_id,
        }
        return {"list": [vod]}

    def searchContent(self, key, quick, pg="1"):
        pg = int(pg or 1)
        url = self.host + "/?m=search&k=" + key
        if pg > 1:
            url += "&p=" + str(pg)
        html = self._txt(url, timeout=30)
        videos = self._parse_cards(html)

        return {
            "list": videos,
            "page": pg,
            "pagecount": 99,
            "limit": 28,
            "total": 9999,
        }

    def playerContent(self, flag, id, vipFlags):
        if not id:
            return {"parse": 1, "playUrl": "", "url": ""}

        m = re.match(r'([^_]+)_(.+)', id)
        if not m:
            return {"parse": 1, "playUrl": "", "url": id}
        source = m.group(1)
        vid = m.group(2)

        ptype, psrc, video = self._get_player_data(source, vid)

        if psrc:
            if ptype == 'iframe':
                m3u8 = self._extract_m3u8_from_iframe(psrc)
                if m3u8 and m3u8.startswith('http'):
                    return {
                        "parse": 0,
                        "playUrl": "",
                        "url": m3u8,
                        "header": {
                            "User-Agent": self.header["User-Agent"],
                            "Referer": self.host + "/?m=play&u=" + source + "&k=" + vid,
                        },
                        "format": "application/x-mpegURL",
                        "contentType": "application/x-mpegURL",
                    }
                return {
                    "parse": 1,
                    "playUrl": "",
                    "url": self._url(psrc),
                    "header": {
                        "User-Agent": self.header["User-Agent"],
                        "Referer": self.host + "/?m=play&u=" + source + "&k=" + vid,
                    },
                }
            elif ptype in ('hls', 'video'):
                url = psrc if psrc.startswith('http') else self._url(psrc)
                is_m3u8 = '.m3u8' in url.lower()
                return {
                    "parse": 0,
                    "playUrl": "",
                    "url": url,
                    "header": {
                        "User-Agent": self.header["User-Agent"],
                        "Referer": self.host + "/?m=play&u=" + source + "&k=" + vid,
                    },
                    "format": "application/x-mpegURL" if is_m3u8 else "",
                    "contentType": "application/x-mpegURL" if is_m3u8 else "",
                }

        play_url = self.host + "/?m=play&u=" + source + "&k=" + vid
        html = self._txt(play_url, timeout=30, referer=self.host + '/?mod=jump')
        if not html:
            return {"parse": 1, "playUrl": "", "url": play_url}

        m3u8 = self._extract_m3u8_from_iframe(html)
        if m3u8 and m3u8.startswith('http'):
            return {
                "parse": 0,
                "playUrl": "",
                "url": m3u8,
                "header": {
                    "User-Agent": self.header["User-Agent"],
                    "Referer": play_url,
                },
                "format": "application/x-mpegURL",
                "contentType": "application/x-mpegURL",
            }

        return {"parse": 1, "playUrl": "", "url": play_url}

    def localProxy(self, param):
        return [200, "video/MP2T", b"", ""]

    def destroy(self):
        pass

    def close(self):
        self.destroy()
