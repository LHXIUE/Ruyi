#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
橘子影视 (xiaoyemao.org) —— TVBox / 影视仓 Python 爬虫源 (dr_py / py-drpy)
功能: 首页推荐 / 分类浏览+翻页 / 搜索 / 详情选集 / 播放(m3u8)
依赖: requests beautifulsoup4 (无 bs4 时回退正则)

站点特点(2026-09 实测逆向):
1. MacCMS v10 + mxone 模板, 标准 HTML 服务端渲染
2. JSON 采集接口已关闭(返回 closed), 走 HTML 解析
3. 播放页 player_aaaa JS 对象携带 url 字段(encrypt=0, 直接为 m3u8 直链或二级播放页)
4. 分片 AES-128 加密, KEY 在 m3u8 同目录(相对 URI, 播放器自动 urljoin)
5. m3u8 / enc.key / .ts 分片均无防盗链, 实测直连 200 -> 播放地址用 m3u8 直链,
   AES-128 由播放器原生解码(见 USE_PROXY 开关, 默认直链不走代理)

2026-09-15 修复记录:
- [致命] 类名 SpiderCustom -> Spider: dr_py 强制按 Spider 类名加载, 原类名导致源无法载入
- [致命] detailContent 返回 {"list": [...]}: 原返回裸 list, TVBox 详情页空白无剧集
- [骨架] 补齐 init/getName/homeVideoContent/isVideoFormat/manualVideoCheck
- [规范] homeContent 只返回 {class, filters}, 推荐列表由 homeVideoContent 独立返回
- [bug] _parse_list main_only: 第二页列表 class 是 module-lines-list(非 line-list) 导致
        解析回退全页混入 320 条噪音; 改为"page-heading 后第一个含详情链接的
        module-list/items 容器", 并限定卡片选择器(module-item / module-search-item)
- [bug] 搜索卡片 class 为 module-search-item, 原卡片正则未覆盖, 标题/封面靠兜底
- [规范] localProxy 返回 [200, type, content, {}] 四元组
- [增强] _extract_m3u8 增加 encrypt 字段判断, 非 0 交 parse:1 由 TVBox 内置解析
- [收敛] 分页: 页面无数字分页条, pagecount 采用渐进式(空页即停止, 不会无限翻页)
- [自检] 增加 __main__ 自检块, 本地可直接 python 运行验证

2026-09-16 修复记录(不能播放):
- [核心] 播放地址改为 m3u8 直链(parse:0), 不再走 proxy:// 中转:
        本站 m3u8 / enc.key / .ts 分片实测均无防盗链(直连 200), AES-128 由
        播放器原生解码(URI 为同目录相对路径, 播放器自动 urljoin);
        proxy:// 中转在影视仓等播放器上存在协议兼容问题, 是"不能播放"最大嫌疑。
- [开关] 新增模块级常量 USE_PROXY: 默认 False(直链);
        若所在网络无法直连分片域非标端口(如 p.jisuts.com:999),
        可改为 True 恢复 localProxy 中转模式(服务端带 header 拉流)。
