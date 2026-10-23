#coding=utf-8
#!/usr/bin/python
# TVBox py 爬虫源 - 6182104.xyz
# 分类栏 / 子分类 / 搜索 / 封面图海报 / 播放 完整可用
# 修复: 兼容两种页面结构(vodbox/span)、播放地址去除#分隔符、m3u8直连播放

import sys
sys.path.append('..')

from base.spider import Spider
import re
import json
from urllib.parse import quote, unquote, parse_qs, urlparse

class Spider(Spider):

    def getName(self):
        return "6182104"

    def init(self, extend=""):
        self.host = "https://6182104.xyz"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': self.host + '/'
        }
        # 分类列表: 名称 -> ID
        self.cateManual = {
            "全部视频": "1",
            "香蕉精品": "13",
            "制服诱惑": "22",
            "国产视频": "6",
            "清纯少女": "8",
            "辣妹大奶": "9",
            "女同专属": "10",
            "素人出演": "11",
            "角色扮演": "12",
            "人妻熟女": "20",
            "日韩剧情": "23",
            "经典伦理": "21",
            "成人动漫": "7",
            "精品二区": "14",
            "精品三区": "40"
        }
        pass

    # ===== XOR 128 解密 =====
    def decrypt(self, text):
        """对 km-script 加密文本进行 XOR 128 解密"""
        if not text:
            return ""
        result = []
        for ch in text:
            result.append(chr(128 ^ ord(ch)))
        return ''.join(result)

    # ===== 获取分类页 URL =====
    def get_cate_url(self, tid, pg=1, wd=None):
        """构造分类页/搜索页 URL"""
        if wd:
            return f"{self.host}/index.php/vod/type/id/{tid}/wd/{quote(wd)}/page/{pg}.html"
        else:
            return f"{self.host}/index.php/vod/type/id/{tid}/page/{pg}.html"

    # ===== 解析视频列表页 (兼容两种页面结构) =====
    def parse_list(self, html):
        """解析视频列表页，返回视频列表和总页数

        网站有两种页面结构:
        结构A (id=13等): <a class="vodbox" href="..."><div class="picbox">...<img data-original="..."/></div><p class="km-script">title</p></a>
        结构B (id=40等): <a href="..."><span class="img"><img data-original="..."/></span><span class="title km-script">title</span></a>
        """
        videos = []

        # 提取总页数
        total_pages = 1
        m = re.search(r"totalPages='(\d+)'", html)
        if m:
            total_pages = int(m.group(1))

        # 统一匹配两种结构: 所有包含 /html/dcdc/ 的 <a> 标签
        pattern = r'<a[^>]*href="([^"]*\/html\/dcdc\/[^"]+)"[^>]*>(.*?)</a>'
        matches = re.findall(pattern, html, re.DOTALL)

        for href, inner in matches:
            try:
                # HTML 实体解码 (&amp; -> &)
                href = href.replace('&amp;', '&')

                # 解析 URL 参数获取 m3u8 和封面图
                parsed = urlparse(href)
                params = parse_qs(parsed.query)
                v_url = params.get('v', [''])[0]
                b_url = params.get('b', [''])[0]

                # 提取封面图: 优先用 b 参数, 其次用 img data-original
                pic = b_url
                if not pic:
                    img_match = re.search(r'data-original="([^"]+)"', inner)
                    if img_match:
                        pic = img_match.group(1)

                # 提取并解密标题
                # 结构A: <p class="km-script">encrypted</p>
                # 结构B: <span class="title km-script">encrypted</span>
                # 统一匹配: 任何 class 含 km-script 的元素
                title = ""
                km_match = re.search(r'<(?:p|span)[^>]*class="[^"]*km-script[^"]*"[^>]*>(.*?)</(?:p|span)>', inner, re.DOTALL)
                if km_match:
                    title = self.decrypt(km_match.group(1).strip())
                if not title:
                    # 兜底: 普通p/span标签
                    fallback_match = re.search(r'<(?:p|span)[^>]*>(.*?)</(?:p|span)>', inner, re.DOTALL)
                    if fallback_match:
                        raw = fallback_match.group(1).strip()
                        try:
                            title = self.decrypt(raw)
                        except:
                            title = raw
                if not title:
                    title = "未知"

                # 构造 vod_id: 使用详情页完整路径作为 ID
                vod_id = href if href.startswith('http') else self.host + href

                videos.append({
                    "vod_id": vod_id,
                    "vod_name": title,
                    "vod_pic": pic,
                    "vod_remarks": ""
                })
            except Exception:
                continue

        return videos, total_pages

    # ===== 首页内容 =====
    def homeContent(self, filter):
        result = {}

        # 分类列表
        classes = []
        for k in self.cateManual:
            classes.append({
                "type_name": k,
                "type_id": self.cateManual[k]
            })
        result['class'] = classes

        # 子分类筛选 (网站无子分类筛选，返回空)
        filters = {}
        for tid in self.cateManual.values():
            filters[tid] = []
        result['filters'] = filters

        # 首页推荐视频 (取香蕉精品分类第一页)
        try:
            url = self.get_cate_url("13", 1)
            rsp = self.fetch(url, headers=self.headers)
            html = rsp.text
            videos, _ = self.parse_list(html)
            result['list'] = videos
        except Exception:
            result['list'] = []

        return result

    # ===== 首页视频内容 =====
    def homeVideoContent(self):
        try:
            url = self.get_cate_url("13", 1)
            rsp = self.fetch(url, headers=self.headers)
            html = rsp.text
            videos, _ = self.parse_list(html)
            return {'list': videos}
        except:
            return {'list': []}

    # ===== 分类内容 =====
    def categoryContent(self, tid, pg, filter, extend):
        result = {}

        page = int(pg) if pg else 1

        # 检查是否有搜索关键词 (extend 中可能包含)
        wd = None
        if extend and isinstance(extend, dict):
            wd = extend.get('wd', '')

        try:
            url = self.get_cate_url(tid, page, wd)
            rsp = self.fetch(url, headers=self.headers)
            html = rsp.text
            videos, total_pages = self.parse_list(html)

            result['list'] = videos
            result['page'] = page
            result['pagecount'] = total_pages
            result['limit'] = len(videos)
            result['total'] = total_pages * len(videos)
        except Exception:
            result['list'] = []
            result['page'] = page
            result['pagecount'] = 1
            result['limit'] = 0
            result['total'] = 0

        return result

    # ===== 通过 m 参数 API 获取真实 m3u8 =====
    def get_m3u8_by_mk(self, mk):
        """通过 h5.xxoo475.org API 获取真实 m3u8 地址

        网站播放器逻辑:
        - 有 v 参数: 直接用 v 作为 m3u8 地址
        - 有 m 参数: 调用 https://h5.xxoo475.org/api/v2/vod/reqplay/{m} 获取真实地址
          retcode==3 取 httpurl_preview, 否则取 httpurl
          最后去掉 ?300 后缀
        """
        try:
            api_url = f"https://h5.xxoo475.org/api/v2/vod/reqplay/{mk}"
            rsp = self.fetch(api_url, headers=self.headers)
            data = json.loads(rsp.text)
            if data.get('retcode') == 3:
                vod_url = data.get('data', {}).get('httpurl_preview', '')
            else:
                vod_url = data.get('data', {}).get('httpurl', '')
            # 去掉 ?300 后缀 (网站播放器的处理逻辑)
            vod_url = vod_url.replace('?300', '')
            return vod_url
        except Exception:
            return ""

    # ===== 详情内容 =====
    def detailContent(self, array):
        # array[0] 是 vod_id，即详情页完整 URL
        vod_id = array[0]
        result = {}

        try:
            # HTML 实体解码 (&amp; -> &)
            vod_id = vod_id.replace('&amp;', '&')
            # 从 URL 参数中提取播放信息
            parsed = urlparse(vod_id)
            params = parse_qs(parsed.query)
            v_url = params.get('v', [''])[0]   # v 参数: m3u8 直连
            m_url = params.get('m', [''])[0]   # m 参数: 需 API 获取
            b_url = params.get('b', [''])[0]   # b 参数: 封面图

            # 获取真实 m3u8 地址
            # 优先 v 参数(直连), 其次 m 参数(API获取)
            if v_url:
                m3u8_url = v_url
            elif m_url:
                m3u8_url = self.get_m3u8_by_mk(m_url)
            else:
                m3u8_url = ""

            # 获取详情页内容提取标题
            title = ""
            rsp = self.fetch(vod_id, headers=self.headers)
            html = rsp.text

            # 尝试从 km-script 元素中提取标题 (兼容p和span)
            km_match = re.search(r'<(?:p|span)[^>]*class="[^"]*km-script[^"]*"[^>]*>(.*?)</(?:p|span)>', html, re.DOTALL)
            if km_match:
                title = self.decrypt(km_match.group(1).strip())
            if not title:
                # 从 URL 路径中提取并解密
                path = unquote(parsed.path)
                path_match = re.search(r'/html/dcdc/(.+?)\.html', path)
                if path_match:
                    raw_title = path_match.group(1)
                    try:
                        title = self.decrypt(raw_title)
                    except:
                        title = raw_title
            if not title:
                title = "未知"

            # 构造播放列表
            # 注意: 播放地址中不能包含 # 字符, 否则 TVBox 会解析错误
            # 直接使用 m3u8 地址作为播放 ID
            play_from = "6182104"
            play_url = title + "$" + m3u8_url

            vod = {
                "vod_id": vod_id,
                "vod_name": title,
                "vod_pic": b_url,
                "type_name": "",
                "vod_year": "",
                "vod_area": "",
                "vod_remarks": "",
                "vod_actor": "",
                "vod_director": "",
                "vod_content": "",
                "vod_play_from": play_from,
                "vod_play_url": play_url
            }

            result['list'] = [vod]
        except Exception:
            result['list'] = []

        return result

    # ===== 搜索内容 =====
    def searchContent(self, key, quick):
        result = {}

        try:
            # 搜索 URL: 使用 id=2 进行搜索
            url = self.get_cate_url("2", 1, key)
            rsp = self.fetch(url, headers=self.headers)
            html = rsp.text
            videos, _ = self.parse_list(html)
            result['list'] = videos
        except Exception:
            result['list'] = []

        return result

    # ===== 播放内容 =====
    def playerContent(self, flag, id, vipFlags):
        # id 即为 m3u8 地址 (不再包含 # 封面图)
        m3u8_url = id

        result = {
            "parse": 0,       # 不需要解析, 直接播放
            "playUrl": "",
            "url": m3u8_url,
            "header": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Referer": self.host + "/"
            }
        }

        return result

    # ===== 视频格式判断 =====
    def isVideoFormat(self, url):
        if re.search(r'\.(m3u8|mp4|flv|avi|mkv|rmvb|wmv)(\?|#|$)', url, re.IGNORECASE):
            return True
        return False

    # ===== 手动检查 =====
    def manualVideoCheck(self):
        return False

    # ===== 验证 URL =====
    def verifyLiveUrl(self, url):
        return url
