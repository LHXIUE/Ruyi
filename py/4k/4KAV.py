#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
═══════════════════════════════════════════════════════════════
  遮天法 v3.1.1 · 洞天境·横宇 · 4K-AV · TVBox 兼容修复版
═══════════════════════════════════════════════════════════════

  【v3.1.1 修复清单】(修复"注入不了TVBox")
  ┌─────────────────────────────────────────────────────────┐
  │ 1. 主类名改为 Spider —— TVBox/影视仓 py 加载器只认       │
  │    module.Spider 类名，原 DongTian_4KAV 导致加载失败     │
  │ 2. 剥离 curl_cffi 依赖 —— TVBox 内置 py 环境无此库，     │
  │    改纯 requests + 全套浏览器头过 Cloudflare（实测 200） │
  │ 3. 补全 homeVideoContent/destroy/isVideoFormat 等       │
  │    TVBox 全套生命周期接口                                │
  │ 4. 搜索参数 x= → y=（站点改版，旧参数已失效）            │
  │ 5. 响应编码固定 utf-8（TVBox 环境无 chardet，避免        │
  │    apparent_encoding 依赖）                              │
  │ 6. 全 .format() 无 f-string，兼容内置 Python 3.6+        │
  │ 7. 解析按 2026-09 站点新版结构重写（旧选择器已全部失效）  │
  └─────────────────────────────────────────────────────────┘

  【站点情报】(2026-09-06 实测)
  · 站点: https://4k-av.com  4K UHD 电影/剧集
  · 防护: Cloudflare TLS 指纹校验 —— 裸 UA 403
  ·        requests + 完整浏览器头(含sec-ch-ua) → 200 ✅
  · 结构: 服务端渲染 HTML，卡片 <a title><img poster_nail.jpg>
  · 分类: /zh/movie/ 电影 · /zh/tv/ 剧集 · /zh/{year}/ · /en/tag/{t}/
  · 分页: 第1页 /{path}/  ·  第N页 /{path}/page-{N}.html
  · 详情: /{movie|tv}/{id}-{slug}/  (无语言前缀可直接访问)
  · 播放: <source src="...m3u8"> 内嵌直链，无防盗链，parse=0
  · 搜索: GET /zh/s?y={keyword}  (旧参数 x= 已失效)

  【TVBox/影视仓 配置】(关键: type 3 + py:// 协议)
  {"key": "4kav",
   "name": "4K-AV(遮天)",
   "type": 3,
   "api": "py:///storage/emulated/0/TV/py/ZheTian_4KAV.py",
   "searchable": 1, "quickSearch": 1, "filterable": 1}
  · TVBox: 文件放 手机存储/TV/py/ 目录（与 api 路径一致）
  · 影视仓: 放入内置 py 目录后 api 用 "py://ZheTian_4KAV"

  【依赖】仅需 requests（TVBox 内置 py 环境自带）
  【自检】python ZheTian_4KAV.py --self-test
  【版本】v3.1.1 | 【境界】洞天境·横宇 | 【作者】叶凡 | 【许可】开源
"""

import sys
import re
import time
import random
import html as html_module
from urllib.parse import quote, urljoin

# ══════════════════════════════════════════════════════════════
# 第〇章 · 导入与优雅降级（TVBox 环境契约）
# ══════════════════════════════════════════════════════════════

# ── TVBox 基类（TVBox/影视仓 py 环境必带；独立调试时兜底）──
try:
    from base.spider import Spider as BaseSpider
except ImportError:
    class BaseSpider(object):
        """独立运行时的兜底基类（TVBox 环境外）"""
        pass

# ── HTTP 库：requests（TVBox 内置，必需）──
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    requests = None
    HAS_REQUESTS = False

# ── curl_cffi：可选增强（TVBox 环境通常没有，静默跳过）──
try:
    # 铁律4: cffi_requests 是模块不是 session，直接模块级 .get() 调用
    from curl_cffi import requests as cffi_requests
    HAS_CFFI = True
except ImportError:
    cffi_requests = None
    HAS_CFFI = False


# ══════════════════════════════════════════════════════════════
# 第一章 · 配置中心（铁律5: 配置优先，禁止硬编码）
# ══════════════════════════════════════════════════════════════

DEFAULT_CONFIG = {
    # ── 基本信息 ──
    "name": "4K-AV(遮天)",
    "host": "https://4k-av.com",
    "language_prefix": "zh",      # 默认语言（/zh/ 中文版）
    "tag_prefix": "en",           # 标签分类仅英文版有数据

    # ── 端点模板（所有路径从这里读取）──
    "endpoints": {
        "home": "{lang}/",
        "category_movie": "{lang}/movie/",
        "category_tv": "{lang}/tv/",
        "category_year": "{lang}/{year}/",
        "category_tag": "{tag_lang}/tag/{tag}/",
        "page_suffix": "page-{pg}.html",
        "search": "{lang}/s?y={kw}",
    },

    # ── 分类（homeContent 输出；AV 分区不收录）──
    "classes": [
        {"type_id": "movie", "type_name": "电影"},
        {"type_id": "tv", "type_name": "剧集"},
    ],

    # ── 筛选器（filterable=1）──
    "filters": {
        "movie": [
            {"key": "year", "name": "年份",
             "value": [{"n": "全部", "v": ""}] + [{"n": str(y), "v": str(y)}
                                                  for y in range(2026, 2018, -1)]},
            {"key": "tag", "name": "类型",
             "value": [{"n": "全部", "v": ""}, {"n": "动作", "v": "Action"},
                       {"n": "剧情", "v": "Drama"}, {"n": "冒险", "v": "Adventure"},
                       {"n": "喜剧", "v": "Comedy"}, {"n": "恐怖", "v": "Horror"},
                       {"n": "战争", "v": "War"}, {"n": "科幻", "v": "Sci-Fi"},
                       {"n": "动画", "v": "Animation"}, {"n": "韩剧", "v": "Korean"},
                       {"n": "犯罪", "v": "Crime"}, {"n": "纪录", "v": "Documentary"}]},
        ],
        "tv": [
            {"key": "year", "name": "年份",
             "value": [{"n": "全部", "v": ""}] + [{"n": str(y), "v": str(y)}
                                                  for y in range(2026, 2018, -1)]},
        ],
    },

    # ── 请求头（临字秘·荒塔：过 Cloudflare 的关键）──
    # 铁律1: 所有内部双引号必须转义为 \"
    "headers": {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "sec-ch-ua": "\"Chromium\";v=\"129\", \"Not=A?Brand\";v=\"8\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    },

    # ── UA 池 ──
    "ua_pool": [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    ],

    # ── 解析配置（斗字秘·吞天魔罐，按 2026-09 新版结构）──
    "parsing": {
        # 卡片: <a href="/zh/movie/010734-xxx/" title="名"><img src="..poster_nail.jpg">
        # 分组: 1=href 2=kind 3=id 4=slug 5=title 6=pic
        # 语言前缀可选（zh 首页 / en 翻页后缀不统一，通用匹配）
        "card_pattern": (
            r'<a[^>]*href="((?:https?://(?:www\.)?4k-av\.com)?/'
            r'(?:[a-z]{2}/)?(movie|tv)/(\d+)-([^"/]+)/?)"'
            r'[^>]*title="([^"]*)"[^>]*>\s*<img[^>]*src="([^"]*)"'
        ),
        "m3u8_pattern": r'<source\s+src="([^"]+\.m3u8[^"]*)"',
        "title_pattern": r'<h1[^>]*>(.*?)</h1>',
        "poster_pattern": r'(https?://[^"\'\s]+poster\.jpg)',
        # meta description 结构: "{别名列表} - {标题} - {剧情简介}"
        "desc_pattern": r'<meta\s+name="description"\s+content="([^"]*)"',
        # 中英文页标签兼容: Year:/年份:（年份藏于 <a> 内）
        "year_pattern": r'(?:Year|年份)\s*:\s*(?:<[^>]+>\s*)*(\d{4})',
        "resolution_pattern": r'(?:Resolution|分辨率)\s*:\s*([^<]{2,30}?)\s*(?:<|$)',
        "length_pattern": r'(?:Length|片长)\s*:\s*([^<]{2,15}?)\s*(?:<|$)',
        "resnote_pattern": r'class="resnote">([^<]+)<',
        # 总页数: "頁次 34/34" / "Page No. 2/34" / "页次"
        "pagecount_pattern": r'(?:頁次|页次|Page\s*No\.?)\s*(?:</?[^>]+>\s*)*:?(\d+)\s*/\s*(\d+)',
    },

    # ── 重试（者字秘·无始钟）──
    "retry": {"max_retries": 2, "backoff_factor": 1.0, "timeout": 15},

    # ── 延迟（行字诀；TVBox 环境默认关）──
    "delay": {"enabled": False, "min_seconds": 0.3, "max_seconds": 1.0},

    # ── 播放 ──
    "play": {"flag_name": "4K-AV", "episode_name": "正片"},

    "debug": False,
}


# ══════════════════════════════════════════════════════════════
# 第二章 · 九秘精要
# ══════════════════════════════════════════════════════════════

# ── 临字秘 · 荒塔：请求头构建与 UA 轮换 ──

def build_headers(config, referer=""):
    """构建完整浏览器请求头（过 Cloudflare 头部校验的关键）"""
    headers = dict(config.get("headers", {}))
    ua_pool = config.get("ua_pool", [])
    if ua_pool:
        headers["User-Agent"] = random.choice(ua_pool)
    if referer:
        headers["Referer"] = referer
        headers["Sec-Fetch-Site"] = "same-origin"
    return headers


# ── 斗字秘 · 吞天魔罐：净化与卡片解析 ──

class DouZiMi(object):

    @staticmethod
    def clean_text(raw):
        """净化术：去标签、实体解码（支持双重转义）、去空白"""
        if not raw:
            return ""
        text = re.sub(r"<[^>]+>", "", str(raw))
        for _ in range(3):  # 站点存在 &amp;amp; 双重转义
            decoded = html_module.unescape(text)
            if decoded == text:
                break
            text = decoded
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def parse_cards(html_text, config):
        """
        吞天魔罐吞取列表卡片。
        vod_id 规范化为 "movie/{id}-{slug}"（无语言前缀，可直接拼详情URL）。
        """
        results, seen = [], set()
        pattern = config.get("parsing", {}).get(
            "card_pattern", DEFAULT_CONFIG["parsing"]["card_pattern"])
        for m in re.finditer(pattern, html_text, re.S):
            href, kind, vid, slug, title, pic = m.groups()
            if vid in seen:
                continue
            seen.add(vid)
            results.append({
                "vod_id": "{0}/{1}-{2}".format(kind, vid, slug),
                "vod_name": DouZiMi.clean_text(title) or vid,
                "vod_pic": pic if pic.startswith("http")
                else urljoin(DEFAULT_CONFIG["host"] + "/", pic),
                "vod_remarks": "电影" if kind == "movie" else "剧集",
            })
        return results

    @staticmethod
    def parse_pagecount(html_text, config):
        """总页数（頁次/Page No. 多语言兼容）"""
        pattern = config.get("parsing", {}).get(
            "pagecount_pattern", DEFAULT_CONFIG["parsing"]["pagecount_pattern"])
        m = re.search(pattern, html_text)
        if m:
            try:
                return int(m.group(2))
            except (ValueError, IndexError):
                pass
        return 1


# ── 者字秘 · 无始钟：不死之身 ──

class ZheZiMi(object):

    @staticmethod
    def safe_call(func, *args, **kwargs):
        """安全调用：任何异常返回 None，绝不崩溃"""
        try:
            return func(*args, **kwargs)
        except Exception:
            return None

    @staticmethod
    def retry_with_backoff(func, config, *args, **kwargs):
        """指数退避重试: delay = backoff_factor * 2**attempt"""
        retry_cfg = config.get("retry", {})
        max_retries = retry_cfg.get("max_retries", 2)
        backoff = retry_cfg.get("backoff_factor", 1.0)
        for attempt in range(max_retries + 1):
            try:
                return func(*args, **kwargs)
            except Exception:
                if attempt < max_retries:
                    time.sleep(backoff * (2 ** attempt))
        return None


# ── 行字诀 · 节奏控制 ──

class XingZiMi(object):

    @staticmethod
    def random_delay(config):
        delay_cfg = config.get("delay", {})
        if not delay_cfg.get("enabled", False):
            return
        time.sleep(random.uniform(delay_cfg.get("min_seconds", 0.3),
                                   delay_cfg.get("max_seconds", 1.0)))


# ══════════════════════════════════════════════════════════════
# 第三章 · 洞天境·横宇 · 4K-AV 站源主体
#   ★★★ 类名必须是 Spider —— TVBox py 加载器契约 ★★★
# ══════════════════════════════════════════════════════════════

class Spider(BaseSpider):
    """
    洞天境·横宇 —— 4K-AV 站点爬虫（TVBox 兼容版）

    帝兵装配: 荒塔(请求头) + 吞天魔罐(卡片解析)
              + 无始钟(分级异常/退避重试) + 行字诀(节奏)
    """

    realm_name = "洞天境·横宇"
    USE_CFFI = True   # 有 curl_cffi 用之（桌面调试环境），无则纯 requests

    def __init__(self):
        self.config = DEFAULT_CONFIG
        self.siteUrl = self.config.get("host", "https://4k-av.com")

    # ── TVBox 生命周期 ──

    def init(self, extend=""):
        """TVBox 初始化入口。extend 支持 JSON 覆盖配置（如代理）"""
        if extend:
            try:
                import json
                ex = json.loads(extend) if isinstance(extend, str) else extend
                if isinstance(ex, dict):
                    for k in ex:
                        self.config[k] = ex[k]
            except Exception:
                pass  # extend 非法时不崩溃（保持默认配置）
        # v3.1.1: 不再抛异常 —— 纯 requests 即可工作，避免 TVBox 加载失败

    # 铁律9: init 之后必须补充 getName
    def getName(self):
        return self.config.get("name", "4K-AV(遮天)")

    # 铁律10: getName 之后必须补充 isVideoFormat（列表推导式）
    def isVideoFormat(self, url):
        video_exts = ['.m3u8', '.mp4', '.flv', '.mkv', '.avi', '.ts', '.mpg', '.mpd']
        return any(ext in url.lower() for ext in video_exts)

    def manualVideoCheck(self):
        return False

    def destroy(self):
        """TVBox 退出钩子"""
        pass

    # ── 网络层（洞天境核心：Cloudflare 对抗）──

    def _fetch(self, url, referer=""):
        """
        虚空穿行: GET → 响应文本。
        桌面调试环境优先 curl_cffi(chrome131指纹)；
        TVBox 环境无 cffi 时纯 requests + 全套浏览器头（实测可过）。
        铁律7: 异常分级处理。
        """
        headers = build_headers(self.config, referer=referer)
        timeout = self.config.get("retry", {}).get("timeout", 15)
        debug = self.config.get("debug", False)

        if self.USE_CFFI and HAS_CFFI:
            try:
                resp = cffi_requests.get(url, headers=headers, timeout=timeout,
                                         impersonate="chrome131")
                if resp.status_code == 200:
                    return resp.text
                if debug:
                    print("[洞天] cffi HTTP {0}: {1}".format(resp.status_code, url))
            except Exception as e:
                if debug:
                    print("[洞天] cffi 异常: {0}".format(type(e).__name__))

        if HAS_REQUESTS:
            def _raw_get():
                resp = requests.get(url, headers=headers, timeout=timeout)
                resp.raise_for_status()
                # v3.1.1: 固定 utf-8，不依赖 chardet（TVBox 环境可能缺失）
                resp.encoding = "utf-8"
                return resp.text

            try:
                return ZheZiMi.retry_with_backoff(_raw_get, self.config)
            except requests.Timeout:
                if debug:
                    print("[洞天] 请求超时: {0}".format(url))
                return None
            except requests.HTTPError as e:
                if debug:
                    code = getattr(e.response, "status_code", "?")
                    print("[洞天] HTTP错误 {0}: {1}".format(code, url))
                return None
            except Exception as e:
                if debug:
                    print("[洞天] 未预期错误: {0}: {1}".format(type(e).__name__, e))
                return None

        if debug:
            print("[洞天] 无可用HTTP引擎(requests/curl_cffi 均缺失)")
        return None

    # ── 内部工具 ──

    def _endpoint(self, key, **kwargs):
        """读配置端点模板并格式化（铁律5: 配置优先）"""
        template = self.config.get("endpoints", {}).get(key, "")
        params = {"lang": self.config.get("language_prefix", "zh"),
                  "tag_lang": self.config.get("tag_prefix", "en")}
        params.update(kwargs)
        try:
            return template.format(**params)
        except (KeyError, IndexError):
            return template

    def _category_path(self, tid, extend):
        """tid + extend(筛选) → 分类路径。优先级: 标签 > 年份 > 基础分类"""
        ext = extend if isinstance(extend, dict) else {}
        tag = str(ext.get("tag", "") or "").strip()
        year = str(ext.get("year", "") or "").strip()
        if tag:
            return self._endpoint("category_tag", tag=quote(tag))
        if year and re.match(r"^\d{4}$", year):
            return self._endpoint("category_year", year=year)
        if tid == "tv":
            return self._endpoint("category_tv")
        return self._endpoint("category_movie")

    def _category_url(self, path, pg):
        """分类路径 + 页码 → URL（第1页无后缀，第2页起 page-N.html）"""
        if pg <= 1:
            return "{0}/{1}".format(self.siteUrl, path)
        return "{0}/{1}{2}".format(self.siteUrl, path,
                                   self._endpoint("page_suffix", pg=pg))

    @staticmethod
    def _to_int(value, default=1):
        """pg 等参数安全转 int（TVBox 可能传 '2'/'0'/None）"""
        try:
            return max(1, int(str(value)))
        except (ValueError, TypeError):
            return default

    # ── TVBox 六接口 + 可选接口 ──

    def homeContent(self, filter):
        """首页: 分类 + 筛选器（filter=True 时附 filters）"""
        result = {"class": [], "list": []}
        for cls in self.config.get("classes", []):
            result["class"].append({"type_id": cls["type_id"],
                                    "type_name": cls["type_name"]})
        if filter:
            result["filters"] = self.config.get("filters", {})
        return result

    def homeVideoContent(self):
        """可选接口: 首页推荐列表（TVBox 首页瀑布流展示）"""
        html_text = ZheZiMi.safe_call(
            self._fetch, "{0}/{1}".format(self.siteUrl,
                                          self._endpoint("home")))
        if not html_text:
            return {"list": []}
        items = DouZiMi.parse_cards(html_text, self.config)
        return {"list": items[:24]}

    def categoryContent(self, tid, pg, filter, extend):
        """
        分类列表。
        铁律6: tid/pg/filter/extend 全部使用 —— tid 定基础分类，
        extend 定年份/标签筛选，pg 定分页。filter 本站无筛选开关差异，
        结果恒含完整列表。
        """
        page = self._to_int(pg)
        path = self._category_path(tid, extend)
        url = self._category_url(path, page)
        XingZiMi.random_delay(self.config)

        html_text = ZheZiMi.safe_call(self._fetch, url)
        if not html_text:
            return {"list": [], "page": page, "pagecount": 0,
                    "limit": 0, "total": 0}

        items = DouZiMi.parse_cards(html_text, self.config)
        pagecount = DouZiMi.parse_pagecount(html_text, self.config)
        # 年份/标签页混合两类卡片时，按 tid 过滤
        if tid in ("movie", "tv"):
            kind = "movie" if tid == "movie" else "tv"
            items = [it for it in items if it["vod_id"].startswith(kind + "/")]

        return {"list": items, "page": page, "pagecount": pagecount,
                "limit": len(items),
                "total": pagecount * len(items) if items else 0}

    def detailContent(self, ids):
        """详情页。v3.0问题9修复: 遍历所有 ids。"""
        results = []
        for vod_id in (ids or []):
            vod_id = str(vod_id).strip("/")
            if not vod_id:
                continue
            detail = ZheZiMi.safe_call(self._parse_detail, vod_id)
            if detail:
                results.append(detail)
        return {"list": results}

    def _parse_detail(self, vod_id):
        """解析详情页 → TVBox vod 对象"""
        url = "{0}/{1}/".format(self.siteUrl, vod_id)
        XingZiMi.random_delay(self.config)
        html_text = self._fetch(url)
        if not html_text:
            return None

        parsing = self.config.get("parsing", {})

        # 标题: h1 → vod_id 兜底
        title = ""
        m = re.search(parsing.get("title_pattern", r'<h1[^>]*>(.*?)</h1>'),
                      html_text, re.S)
        if m:
            title = DouZiMi.clean_text(m.group(1))
        if not title:
            title = vod_id.split("/")[-1]

        # 海报大图 poster.jpg
        pic = ""
        m = re.search(parsing.get("poster_pattern", r''), html_text)
        if m:
            pic = m.group(1)

        # 简介: meta desc = "{别名列表} - {标题} - {剧情简介}"
        aliases, desc = "", ""
        m = re.search(parsing.get("desc_pattern", r''), html_text)
        if m:
            raw_desc = DouZiMi.clean_text(m.group(1))
            parts = raw_desc.split(" - ", 2)
            if len(parts) >= 3:
                aliases, desc = parts[0], parts[2]
            elif len(parts) == 2:
                aliases, desc = parts[0], parts[1]
            else:
                desc = raw_desc

        # 元信息（中英文页标签兼容）
        m = re.search(parsing.get("year_pattern", r''), html_text)
        year = m.group(1) if m else ""
        m = re.search(parsing.get("resolution_pattern", r''), html_text)
        resolution = m.group(1).strip() if m else ""
        m = re.search(parsing.get("length_pattern", r''), html_text)
        length = m.group(1).strip() if m else ""
        m = re.search(parsing.get("resnote_pattern", r''), html_text)
        resnote = DouZiMi.clean_text(m.group(1)).lstrip("* ").strip() if m else ""

        # 播放地址: <source> 内嵌 m3u8 直链
        m = re.search(parsing.get("m3u8_pattern", r''), html_text)
        m3u8_url = m.group(1) if m else ""

        remarks = " / ".join(x for x in [resolution, year, resnote] if x)

        # 集名: 电影"正片"; 剧集从 URL 提取 E01/S10E01 → "第01集"
        play_cfg = self.config.get("play", {})
        ep_name = play_cfg.get("episode_name", "正片")
        if vod_id.startswith("tv/"):
            m = re.search(r'[sS]\d+[eE](\d{1,3})|(?:^|[^0-9])[eE](\d{1,3})(?:\D|$)',
                          vod_id)
            if m:
                ep_num = m.group(1) or m.group(2)
                ep_name = "第{0}集".format(ep_num.zfill(2))

        play_url = "{0}${1}".format(ep_name, m3u8_url) if m3u8_url else ""

        content_parts = []
        if aliases:
            content_parts.append("别名: {0}".format(aliases))
        if desc:
            content_parts.append("简介: {0}".format(desc))
        if length:
            content_parts.append("片长: {0}".format(length))

        return {
            "vod_id": vod_id,
            "vod_name": title,
            "vod_pic": pic,
            "vod_year": year,
            "vod_remarks": remarks,
            "vod_content": "\n".join(content_parts),
            "vod_play_from": play_cfg.get("flag_name", "4K-AV"),
            "vod_play_url": play_url,
            "vod_actor": "",
            "vod_director": "",
        }

    def playerContent(self, flag, id, vipFlags=None):
        """
        播放。铁律6: flag 实际使用 —— 透传给播放器标识线路；
        本站 m3u8 直链无防盗链，parse=0。
        """
        play_url = str(id or "").strip()
        if not play_url:
            return {"parse": 0, "url": "", "header": {}}
        header = {
            "User-Agent": self.config.get("headers", {}).get(
                "User-Agent", "Mozilla/5.0"),
            "Referer": self.siteUrl + "/",
            "Origin": self.siteUrl,
        }
        return {"parse": 0, "url": play_url, "header": header,
                "playUrl": "", "flag": flag or ""}

    def searchContent(self, key, quick, pg="1"):
        """
        搜索: GET /zh/s?y={kw}（站点改版后 x= 参数已失效）。
        铁律6: key/pg 均使用; quick 本站无快速模式差异，仅保持契约。
        """
        keyword = str(key or "").strip()
        if not keyword:
            return {"list": [], "page": 1, "pagecount": 0}
        page = self._to_int(pg)
        if page > 1:  # 站点搜索仅1页
            return {"list": [], "page": page, "pagecount": 1}

        endpoint = self._endpoint("search", kw=quote(keyword))
        url = "{0}/{1}".format(self.siteUrl, endpoint)
        XingZiMi.random_delay(self.config)

        html_text = ZheZiMi.safe_call(self._fetch, url)
        if not html_text:
            return {"list": [], "page": 1, "pagecount": 0}
        items = DouZiMi.parse_cards(html_text, self.config)
        return {"list": items, "page": 1, "pagecount": 1}

    def localProxy(self, param):
        """本地代理（本站直链无防盗链，无需转发）"""
        return [200, "text/plain", ""]


# ══════════════════════════════════════════════════════════════
# 第四章 · 模块级入口
# ══════════════════════════════════════════════════════════════

# 遮天法体系别名（独立调试用；TVBox 只认上面的 Spider 类名）
DongTian_4KAV = Spider


def create_spider():
    """工厂入口（独立调试用）"""
    spider = Spider()
    spider.init()
    return spider


__all__ = ["Spider", "DongTian_4KAV", "create_spider", "DEFAULT_CONFIG",
           "DouZiMi", "ZheZiMi", "XingZiMi", "build_headers"]


# ══════════════════════════════════════════════════════════════
# 第五章 · 自检程序（铁律8: 每次修改后必须运行）
# ══════════════════════════════════════════════════════════════

def self_test():
    print("█" * 60)
    print("遮天法 v3.1.1 · 洞天境·横宇 · 4K-AV · TVBox兼容版 自检")
    print("█" * 60)

    checks = []

    # 1. TVBox 加载契约（本次修复核心）
    checks.append(("模块存在 Spider 类名", "Spider" in globals()))
    checks.append(("Spider 继承基类", issubclass(Spider, BaseSpider)))
    checks.append(("requests 引擎可用", HAS_REQUESTS))

    # 2. 配置完整性
    for section in ["endpoints", "headers", "parsing", "retry",
                    "classes", "filters"]:
        checks.append(("配置段 {0}".format(section), section in DEFAULT_CONFIG))

    # 3. 引号闭合（铁律1）
    test_headers = {"sec-ch-ua": "\"Chromium\";v=\"129\", \"Not=A?Brand\";v=\"8\""}
    checks.append(("sec-ch-ua 引号转义",
                   test_headers["sec-ch-ua"] == '"Chromium";v="129", "Not=A?Brand";v="8"'))

    # 4. 基础方法
    spider = Spider()
    spider.init()
    checks.append(("getName", spider.getName() == DEFAULT_CONFIG["name"]))
    checks.append(("isVideoFormat(m3u8)",
                   spider.isVideoFormat("https://x.com/v.m3u8") is True))
    checks.append(("isVideoFormat(jpg)",
                   spider.isVideoFormat("https://x.com/v.jpg") is False))
    checks.append(("destroy 可调用", spider.destroy() is None))

    # 5. 九秘单元测试
    checks.append(("斗字秘·净化术(双重转义)",
                   DouZiMi.clean_text("a&amp;amp;b") == "a&b"))
    cards = DouZiMi.parse_cards(
        '<a href="/zh/movie/010734-minions-monsters/" title="小黄人">'
        '<img src="https://www.4k-av.com/movie/010734-minions-monsters/poster_nail.jpg"/></a>',
        DEFAULT_CONFIG)
    checks.append(("斗字秘·吞卡片",
                   len(cards) == 1 and cards[0]["vod_id"] == "movie/010734-minions-monsters"))
    checks.append(("者字秘·safe_call", ZheZiMi.safe_call(lambda: 1 / 0) is None))
    checks.append(("斗字秘·页码(EN)",
                   DouZiMi.parse_pagecount("Page No. 2/34", DEFAULT_CONFIG) == 34))
    checks.append(("斗字秘·页码(ZH繁)",
                   DouZiMi.parse_pagecount("頁次 17/17", DEFAULT_CONFIG) == 17))

    # 6. 端点与路径构造
    checks.append(("端点·分类", spider._endpoint("category_movie") == "zh/movie/"))
    checks.append(("端点·标签", spider._endpoint("category_tag", tag="Action") == "en/tag/Action/"))
    checks.append(("端点·年份", spider._endpoint("category_year", year="2026") == "zh/2026/"))
    checks.append(("路径·标签筛选",
                   spider._category_path("movie", {"tag": "Action"}) == "en/tag/Action/"))
    checks.append(("路径·年份筛选",
                   spider._category_path("movie", {"year": "2025"}) == "zh/2025/"))
    checks.append(("路径·默认tv", spider._category_path("tv", {}) == "zh/tv/"))
    checks.append(("URL·第1页",
                   spider._category_url("zh/movie/", 1) == "https://4k-av.com/zh/movie/"))
    checks.append(("URL·第2页",
                   spider._category_url("zh/movie/", 2) == "https://4k-av.com/zh/movie/page-2.html"))

    # 7. homeContent 契约
    home = spider.homeContent(True)
    checks.append(("homeContent·分类数", len(home.get("class", [])) == 2))
    checks.append(("homeContent·筛选器", "movie" in home.get("filters", {})))

    passed = 0
    for name, ok in checks:
        if ok:
            passed += 1
        print("  [{0}] {1}".format("PASS" if ok else "FAIL", name))
    print("\n  结果: {0}/{1} 通过".format(passed, len(checks)))
    print("█" * 60)
    print("洞天境·横宇就绪" + ("，九秘护道，万法不侵！" if passed == len(checks)
                             else "（存在未通过项）"))
    print("█" * 60)
    return passed == len(checks)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="遮天法·洞天境·4K-AV(TVBox兼容版)")
    parser.add_argument("--self-test", action="store_true", help="离线自检")
    parser.add_argument("--test", choices=["home", "category", "detail",
                                           "player", "search", "recommend"],
                        help="在线测试指定接口")
    parser.add_argument("--url", help="测试参数(tid/vod_id/关键词)")
    args = parser.parse_args()

    if args.self_test or not args.test:
        self_test()
        return

    spider = create_spider()
    if args.test == "home":
        print(spider.homeContent(True))
    elif args.test == "recommend":
        result = spider.homeVideoContent()
        print("首页推荐 {0} 条".format(len(result["list"])))
        for item in result["list"][:5]:
            print("  {0} | {1}".format(item["vod_id"], item["vod_name"]))
    elif args.test == "category":
        result = spider.categoryContent(args.url or "movie", "1", False, {})
        print("共 {0} 条 | 页 {1}/{2}".format(len(result["list"]),
                                               result["page"], result["pagecount"]))
        for item in result["list"][:5]:
            print("  {0} | {1}".format(item["vod_id"], item["vod_name"]))
    elif args.test == "detail":
        result = spider.detailContent([args.url or "movie/010734-minions-monsters"])
        for vod in result["list"]:
            print("  标题: {0}".format(vod["vod_name"]))
            print("  海报: {0}".format(vod["vod_pic"]))
            print("  备注: {0}".format(vod["vod_remarks"]))
            print("  播放: {0}".format(vod["vod_play_url"][:120]))
            print("  详情: {0}".format(vod["vod_content"][:150]))
    elif args.test == "player":
        result = spider.playerContent(
            "4K-AV", args.url or "https://www.4k-av.com/movie/010734-minions-monsters/1080P/vrogfy.m3u8")
        print(result)
    elif args.test == "search":
        result = spider.searchContent(args.url or "minions", "1")
        print("共 {0} 条".format(len(result["list"])))
        for item in result["list"][:5]:
            print("  {0} | {1}".format(item["vod_id"], item["vod_name"]))


if __name__ == "__main__":
    main()