"""

import re
import json
import time
import random
import logging
import urllib.parse
import requests

try:
    from base.spider import Spider
except ImportError:
    # 本地调试桩: dr_py/TVBox 环境下由真实基类替换, 仅用于 __main__ 自检
    class Spider(object):
        def fetch(self, url, **kwargs):
            return ""

        def localProxy(self, param):
            return []

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except Exception:
    HAS_BS4 = False

logger = logging.getLogger("xiaoyemao")

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

# 播放模式开关:
# False(默认) = m3u8 直链, 播放器原生解码 AES-128(本站 m3u8/key/分片均无防盗链)
# True         = localProxy 中转(proxy://), 适合分片域非标端口(如 :999)被
#               客户端网络阻断、直连失败的场景; 需 dr_py 服务器能访问源站
USE_PROXY = False


class Spider(Spider):
    """橘子影视 爬虫源 (dr_py 要求类名必须为 Spider)"""

    # ==================== 基础配置 ====================
    name = "橘子影视"
    base_url = "http://xiaoyemao.org"
    site_url = "http://xiaoyemao.org"

    # ==================== 分类映射 (MacCMS type_id) ====================
    class_name = ["电影", "电视剧", "综艺", "动漫", "短剧"]
    class_url = ["1", "2", "3", "4", "32"]

    headers = {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": "http://xiaoyemao.org/",
    }
    ua_pool = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    ]
    timeout = 15
    max_retry = 3
    _limit = 20

    # ==================== 基类骨架方法 ====================

    def init(self, cfg):
        """dr_py 注入配置(一般无自定义项)"""
        return True

    def getName(self):
        return self.name

    def isVideoFormat(self, url):
        """判断是否为可播视频地址(proxy:// 代理流同样放行)"""
        if not url:
            return False
        low = url.lower()
        if low.startswith("proxy://"):
            return True
        return any(ext in low for ext in (".m3u8", ".mp4", ".ts", ".mkv", ".flv"))

    def manualVideoCheck(self):
        """不使用手动验证"""
        return False

    # ==================== 工具函数 ====================

    def _abs(self, url):
        if not url:
            return ""
        if url.startswith("http"):
            return url
        return urllib.parse.urljoin(self.base_url + "/", url.lstrip("/"))

    def _get(self, url, retry=None, timeout=None, ref=None):
        """GET请求封装：随机UA + 超时 + 重试"""
        retry = self.max_retry if retry is None else retry
        timeout = timeout or self.timeout
        for i in range(retry):
            try:
                h = dict(self.headers)
                h["User-Agent"] = random.choice(self.ua_pool)
                if ref:
                    h["Referer"] = ref
                resp = requests.get(url, headers=h, timeout=timeout)
                if resp.status_code == 200:
                    resp.encoding = resp.apparent_encoding or "utf-8"
                    return resp.text
                if resp.status_code in (429, 403):
                    logger.warning("[%s] 限流(%s) %s", self.name, resp.status_code, url)
                    time.sleep(random.uniform(3, 8))
                    continue
                logger.warning("[%s] HTTP %s: %s", self.name, resp.status_code, url)
                return None
            except Exception as e:
                logger.warning("[%s] 请求异常: %s (%s)", self.name, e, url)
                time.sleep(random.uniform(1.5, 4))
        return None

    def _get_bytes(self, url, timeout=None, ref=None):
        """拉取二进制(分片/KEY), 失败返回 b''"""
        timeout = timeout or (6, 15)
        try:
            h = {"User-Agent": random.choice(self.ua_pool)}
            if ref:
                h["Referer"] = ref
            r = requests.get(url, headers=h, timeout=timeout)
            if r.status_code == 200 and r.content[:2] not in (b"<!", b"<h"):
                return r.content
        except Exception:
            pass
        return b""

    # ==================== 列表解析 ====================

    def _card_selector(self):
        """详情链接选择器: 本站 detail 链接只出现在影片卡片区(导航为 type/search
        链接), 配合 _main_scope 收敛主体列表即可, 无需再按卡片容器过滤
        (module-line-list 横向列表的链接不在 div.module-item 内)。"""
        return "a[href*='/vod/detail/id/']"

    def _main_scope(self, soup):
        """兼容 mxone 模板多种列表 class(页面结构已实测):
        - type 页: page-heading 后先有一个 4 条的横向推荐条(module-lines-list),
          其后才是当前分类主体 module-line-list(多为 32 条网格)
        - show 翻页页: 同样先有 4 条推荐条(module-lines-list), 主体为后续
          无后缀的 module-list(72 条)
        - 搜索页: 无 page-heading, 返回整个 soup, 由泛化匹配兜底
        策略: 存在 module-line-list 时取第一个(网格主体);
        否则在所有候选列表容器中取详情链接去重数最大的(主体)。
        """
        ph = soup.find("div", class_="page-heading")
        if not ph:
            return soup
        candidates = []
        for nxt in ph.find_all_next():
            if nxt.name != "div":
                continue
            tokens = set(nxt.get("class", []))
            if "module-list" not in tokens and "module-items" not in tokens:
                continue
            links = nxt.select("a[href*='/vod/detail/id/']")
            if not links:
                continue
            if "module-line-list" in tokens:
                return nxt
            n_uniq = len({re.search(r'/vod/detail/id/(\d+)\.html', a["href"]).group(1) for a in links})
            candidates.append((n_uniq, nxt))
        if not candidates:
            return soup
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]

    def _parse_list(self, html, main_only=False):
        """解析首页/分类/搜索页影片卡片
        main_only=True 时只取分类主体列表, 避免混入推荐/排行区。
        """
        items = []
        if not html:
            return items
        if HAS_BS4:
            soup = BeautifulSoup(html, "html.parser")
            scope = self._main_scope(soup) if main_only else soup
            sel = self._card_selector()
            seen = set()
            for a in scope.select(sel):
                href = a["href"]
                m = re.search(r'/vod/detail/id/(\d+)\.html', href)
                if not m:
                    continue
                vid = m.group(1)
                if vid in seen:
                    continue
                # 标题: 卡片内标题元素文本优先, a[title] 兜底, 过滤长SEO描述
                name = ""
                card = a.find_parent("div", class_=re.compile(r"module-item|module-search-item|video-item|stui-vodlist|swiper-slide"))
                if card:
                    t_el = (card.select_one(".module-item-title") or card.select_one(".module-item-titlebox a")
                            or card.select_one("h3") or card.select_one("h4")
                            or card.select_one(".video-title"))
                    if t_el:
                        name = t_el.get_text(" ", strip=True)
                if not name:
                    name = a.get("title", "").strip() or ""
                    if len(name) > 30:  # SEO长描述, 弃用
                        name = ""
                if not name:
                    img0 = a.find("img")
                    if img0:
                        name = img0.get("alt", "")
                if not name or len(name) > 30:
                    continue
                seen.add(vid)
                # 封面: 卡片容器内 img
                pic = ""
                card = a.find_parent("div", class_=re.compile(r"module-item|module-search-item|video-item|stui-vodlist"))
                if card:
                    img = card.find("img")
                    if img:
                        pic = img.get("data-src") or img.get("src") or ""
                else:
                    img = a.find_previous("img")
                    if img:
                        pic = img.get("data-src") or img.get("src") or ""
                # 备注
                remark = ""
                if card:
                    remark_el = card.select_one(".module-item-text") or card.select_one(".module-item-caption")
                    if remark_el:
                        remark = remark_el.get_text(" ", strip=True)
                items.append({
                    "vod_id": vid,
                    "vod_name": name,
                    "vod_pic": self._abs(pic),
                    "vod_remarks": remark[:40],
                })
        else:
            # 正则回退
            seen = set()
            if main_only:
                seg = html
                m = re.search(r'class="page-heading"', seg)
                if m:
                    m2 = re.search(r'class="module-list (?:module-line-list|module-lines-list|module-items)"', seg[m.end():])
                    if m2:
                        seg = seg[m.end() + m2.start():m.end() + m2.start() + 50000]
                for m in re.finditer(r'<a[^>]*href="([^"]*/vod/detail/id/(\d+)\.html)"[^>]*title="([^"]*)"', seg):
                    href, vid, name = m.group(1), m.group(2), m.group(3)
                    if vid in seen or not name:
                        continue
                    seen.add(vid)
                    pic = ""
                    pm = re.search(r'data-src="([^"]+)"', seg[max(0, m.start() - 600):m.start()])
                    if pm:
                        pic = pm.group(1)
                    items.append({"vod_id": vid, "vod_name": name,
                                 "vod_pic": self._abs(pic), "vod_remarks": ""})
            else:
                for m in re.finditer(r'<a[^>]*href="([^"]*/vod/detail/id/(\d+)\.html)"[^>]*title="([^"]*)"', html):
                    href, vid, name = m.group(1), m.group(2), m.group(3)
                    if vid in seen or not name:
                        continue
                    seen.add(vid)
                    pic = ""
                    pm = re.search(r'data-src="([^"]+)"', html[max(0, m.start() - 600):m.start()])
                    if pm:
                        pic = pm.group(1)
                    items.append({"vod_id": vid, "vod_name": name,
                                 "vod_pic": self._abs(pic), "vod_remarks": ""})
        return items

    # ==================== 首页 ====================

    def homeContent(self, filter=False):
        """首页分类 + 筛选(推荐列表由 homeVideoContent 独立返回)"""
        result = {"class": [], "filters": {}}
        try:
            result["class"] = [
                {"type_id": tid, "type_name": name}
                for tid, name in zip(self.class_url, self.class_name)
            ]
            logger.info("[%s] homeContent 分类 %d 个", self.name, len(result["class"]))
        except Exception as e:
            logger.warning("[%s] homeContent异常: %s", self.name, e)
        return result

    def homeVideoContent(self, filter=False):
        """首页推荐"""
        result = {"list": []}
        try:
            html = self._get(self.base_url + "/")
            result["list"] = self._parse_list(html)
            if not result["list"]:
                # 首页推荐为空则用分类页兜底
                html = self._get(f"{self.base_url}/index.php/vod/show/id/1.html")
                result["list"] = self._parse_list(html, main_only=True)
            logger.info("[%s] 首页推荐 %d 条", self.name, len(result["list"]))
        except Exception as e:
            logger.warning("[%s] 首页异常: %s", self.name, e)
        return result

    def categoryContent(self, tid, pg, filter=False, content=None):
        """分类列表 (MacCMS)"""
        result = {
            "list": [],
            "page": int(pg or 1),
            "pagecount": 0,
            "limit": self._limit,
            "total": 0,
        }
        try:
            pg = int(pg or 1)
            if pg <= 1:
                url = f"{self.base_url}/index.php/vod/type/id/{tid}.html"
            else:
                # 分页用 show 频道格式(实测 /page/{pg}.html 有效)
                url = f"{self.base_url}/index.php/vod/show/id/{tid}/page/{pg}.html"
            html = self._get(url)
            if not html:
                return result
            result["list"] = self._parse_list(html, main_only=True)
            result["page"] = pg
            # 页面无数字分页条, 用渐进式: 当前页有内容->还有下一页; 空页->停止
            result["pagecount"] = pg + 1 if result["list"] else pg
            result["total"] = len(result["list"]) * pg
            logger.info("[%s] 分类 %s 第%s页: %d 条", self.name, tid, pg, len(result["list"]))
        except Exception as e:
            logger.warning("[%s] 分类异常: %s", self.name, e)
        return result

    # ==================== 详情 ====================

    def detailContent(self, ids):
        """影片详情 + 多线路剧集 (返回 {"list": [...]})"""
        result = []
        vod_id = ids if isinstance(ids, str) else (ids[0] if ids else "")
        if not vod_id:
            return {"list": result}
        try:
            url = f"{self.base_url}/index.php/vod/detail/id/{vod_id}.html"
            html = self._get(url)
            if not html:
                return {"list": result}

            if HAS_BS4:
                soup = BeautifulSoup(html, "html.parser")
                # 标题
                vod_name = ""
                h1 = soup.find("h1")
                if h1:
                    vod_name = h1.get_text(strip=True)
                if not vod_name:
                    title_tag = soup.find("title")
                    if title_tag:
                        t = title_tag.get_text(strip=True)
                        vod_name = re.split(r'[_-]', t)[0].strip()
                # 封面
                vod_pic = ""
                img = soup.select_one(".module-info-poster img") or soup.select_one("img[data-src*='cover']")
                if img:
                    vod_pic = img.get("data-src") or img.get("src") or ""
                # 简介
                vod_content = ""
                desc = soup.select_one(".module-info-introduction") or soup.select_one(".txt-info")
                if desc:
                    vod_content = desc.get_text(" ", strip=True)
                meta_desc = soup.find("meta", attrs={"name": "description"})
                if meta_desc and meta_desc.get("content"):
                    vod_content = vod_content or meta_desc["content"].strip()

                # 线路 + 剧集: 每个 tab-item 对应一个 glist-{idx} 列表(实测 idx 从 1 起)
                line_names, line_urls = [], []
                tab_items = soup.select("div.module-tab-item.tab-item[data-dropdown-value]")
                if tab_items:
                    for idx, tab in enumerate(tab_items, start=1):
                        line_name = tab.get("data-dropdown-value", "").strip()
                        if not line_name:
                            continue
                        gid = "glist-%d" % idx
                        glist = soup.find("div", id=gid)
                        if not glist:
                            glist = soup.find("div", attrs={"data-dropdown-value": line_name})
                        eps = []
                        if glist:
                            for a in glist.select("a[href*='/vod/play/']"):
                                href = a["href"].strip()
                                ep_name = a.get_text(" ", strip=True) or a.get("title", "")
                                if not ep_name:
                                    ep_name = "第%d集" % (len(eps) + 1)
                                eps.append("%s$%s" % (ep_name, href))
                        if eps:
                            line_names.append(line_name)
                            line_urls.append("#".join(eps))
                if not line_names:
                    # 兜底: 从所有 play 链接按 sid 分组
                    groups = {}
                    for a in soup.select("a[href*='/vod/play/']"):
                        href = a["href"].strip()
                        m = re.search(r'/sid/(\d+)/', href)
                        sid = m.group(1) if m else "1"
                        ep_name = a.get_text(" ", strip=True) or a.get("title", "") or f"第{len(groups.get(sid, [])) + 1}集"
                        groups.setdefault(sid, []).append(f"{ep_name}${href}")
                    for sid, eps in groups.items():
                        line_names.append(f"线路{sid}")
                        line_urls.append("#".join(eps))

                vod = {
                    "vod_id": vod_id,
                    "vod_name": vod_name,
                    "vod_pic": self._abs(vod_pic),
                    "vod_year": "",
                    "vod_area": "",
                    "vod_director": "",
                    "vod_actor": "",
                    "vod_type": "",
                    "vod_content": vod_content,
                    "vod_play_from": "$$$".join(line_names),
                    "vod_play_url": "$$$".join(line_urls),
                }
                result.append(vod)
            else:
                # 正则回退
                result = self._detail_regex(html, vod_id)
            logger.info("[%s] 详情 %s: %d 线路", self.name, vod_name,
                        len(vod.get("vod_play_from", "").split("$$$")) if vod else 0)
        except Exception as e:
            logger.warning("[%s] 详情异常: %s", self.name, e)
        return {"list": result}

    def _detail_regex(self, html, vod_id):
        """无 bs4 时正则解析详情"""
        result = []
        m = re.search(r'<h1[^>]*>([^<]+)</h1>', html)
        vod_name = m.group(1).strip() if m else ""
        # 线路
        tabs = re.findall(r'data-dropdown-value="([^"]+)"', html)
        line_names, line_urls = [], []
        used = set()
        for i, name in enumerate(tabs, start=1):
            if name in used:
                continue
            used.add(name)
            gid = f"glist-{i}"
            blk = re.search(rf'id="{gid}"(.*?)(?:<div class="module-list|<div class="player|</main>)', html, re.S)
            if not blk:
                continue
            eps = re.findall(r'<a[^>]*href="([^"]*/vod/play/[^"]+)"[^>]*>([\s\S]*?)</a>', blk.group(1))
            ep_parts = []
            for href, txt in eps:
                ep_name = re.sub(r'<[^>]+>', '', txt).strip() or f"第{len(ep_parts) + 1}集"
                ep_parts.append(f"{ep_name}${href}")
            if ep_parts:
                line_names.append(name)
                line_urls.append("#".join(ep_parts))
        if not line_names:
            all_eps = re.findall(r'<a[^>]*href="([^"]*/vod/play/[^"]+)"[^>]*>([\s\S]*?)</a>', html)
            groups = {}
            for href, txt in all_eps:
                sm = re.search(r'/sid/(\d+)/', href)
                sid = sm.group(1) if sm else "1"
                ep_name = re.sub(r'<[^>]+>', '', txt).strip() or f"第{len(groups.get(sid, [])) + 1}集"
                groups.setdefault(sid, []).append(f"{ep_name}${href}")
            for sid, eps in groups.items():
                line_names.append(f"线路{sid}")
                line_urls.append("#".join(eps))
        vod = {
            "vod_id": vod_id,
            "vod_name": vod_name,
            "vod_pic": "",
            "vod_content": "",
            "vod_play_from": "$$$".join(line_names),
            "vod_play_url": "$$$".join(line_urls),
        }
        if vod_name and line_urls:
            result.append(vod)
        return result

    # ==================== 搜索 ====================

    def searchContent(self, key, pg, filter=False):
        """关键词搜索 (pg 必带, 兼容 quick 布尔值入参)"""
        result = {
            "list": [],
            "page": int(pg or 1),
            "pagecount": 0,
            "limit": self._limit,
            "total": 0,
        }
        if not key:
            return result
        try:
            url = f"{self.base_url}/index.php/vod/search.html?wd={urllib.parse.quote(key)}"
            html = self._get(url)
            if not html:
                return result
            result["list"] = self._parse_list(html, main_only=True)
            result["pagecount"] = 1
            result["total"] = len(result["list"])
            logger.info("[%s] 搜索 %s: %d 条", self.name, key, len(result["list"]))
        except Exception as e:
            logger.warning("[%s] 搜索异常: %s", self.name, e)
        return result

    # ==================== 播放解析 ====================

    def _extract_m3u8(self, play_url):
        """
        播放页解析:
        1. 抓播放页 -> player_aaaa JS 对象 -> url 字段(encrypt=0 时有效)
        2. url 是 m3u8 直链则直接返回
        3. url 是二级播放页(如 https://hd.kuktxu.com/play/xxx) 则 + /index.m3u8
        4. encrypt != 0 为站内加密, 本爬虫无解密能力, 返回 "" 交 parse:1
        """
        try:
            html = self._get(play_url, timeout=(6, 12))
            if not html:
                return ""
            # 1. player_aaaa JSON (MacCMS 标准: var player_aaaa={...}</script>)
            m = re.search(r'player_aaaa\s*=\s*(\{.*?\})\s*</script>', html, re.S)
            if m:
                raw = m.group(1).replace("\\/", "/")
                try:
                    d = json.loads(raw)
                    u = d.get("url", "")
                    enc = int(d.get("encrypt", 0) or 0)
                    if u and enc == 0:
                        if u.endswith(".m3u8"):
                            return u
                        # 二级页 -> 加 /index.m3u8
                        return u.rstrip("/") + "/index.m3u8"
                    # encrypt != 0: 站内加密无解密实现, 交 TVBox 内置解析
                    return ""
                except Exception:
                    pass
            # 2. 直接 m3u8
            m2 = re.search(r'https?://[^\s"\'<>\\]+?\.m3u8[^\s"\'<>\\]*', html)
            if m2:
                return m2.group(0)
            # 3. iframe
            m3 = re.search(r'<iframe[^>]*src="([^"]+)"', html)
            if m3:
                src = m3.group(1)
                if not src.startswith("http"):
                    src = urllib.parse.urljoin(self.base_url, src)
                # iframe 内抓 m3u8
                iframe_html = self._get(src, timeout=(6, 12))
                if iframe_html:
                    m4 = re.search(r'https?://[^\s"\'<>\\]+?\.m3u8[^\s"\'<>\\]*', iframe_html)
                    if m4:
                        return m4.group(0)
                    # iframe 里 url 参数
                    mm = re.search(r'[?&]url=([^&"\'<>]+)', src)
                    if mm:
                        u = urllib.parse.unquote(mm.group(1))
                        if ".m3u8" in u:
                            return u
                        return u.rstrip("/") + "/index.m3u8"
            return ""
        except Exception as e:
            logger.warning("[%s] 播放解析异常: %s", self.name, e)
            return ""

    def playerContent(self, flag, id, vipFlags=None):
        """播放地址解析:
        默认返回 m3u8 直链(parse:0), 由播放器原生拉流并解码 AES-128;
        USE_PROXY=True 时返回 proxy:// 走 localProxy 中转(服务端拉流)。
        """
        try:
            pid = str(id).strip()
            play_url = pid if pid.startswith("http") else self._abs(pid)
            m3u8 = self._extract_m3u8(play_url)
            if m3u8:
                if USE_PROXY:
                    # 本地代理: 播放器经 dr_py 服务器拉流(实测 m3u8/key/ts 均无防盗链)
                    return {
                        "parse": 0,
                        "url": "proxy://do=m3u8&url=" + urllib.parse.quote(m3u8, safe=""),
                        "header": {},
                    }
                # 直链: AES-128 由播放器原生处理, key 相对路径自动 urljoin
                return {
                    "parse": 0,
                    "url": m3u8,
                    "header": {"User-Agent": UA, "Referer": self.base_url + "/"},
                }
            return {"parse": 1, "url": play_url,
                    "header": {"User-Agent": UA}}
        except Exception as e:
            logger.warning("[%s] playerContent异常: %s", self.name, e)
            return {"parse": 1, "url": id, "header": {}}

    # ==================== 本地代理 ====================

    def localProxy(self, param):
        """本地代理: m3u8/分片/KEY 经服务端中转
        返回 [200, content-type, data, {}] 四元组(dr_py 规范)
        """
        try:
            if isinstance(param, dict):
                do = param.get("do", "")
                u = param.get("url", "")
            else:
                qs = str(param or "")
                dm = re.search(r'do=([^&]+)', qs)
                do = dm.group(1) if dm else ""
                um = re.search(r'url=([^&\s"]+)', qs)
                u = um.group(1) if um else ""
            u = urllib.parse.unquote(u.strip()).strip('"').strip("'")
            if not u or not do:
                return []

            if do == "seg":
                data = self._get_bytes(u)
                if not data:
                    return []
                return [200, "video/mp2t", data, {}]

            if do == "key":
                data = self._get_bytes(u)
                if not data:
                    return []
                return [200, "application/octet-stream", data, {}]

            # do == m3u8 (含子流)
            txt = self._get(u, timeout=(8, 15))
            if not txt or "#EXTM3U" not in txt:
                return []
            out = []
            for ln in txt.splitlines():
                s = ln.strip()
                if not s:
                    out.append(ln)
                    continue
                if s.startswith("#"):
                    km = re.search(r'URI="([^"]+)"', s)
                    if km:
                        kurl = urllib.parse.urljoin(u, km.group(1))
                        out.append(s.replace(km.group(1),
                                             "proxy://do=key&url=" + urllib.parse.quote(kurl, safe="")))
                    else:
                        out.append(ln)
                    continue
                if s.startswith("proxy://"):
                    out.append(ln)
                    continue
                full = urllib.parse.urljoin(u, s)
                if s.endswith(".m3u8"):
                    out.append("proxy://do=m3u8&url=" + urllib.parse.quote(full, safe=""))
                else:
                    out.append("proxy://do=seg&url=" + urllib.parse.quote(full, safe=""))
            return [200, "application/vnd.apple.mpegurl",
                    "\n".join(out).encode("utf-8"), {}]
        except Exception as e:
            logger.warning("[%s] localProxy异常: %s", self.name, e)
            return []


