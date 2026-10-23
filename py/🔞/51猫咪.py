# -*- coding: utf-8 -*-
"""
51猫咪 (7oqo67h.51mm.buzz) Python Spider
兼容 FongMi/TV (T3) 与 WebHomeTV / PeekPro (T4)
"""
import sys
import re
import base64
import json
import time
from urllib.parse import quote

sys.path.append('..')

try:
    from base.spider import Spider
except ImportError:
    import requests as rq
    class Spider:
        _session = rq.Session()
        def fetch(self, url, headers=None, **kw):
            kw.pop('timeout', None)
            r = self._session.get(url, headers=headers, timeout=15, **kw)
            r.encoding = 'utf-8'
            return r


class Spider(Spider):
    HOST = 'https://7oqo67h.51mm.buzz'

    def getName(self):
        return "51猫咪"

    def init(self, extend=''):
        if isinstance(extend, list):
            self.extend = ''
        else:
            self.extend = extend or ''
        self.host = self.HOST
        self.header = {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 '
                          '(KHTML, like Gecko) Chrome/120.0 Mobile Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Referer': self.host + '/',
        }
        self._home_cache = []
        self._home_cache_time = 0
        self._classes = None
        self._filters = None
        # 封面图缓存：vid -> pic_url，用于修复列表页空封面
        self._pic_cache = {}
        # m3u8 缓存：vid -> m3u8_url，避免播放时重复请求详情页
        self._m3u8_cache = {}

    def _url(self, path):
        if not path:
            return self.host
        if path.startswith('http'):
            return path
        return self.host + path if path.startswith('/') else self.host + '/' + path

    def _fetch_html(self, url, timeout=10):
        """获取页面并解码 base64Content（空响应/523自动重试一次）"""
        for attempt in range(2):
            try:
                rsp = self.fetch(url, headers=self.header, timeout=timeout)
                try:
                    rsp.encoding = 'utf-8'
                except Exception:
                    pass
                text = rsp.text
                m = re.search(r"""const\s+base64Content\s*=\s*['"/]([^'"]+)['"]""", text)
                if m:
                    try:
                        return base64.b64decode(m.group(1)).decode('utf-8', errors='ignore')
                    except Exception:
                        pass
                if len(text) > 500:
                    return text
                # 空响应或 523 错误页（通常仅几十字节），重试一次
                if attempt == 0:
                    time.sleep(0.5)
                    continue
                return ''
            except Exception:
                if attempt == 0:
                    time.sleep(0.5)
                    continue
                return ''
        return ''

    def _extract_value(self, raw):
        """兼容 TVBox 传入的 extend 值"""
        if raw is None:
            return ''
        if isinstance(raw, dict):
            return str(raw.get('v', ''))
        if isinstance(raw, str):
            return raw
        return str(raw)

    def _parse_extend(self, extend):
        """解析 extend 参数"""
        ext = {}
        if not extend:
            return ext
        if isinstance(extend, dict):
            ext = extend
        elif isinstance(extend, str):
            extend = extend.strip()
            if not extend or extend.lower() in ('null', 'undefined', 'none', ''):
                return ext
            try:
                parsed = json.loads(extend)
                if isinstance(parsed, dict):
                    ext = parsed
            except Exception:
                pass
        return ext

    def _parse_videos(self, html):
        """解析视频卡片列表（增强版，修复空封面问题）"""
        videos = []
        seen = set()
        if not html:
            return videos

        # 策略1：基于实际HTML结构解析卡片
        # 匹配 <a href="player.php?id=数字">...</a> 包裹的完整卡片
        for m in re.finditer(
            r"""<a\b[^>]*\bhref\s*=\s*['"/]player\.php\?id\s*=\s*(\d+)['"][^>]*>(.*?)</a>""",
            html, re.S
        ):
            vid = m.group(1)
            if vid in seen:
                continue
            seen.add(vid)
            block = m.group(2)

            # 提取图片 src（支持各种引号，允许空值）
            pic = ''
            # 先尝试标准 src
            img_m = re.search(r"""<img\b[^>]*\bsrc\s*=\s*['"/]([^'"]*)['"]""", block, re.I)
            if img_m:
                pic = img_m.group(1).strip()

            # 如果 src 为空，尝试 data-src / data-original
            if not pic:
                img_m = re.search(r"""<img\b[^>]*\bdata-(?:src|original)\s*=\s*['"/]([^'"]+)['"]""", block, re.I)
                if img_m:
                    pic = img_m.group(1).strip()

            # 如果还是没图片，尝试从缓存或详情页补全
            if not pic and vid in self._pic_cache:
                pic = self._pic_cache[vid]

            if pic and not pic.startswith('http'):
                pic = self._url(pic)

            # 提取标题（优先 alt，其次 card-title）
            title = ''
            alt_m = re.search(r"""\balt\s*=\s*['"/]([^'"]+)['"]""", block, re.I)
            if alt_m:
                title = alt_m.group(1).strip()
            if not title:
                t_m = re.search(r"""class\s*=\s*['"/]card-title['"][^>]*>(.*?)</div>""", block, re.S)
                if t_m:
                    title = re.sub(r'<[^>]+>', '', t_m.group(1)).strip()

            # 提取备注
            remarks = ''
            meta_m = re.search(r"""class\s*=\s*['"/]meta['"][^>]*>(.*?)</div>""", block, re.S)
            if meta_m:
                remarks = re.sub(r'<[^>]+>', '', meta_m.group(1)).strip()
                remarks = remarks.replace('\n', ' ').replace('  ', ' ')[:30]

            videos.append({
                'vod_id': vid,
                'vod_name': title or vid,
                'vod_pic': pic,
                'vod_remarks': remarks,
            })

        return videos

    def _parse_detail(self, html, vid):
        """解析详情页（增强版，缓存封面图）"""
        title = ''
        title_match = re.search(r'<title>([^<]+)</title>', html)
        if title_match:
            title = title_match.group(1).split(' - ')[0].strip()

        pic = ''
        # 优先查找高清大图
        pic_match = re.search(r'<img[^>]*src="(https?://[^"]+)"', html)
        if not pic_match:
            pic_match = re.search(r'<img[^>]*data-src="(https?://[^"]+)"', html)
        if not pic_match:
            pic_match = re.search(r'<img[^>]*src="([^"]+)"', html)
        if pic_match:
            pic = pic_match.group(1)
            if pic and not pic.startswith('http'):
                pic = self._url(pic)
            # 缓存封面图，供列表页使用
            if pic:
                self._pic_cache[vid] = pic

        content = ''
        desc_match = re.search(r'<div[^>]*class="[^"]*desc[^"]*"[^>]*>(.*?)</div>', html, re.S)
        if desc_match:
            content = re.sub(r'<[^>]+>', '', desc_match.group(1)).strip()

        m3u8 = ''
        # 优先匹配 sourceUrl 变量
        src_match = re.search(r'const\s+sourceUrl\s*=\s*"([^"]+\.m3u8[^"]*)"', html)
        if not src_match:
            src_match = re.search(r'"(https?://[^"]+\.m3u8[^"]*)"', html)
        if src_match:
            m3u8 = src_match.group(1).strip('"')
            # 缓存 m3u8，供 playerContent 直接使用，避免重复请求详情页
            if m3u8 and vid:
                self._m3u8_cache[vid] = m3u8

        play_url = "播放$" + m3u8 if m3u8 else ''

        return {
            'vod_id': vid,
            'vod_name': title or vid,
            'vod_pic': pic,
            'type_name': '',
            'vod_year': '',
            'vod_area': '',
            'vod_remarks': '',
            'vod_actor': '',
            'vod_director': '',
            'vod_content': content[:500] if content else '',
            'vod_play_from': '默认线路',
            'vod_play_url': play_url,
        }

    def _get_pagecount(self, html):
        """提取最大页码"""
        if not html:
            return 1
        pages = re.findall(r'[?&]page=(\d+)', html)
        if pages:
            nums = [int(p) for p in pages if p.isdigit()]
            if nums:
                return max(nums)
        return 1

    def _load_classes(self):
        if self._classes is not None:
            return self._classes

        classes = [
            {'type_id': 'guochan', 'type_name': '国产视频'},
            {'type_id': 'riben', 'type_name': '日本视频'},
            {'type_id': 'oumei', 'type_name': '欧美视频'},
            {'type_id': 'hanguo', 'type_name': '韩国视频'},
            {'type_id': 'zhifu', 'type_name': '制服角色'},
            {'type_id': 'lunli', 'type_name': '伦理专区'},
            {'type_id': 'zhibo', 'type_name': '直播视频'},
            {'type_id': 'dongman', 'type_name': '动漫视频'},
            {'type_id': 'zhongkou', 'type_name': '重口猎奇'},
            {'type_id': 'sifang', 'type_name': '私房俱乐部'},
        ]

        filters = {
            'guochan': [{
                'key': 'cat',
                'name': '子分类',
                'value': [
                    {'n': '国产AV', 'v': '71'},
                    {'n': '学生少女', 'v': '21'},
                    {'n': '技师风采', 'v': '22'},
                    {'n': '熟女少妇', 'v': '23'},
                    {'n': '国产热播', 'v': '24'},
                    {'n': '反差母狗', 'v': '25'},
                    {'n': '美脚丝足', 'v': '26'},
                    {'n': '情侣自拍', 'v': '27'},
                    {'n': '偷情约炮', 'v': '28'},
                    {'n': '真实偷拍', 'v': '29'},
                    {'n': '高潮喷水', 'v': '30'},
                    {'n': '强奸迷奸', 'v': '32'},
                    {'n': '户外露出', 'v': '33'},
                    {'n': 'SM调教', 'v': '34'},
                    {'n': '情趣内衣', 'v': '35'},
                    {'n': '黑料曝光', 'v': '37'},
                    {'n': '网曝门事件', 'v': '38'},
                    {'n': '校园猛料', 'v': '39'},
                    {'n': '网红流出', 'v': '40'},
                    {'n': '明星黑料', 'v': '41'},
                    {'n': '裸贷肉偿', 'v': '42'},
                    {'n': '婚闹恶俗', 'v': '43'},
                    {'n': '抓奸名场面', 'v': '44'},
                    {'n': '男同女同', 'v': '45'},
                ]
            }],
            'riben': [{
                'key': 'cat',
                'name': '子分类',
                'value': [
                    {'n': '日本中文', 'v': '94'},
                    {'n': '无码流出', 'v': '95'},
                    {'n': 'FC2', 'v': '96'},
                    {'n': 'HEYZO', 'v': '97'},
                    {'n': '东京热', 'v': '98'},
                    {'n': '一本道', 'v': '99'},
                    {'n': '人妻斩', 'v': '100'},
                    {'n': '网红主播', 'v': '101'},
                    {'n': '伦理精选', 'v': '102'},
                    {'n': '剧情故事', 'v': '103'},
                ]
            }],
            'oumei': [{
                'key': 'cat',
                'name': '子分类',
                'value': [
                    {'n': '欧美精选', 'v': '73'},
                    {'n': '户外搭讪', 'v': '74'},
                    {'n': '美女自慰', 'v': '75'},
                    {'n': '成人剧情', 'v': '76'},
                    {'n': '黑人大屌', 'v': '77'},
                    {'n': '群P大作战', 'v': '78'},
                    {'n': '欧美重口', 'v': '79'},
                ]
            }],
            'hanguo': [{
                'key': 'cat',
                'name': '子分类',
                'value': [
                    {'n': '主播网黄', 'v': '111'},
                    {'n': '色情综艺', 'v': '112'},
                    {'n': '乱伦精选', 'v': '114'},
                ]
            }],
            'zhifu': [{
                'key': 'cat',
                'name': '子分类',
                'value': [
                    {'n': '制服诱惑', 'v': '46'},
                    {'n': 'JK少女', 'v': '47'},
                    {'n': '黑丝白丝', 'v': '48'},
                    {'n': '女仆', 'v': '49'},
                    {'n': 'cosplay', 'v': '50'},
                    {'n': 'OL制服', 'v': '51'},
                    {'n': '旗袍', 'v': '52'},
                    {'n': '空姐制服', 'v': '53'},
                    {'n': '护士医生', 'v': '54'},
                ]
            }],
            'lunli': [{
                'key': 'cat',
                'name': '子分类',
                'value': [
                    {'n': '禁忌母子', 'v': '56'},
                    {'n': '兄弟姐妹', 'v': '57'},
                    {'n': '爱上嫂子', 'v': '59'},
                    {'n': '狂操小姨', 'v': '60'},
                    {'n': '换夫换妻', 'v': '61'},
                    {'n': '淫荡儿媳', 'v': '62'},
                    {'n': '爷爷奶奶', 'v': '63'},
                ]
            }],
            'zhibo': [{
                'key': 'cat',
                'name': '子分类',
                'value': [
                    {'n': '啪啪直播', 'v': '65'},
                    {'n': '学生直播', 'v': '66'},
                    {'n': '自慰诱惑', 'v': '67'},
                    {'n': '乱伦直播', 'v': '68'},
                    {'n': '户外勾搭', 'v': '69'},
                    {'n': '车震直播', 'v': '70'},
                ]
            }],
            'dongman': [{
                'key': 'cat',
                'name': '子分类',
                'value': [
                    {'n': '3D动漫', 'v': '91'},
                    {'n': '同人动漫', 'v': '92'},
                    {'n': '国产动漫', 'v': '104'},
                    {'n': '日韩动漫', 'v': '105'},
                    {'n': '欧美动漫', 'v': '106'},
                    {'n': '港台动漫', 'v': '107'},
                    {'n': '海外动漫', 'v': '108'},
                ]
            }],
            'zhongkou': [{
                'key': 'cat',
                'name': '子分类',
                'value': [
                    {'n': '人兽性交', 'v': '81'},
                    {'n': 'SM性虐', 'v': '82'},
                    {'n': '人妖伪娘', 'v': '83'},
                    {'n': '孕妇内射', 'v': '84'},
                    {'n': '吃屎喝尿', 'v': '85'},
                    {'n': '扩阴拳交', 'v': '86'},
                    {'n': '阳具巨物', 'v': '87'},
                ]
            }],
        }

        self._classes = classes
        self._filters = filters
        return classes

    def _get_filters(self):
        if self._filters is None:
            self._load_classes()
        return self._filters or {}

    # ========== 首页 ==========
    def homeContent(self, filter):
        return {
            'class': self._load_classes(),
            'filters': self._get_filters(),
        }

    def homeVideoContent(self):
        now = int(time.time())
        if self._home_cache and now - self._home_cache_time < 300:
            return {'list': self._home_cache[:72]}

        videos = []
        seen = set()

        try:
            html = self._fetch_html(self.host + '/', timeout=10)
            items = self._parse_videos(html)
            for v in items:
                vid = v.get('vod_id')
                if vid and vid not in seen:
                    seen.add(vid)
                    videos.append(v)
                if len(videos) >= 72:
                    break
        except Exception:
            pass

        self._home_cache = videos[:72]
        self._home_cache_time = now
        return {'list': self._home_cache}

    # ========== 分类列表 ==========
    def categoryContent(self, tid, pg, filter, extend):
        try:
            pg = int(pg or 1)
            ext = self._parse_extend(extend)
            cat = self._extract_value(ext.get('cat', ''))

            defaults = {
                'guochan': '71',
                'riben': '94',
                'oumei': '73',
                'hanguo': '111',
                'zhifu': '46',
                'lunli': '56',
                'zhibo': '65',
                'dongman': '91',
                'zhongkou': '81',
                'sifang': '1',
            }

            if cat:
                category_id = cat
            elif tid in defaults:
                category_id = defaults[tid]
            else:
                category_id = tid

            url = self.host + '/list.php?category=' + category_id + '&page=' + str(pg)
            html = self._fetch_html(url, timeout=10)

            if not html:
                return {'list': [], 'page': pg, 'pagecount': 1, 'limit': 20, 'total': 0}

            videos = self._parse_videos(html)

            pagecount = self._get_pagecount(html)
            if not pagecount and videos:
                pagecount = 1

            return {
                'list': videos,
                'page': pg,
                'pagecount': pagecount or 1,
                'limit': 20,
                'total': len(videos) * (pagecount or 1),
            }
        except Exception:
            return {'list': [], 'page': int(pg or 1), 'pagecount': 1, 'limit': 20, 'total': 0}

    # ========== 详情页 ==========
    def detailContent(self, ids):
        try:
            if isinstance(ids, str):
                ids = [ids]
            if not ids:
                return {'list': []}
            vid = ids[0]
            if not vid:
                return {'list': []}

            url = self.host + '/player.php?id=' + str(vid)
            html = self._fetch_html(url, timeout=10)

            if not html:
                return {'list': [{
                    'vod_id': vid,
                    'vod_name': str(vid),
                    'vod_pic': self._pic_cache.get(vid, ''),
                    'type_name': '',
                    'vod_year': '',
                    'vod_area': '',
                    'vod_remarks': '',
                    'vod_actor': '',
                    'vod_director': '',
                    'vod_content': '',
                    'vod_play_from': '默认线路',
                    'vod_play_url': '',
                }]}

            vod = self._parse_detail(html, vid)
            return {'list': [vod]}
        except Exception:
            vid = ids[0] if isinstance(ids, (list, tuple)) and ids else (ids if isinstance(ids, str) else '0')
            return {'list': [{
                'vod_id': vid,
                'vod_name': str(vid),
                'vod_pic': self._pic_cache.get(vid, ''),
                'type_name': '',
                'vod_year': '',
                'vod_area': '',
                'vod_remarks': '',
                'vod_actor': '',
                'vod_director': '',
                'vod_content': '',
                'vod_play_from': '默认线路',
                'vod_play_url': '',
            }]}

    # ========== 搜索 ==========
    def searchContent(self, key, quick, pg='1'):
        try:
            pg = int(pg or 1)
            url = self.host + '/list.php?search=' + quote(key, safe='') + '&page=' + str(pg)

            html = self._fetch_html(url, timeout=10)
            videos = self._parse_videos(html)

            pagecount = self._get_pagecount(html)
            if not pagecount and videos:
                pagecount = 1

            return {
                'list': videos,
                'page': pg,
                'pagecount': pagecount or 1,
                'limit': 20,
                'total': len(videos) * (pagecount or 1),
            }
        except Exception:
            return {'list': [], 'page': int(pg or 1), 'pagecount': 1, 'limit': 20, 'total': 0}

    # ========== 播放解析（增强版）==========
    def playerContent(self, flag, id, vipFlags):
        if not id:
            return {'parse': 1, 'playUrl': '', 'url': ''}

        # 如果 id 是播放链接（以 $ 分隔符分隔）
        if '$' in id:
            parts = id.split('$')
            if len(parts) == 2:
                id = parts[1]

        # 如果 id 是纯数字，说明是视频ID而非播放链接
        # 优先从缓存取 m3u8，缓存未命中则请求详情页获取
        if str(id).isdigit():
            vid = str(id)
            if vid in self._m3u8_cache:
                url = self._m3u8_cache[vid]
                return {
                    'parse': 0,
                    'playUrl': '',
                    'url': url,
                    'header': {
                        'User-Agent': self.header['User-Agent'],
                        'Referer': self.host + '/',
                    },
                    'format': 'application/x-mpegURL',
                    'contentType': 'application/x-mpegURL',
                }
            # 缓存未命中，请求详情页获取 m3u8
            try:
                durl = self.host + '/player.php?id=' + vid
                dhtml = self._fetch_html(durl, timeout=10)
                if dhtml:
                    src_match = re.search(r'const\s+sourceUrl\s*=\s*"([^"]+\.m3u8[^"]*)"', dhtml)
                    if not src_match:
                        src_match = re.search(r'"(https?://[^"]+\.m3u8[^"]*)"', dhtml)
                    if src_match:
                        url = src_match.group(1).strip('"')
                        self._m3u8_cache[vid] = url
                        return {
                            'parse': 0,
                            'playUrl': '',
                            'url': url,
                            'header': {
                                'User-Agent': self.header['User-Agent'],
                                'Referer': self.host + '/',
                            },
                            'format': 'application/x-mpegURL',
                            'contentType': 'application/x-mpegURL',
                        }
            except Exception:
                pass
            return {'parse': 1, 'playUrl': '', 'url': ''}

        url = id if str(id).startswith('http') else self._url(id)

        # 空链接检测
        if not url or url == self.host + '/':
            return {'parse': 1, 'playUrl': '', 'url': ''}

        if '.m3u8' in url:
            return {
                'parse': 0,
                'playUrl': '',
                'url': url,
                'header': {
                    'User-Agent': self.header['User-Agent'],
                    'Referer': self.host + '/',
                },
                'format': 'application/x-mpegURL',
                'contentType': 'application/x-mpegURL',
            }

        if '.mp4' in url:
            return {
                'parse': 0,
                'playUrl': '',
                'url': url,
                'header': {
                    'User-Agent': self.header['User-Agent'],
                    'Referer': self.host + '/',
                },
            }

        # 如果URL不是直接媒体链接，尝试获取真实链接
        if not any(ext in url for ext in ['.m3u8', '.mp4', '.ts', '.flv']):
            try:
                html = self._fetch_html(url, timeout=10)
                if html:
                    src_match = re.search(r'const\s+sourceUrl\s*=\s*"([^"]+\.m3u8[^"]*)"', html)
                    if src_match:
                        real_url = src_match.group(1).strip('"')
                        return {
                            'parse': 0,
                            'playUrl': '',
                            'url': real_url,
                            'header': {
                                'User-Agent': self.header['User-Agent'],
                                'Referer': self.host + '/',
                            },
                            'format': 'application/x-mpegURL',
                            'contentType': 'application/x-mpegURL',
                        }
            except:
                pass

        return {'parse': 1, 'playUrl': '', 'url': url, 'header': self.header}

    def localProxy(self, param):
        return [200, 'video/MP2T', b'', '']

    def destroy(self):
        pass

    def close(self):
        self.destroy()