# ==================== 自检 ====================

def _selftest():
    """接口自检: 需网络可用; 逐个接口验证并输出 PASS/FAIL"""
    s = Spider()
    fails = []
    out = []

    def check(tag, cond, detail=""):
        out.append(("[PASS] " if cond else "[FAIL] ") + tag + ((" | " + detail) if detail else ""))
        if not cond:
            fails.append(tag)

    check("getName", s.getName() == "橘子影视", s.getName())

    h = s.homeContent()
    check("homeContent 分类", bool(h.get("class")), str(len(h.get("class", []))))

    hv = s.homeVideoContent()
    check("homeVideoContent 推荐", bool(hv.get("list")), f"{len(hv.get('list', []))} 条")
    if hv.get("list"):
        it = hv["list"][0]
        check("首页条目标题/封面", bool(it.get("vod_name")) and bool(it.get("vod_pic")),
              f"{it.get('vod_name')} | {it.get('vod_pic', '')[:40]}")

    c = s.categoryContent("1", 1)
    check("categoryContent 分类1", bool(c.get("list")) and len(c.get("list", [])) >= 20,
          f"{len(c.get('list', []))} 条 pagecount={c.get('pagecount')}")
    c2 = s.categoryContent("1", 2)
    check("categoryContent 第2页", bool(c2.get("list")) and len(c2.get("list", [])) >= 20,
          f"{len(c2.get('list', []))} 条")
    # 第2页不应混入第1页特有的横向推荐条内容(4条区), 抽样对比允许站点本身重叠
    p1_titles = {i["vod_name"] for i in c.get("list", [])}
    p2_only = [i["vod_name"] for i in c2.get("list", []) if i["vod_name"] not in p1_titles]
    check("第2页与第1页主体有差异", len(p2_only) >= len(c2.get("list", [])) // 2,
          f"第2页独有条目 {len(p2_only)}/{len(c2.get('list', []))}")

    q = s.searchContent("求救信号", 1)
    check("searchContent", bool(q.get("list")), f"{len(q.get('list', []))} 条")
    if q.get("list"):
        check("搜索结果带封面", bool(q["list"][0].get("vod_pic")), q["list"][0].get("vod_pic", "")[:40])

    d = s.detailContent(["119188"])
    vl = d.get("list", []) if isinstance(d, dict) else d
    check("detailContent 返回dict", isinstance(d, dict), str(type(d).__name__))
    check("detailContent 线路", bool(vl) and bool(vl[0].get("vod_play_url")),
          f"{len(vl[0].get('vod_play_from', '').split('$$$')) if vl else 0} 线路")
    if vl and vl[0].get("vod_play_url"):
        first_ep = vl[0]["vod_play_url"].split("#")[0].split("$")[-1]
        p = s.playerContent("", first_ep)
        check("playerContent", p.get("parse") == 0,
              str(p.get("url", ""))[:70])
        # 直链模式: url 应为 m3u8 直链且可拉取
        if USE_PROXY:
            pu = p.get("url", "")
            m = re.search(r'url=([^&]+)', pu)
            if m:
                lp = s.localProxy("do=m3u8&url=" + m.group(1))
                check("localProxy m3u8", len(lp) == 4 and lp[0] == 200 and b"#EXTM3U" in (lp[2] or b""),
                      f"len={len(lp)} type={lp[1] if len(lp) > 1 else '-'}")
        else:
            pu = p.get("url", "")
            check("播放直链可拉取", pu.startswith("http") and "proxy" not in pu,
                  pu[:80])
            if pu.startswith("http"):
                txt3 = s._get(pu, timeout=(6, 12))
                check("播放直链为m3u8", txt3 and "#EXTM3U" in txt3,
                      f"{len(txt3 or '')}B")

    check("isVideoFormat", s.isVideoFormat("https://x/a.m3u8") and s.isVideoFormat("proxy://do=seg&url=x"),
          "")
    check("manualVideoCheck", s.manualVideoCheck() is False, "")

    print("\n".join(out))
    print(f"\n自检结果: {'ALL PASS' if not fails else 'FAILED: ' + ', '.join(fails)}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    _selftest()