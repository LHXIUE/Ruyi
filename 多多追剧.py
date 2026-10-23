#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
═══════════════════════════════════════════════════════════════
  遮天法 v3.1 · 终极融合版
  九秘归一 · 万法归宗 · 八境圆满 · 大帝路由
═══════════════════════════════════════════════════════════════

  【融合来源】
  - v3.0框架: 九秘独立类 + 配置中心 + 逆字秘
  - 布布爬虫: Protobuf编解码 + WASM签名逆向
  - 通用模板v2.0: CONFIG驱动 + TVBox六接口 + 代理服务器
  - 九秘生成器: 知识库 + 特征分析 + 治疗术引擎
  - 2.0说明文档: 八境架构 + 路由引擎 + 日志统计

  【核心特性】
  ✓ 九秘独立模块化 (BingZiMi/DouZiMi/.../NiZiMi)
  ✓ DEFAULT_CONFIG配置中心 (20+配置段)
  ✓ 30项特征扫描 + RealmAutoRouter自动路由
  ✓ 八境功法完整实现 (轮海→红尘仙 + 洞天境)
  ✓ ZheTianLogger结构化日志 + RequestStats量化统计
  ✓ 线程安全Session + UA池随机轮换
  ✓ 本地代理服务器 (含XOR解密 + HEAD/OPTIONS支持)
  ✓ m3u8广告清洗 (修正MEDIA-SEQUENCE逻辑)
  ✓ Protobuf编解码 + SHA-256签名重建 (逆字秘)
  ✓ 零依赖优雅降级 (缺失库不崩溃)
  ✓ __main__自检 + 命令行参数支持

  【用法】
  python 遮天法v3.1.py --self-test
  python 遮天法v3.1.py https://example.com
  python 遮天法v3.1.py https://example.com --realm=洞天
  python 遮天法v3.1.py https://example.com --test=home

  【版本】v3.1.0 | 【作者】叶凡 | 【许可】开源
"""

import sys
import re
import json
import time
import base64
import hashlib
import html as html_module
import os
import threading
import random
import argparse
from urllib.parse import quote, unquote, urljoin, urlparse
from typing import Dict, List, Optional, Tuple, Any, Callable
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

# ── 基类导入（兼容TVBox环境）──
try:
    from base.spider import Spider as BaseSpider
except ImportError:
    class BaseSpider:
        """TVBox环境缺失时的兜底基类"""
        pass

# ── HTTP请求库（优雅降级）──
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    requests = None

# ── 加密库（优雅降级）──
try:
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import unpad, pad
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

try:
    from curl_cffi import requests as cffi_requests
    HAS_CFFI = True
except ImportError:
    HAS_CFFI = False
    cffi_requests = None


# ═══════════════════════════════════════════════════════════════
#  第一章：大帝配置中心（CONFIG）
# ═══════════════════════════════════════════════════════════════

DEFAULT_CONFIG = {
    # ── 基础信息 ──
    "name": "遮天·通用爬虫",
    "host": "https://example.com",
    "api_base": "/api/",

    # ── 域名备份（临字秘·多域轮询）──
    "domain_candidates": [],

    # ── API端点映射 ──
    "endpoints": {
        "home": "index/home",
        "category": "filter/vod",
        "detail": "vod/detail/{id}",
        "search": "search/index",
        "play_parse": "",
        "topic_list": "",
        "topic_detail": "",
    },

    # ── 分页配置 ──
    "pagination": {
        "page_param": "page",
        "limit_param": "limit",
        "page_size": 20,
        "page_start": 1,
    },

    # ── 字段映射 ──
    "fields": {
        "vod_id": "vodId",
        "vod_name": "vodName",
        "vod_pic": "vodPic",
        "vod_remarks": "vodRemarks",
        "vod_year": "vodYear",
        "vod_area": "vodArea",
        "vod_actor": "vodActor",
        "vod_director": "vodDirector",
        "vod_type": "vodClass",
        "vod_score": "vodScore",
        "vod_content": "vodContent",
        "vod_play_from": "vodPlayFrom",
        "vod_play_url": "vodPlayUrl",
        "vod_play_source": "vodPlaySource",
        "vod_preview": "vodPreview",
    },

    # ── 响应结构映射 ──
    "response": {
        "code_field": "code",
        "code_success": 200,
        "data_field": "data",
        "list_field": "list",
        "total_field": "total",
        "totalpages_field": "totalPages",
        "topic_list_field": "data",
        "topic_vods_field": "relatedVods",
    },

    # ── 兵字秘·加密配置 ──
    "encryption": {
        "enabled": False,
        "type": "aes-128-cbc",
        "key": "",
        "iv": "",
        "iv_prefix": True,
        "input_format": "hex",
        "output_format": "json",
    },

    # ── 斗字秘·解析配置 ──
    "parsing": {
        "list_selector": "div.video-item",
        "title_selector": "a.title",
        "pic_selector": "img",
        "link_selector": "a",
        "remark_selector": "span.remark",
        "use_bs4": True,
        "fallback_regex": True,
    },

    # ── 阵字秘·代理配置 ──
    "proxy": {
        "enabled": True,
        "port": 9979,
        "fallback_ports": [9980, 9981, 9982, 9983, 9984, 9985, 9986, 9987, 9988, 9989],
        "xor_decrypt": False,
        "xor_key": 18,
        "xor_prefix_bytes": 4096,
        "proxy_domains": [],
        "proxy_extensions": [".txt"],
        "referer": "",
    },

    # ── 皆字秘·m3u8清洗 ──
    "m3u8_clean": {
        "enabled": True,
        "ad_keywords": ["ad", "ads", "advert", "preroll", "片头", "广告", "/gg/",
                        "banner", "promo", "casino", "博彩", "充值", "slot", "sponsor"],
        "min_duration": 1.2,
        "skip_first_n": 12,
    },

    # ── 者字秘·重试与容错 ──
    "retry": {
        "max_retries": 3,
        "backoff_factor": 1.0,
        "timeout": 15,
        "allow_downgrade": True,
    },

    # ── 行字秘·延迟控制 ──
    "delay": {
        "enabled": False,
        "min_seconds": 0.5,
        "max_seconds": 2.0,
    },

    # ── 前字秘·播放提取（13层策略，配置化）──
    "player_extract": {
        "13_layers": [
            {"name": "player_aaaa变量", "pattern": r"""var\s+(player_\w+)\s*=\s*(\{.*?\});"""},
            {"name": "video标签src", "pattern": r"""<video[^>]*src=['"]([^'"]+)['"]"""},
            {"name": "source标签src", "pattern": r"""<source[^>]*src=['"]([^'"]+)['"]"""},
            {"name": "iframe标签src", "pattern": r"""<iframe[^>]*src=['"]([^'"]+)['"]"""},
            {"name": "m3u8直链", "pattern": r"""(https?://[^\s"<>]+\.m3u8)"""},
            {"name": "mp4直链", "pattern": r"""(https?://[^\s"<>]+\.mp4)"""},
            {"name": "JS变量url", "pattern": r"""var\s+(?:video_)?url\s*=\s*['"]([^'"]+)['"]"""},
            {"name": "Base64解码", "pattern": r"""base64Decode\(['"]([A-Za-z0-9+/=]+)['"]"""},
            {"name": "location跳转", "pattern": r"""location\.href\s*=\s*['"]([^'"]+)['"]"""},
            {"name": "meta refresh", "pattern": r"""<meta[^>]+refresh[^>]+url=([^'"]+)"""},
            {"name": "playurl变量", "pattern": r"""playurl\s*=\s*['"]([^'"]+)['"]"""},
            {"name": "file变量", "pattern": r"""file\s*=\s*['"]([^'"]+)['"]"""},
            {"name": "url参数", "pattern": r"""['"]url['"]\s*:\s*['"]([^'"]+)['"]"""},
        ]
    },

    # ── 逆字秘·Protobuf配置（新增，融合布布爬虫）──
    "protobuf": {
        "enabled": False,
        "endpoint": "",
        "request_fields": {},
        "response_fields": {},
        "decode_finger": "",
        "decode_id": "",
        "decode_sk": "",
    },

    # ── 逆字秘·签名配置 ──
    "signature": {
        "enabled": False,
        "type": "md5",
        "secret_key": "",
        "params_order": "alphabetical",
        "fixed_order": [],
        "exclude_params": ["sign", "signature"],
        "custom_function": "",
    },

    # ── 备用分类（临字秘·fallback）──
    "fallback_classes": [
        {"type_id": "1", "type_name": "电影"},
        {"type_id": "2", "type_name": "剧集"},
        {"type_id": "3", "type_name": "动漫"},
        {"type_id": "4", "type_name": "综艺"},
        {"type_id": "5", "type_name": "纪录片"},
    ],

    # ── 特殊分类ID ──
    "special_classes": {
        "latest": "",
        "recommend": "",
        "hot": "",
    },

    # ── 请求头 ──
    "headers": {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "sec-ch-ua": "\"Chromium\";v=\"129\", \"Not=A?Brand\";v=\"8\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "Upgrade-Insecure-Requests": "1",
    },

    # ── UA池（行字秘·随机轮换）──
    "ua_pool": [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1",
        "Mozilla/5.0 (iPad; CPU OS 17_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1",
    ],

    # ── 洞天境·现代站点配置（新增）──
    "洞天": {
        "htmx": {
            "headers": {"HX-Request": "true", "HX-Target": "main", "HX-Current-URL": "{siteUrl}/"},
            "content_api_use_htmx": True,
        },
        "endpoints": {
            "discover": "/discover/{type}",
            "search": "/api/htmx/search?kw={kw}",
            "play": "/play/{src}/{vod}?douban_id=",
        },
        "regex": {
            "episode_list": r"episodeList\s*=\s*(\[.*?\]);",
            "init_player": r"initPlayer\(\s*\'[^\']*\'\s*,\s*\'([^\']+)\'\s*,",
        }
    },

    # ── 调试 ──
    "debug": False,
}


# ═══════════════════════════════════════════════════════════════
#  第二章：九秘核心能力库
#  九种能力独立实现为可复用模块
# ═══════════════════════════════════════════════════════════════

# ── 2.1 临字秘 · 基础架构 ──

def build_headers(host: str, extra: Dict = None, config: Dict = None) -> Dict:
    """临字秘·构建完整请求头"""
    cfg = config or DEFAULT_CONFIG
    headers = dict(cfg.get("headers", {}))
    headers["Referer"] = host + "/"
    headers["Origin"] = host
    if extra:
        headers.update(extra)
    return headers


def random_ua(config: Dict = None) -> str:
    """临字秘·随机UA"""
    cfg = config or DEFAULT_CONFIG
    pool = cfg.get("ua_pool", DEFAULT_CONFIG["ua_pool"])
    return random.choice(pool) if pool else DEFAULT_CONFIG["ua_pool"][0]


def discover_domain(candidates: List[str], test_path: str = "", config: Dict = None) -> str:
    """临字秘·多域名轮询自适应"""
    cfg = config or DEFAULT_CONFIG
    if not candidates:
        candidates = cfg.get("domain_candidates", [])
    if not candidates:
        return cfg.get("host", "")
    if not HAS_REQUESTS:
        return candidates[0].rstrip("/")
    headers = build_headers(candidates[0], config=cfg)
    for domain in candidates:
        try:
            url = domain.rstrip("/") + test_path
            r = requests.get(url, headers=headers, timeout=8, allow_redirects=True)
            if r.status_code == 200:
                return domain.rstrip("/")
        except:
            continue
    return candidates[0].rstrip("/")


def fallback_classes(config: Dict = None) -> List[Dict]:
    """临字秘·备用分类"""
    cfg = config or DEFAULT_CONFIG
    return cfg.get("fallback_classes", DEFAULT_CONFIG["fallback_classes"])


# ── 2.2 兵字秘 · 万法解密 ──

class BingZiMi:
    """兵字秘·万法解密引擎（诛仙四剑）"""

    @staticmethod
    def aes_cbc_decrypt(encrypted_data: str, key: str, iv: str = None,
                        iv_prefix: bool = True, input_format: str = "hex") -> Optional[str]:
        """诛仙剑·AES-CBC解密"""
        if not HAS_CRYPTO:
            print("[兵字秘] 警告: 未安装pycryptodome，AES解密不可用")
            return None
        try:
            if input_format == "hex":
                data = bytes.fromhex(encrypted_data)
            elif input_format == "base64":
                data = base64.b64decode(encrypted_data)
            else:
                data = encrypted_data.encode("utf-8") if isinstance(encrypted_data, str) else encrypted_data

            if len(data) < 16:
                return None

            key_bytes = key.encode("utf-8") if isinstance(key, str) else key
            # 统一使用MD5补齐密钥长度到16字节（AES-128）
            if len(key_bytes) not in (16, 24, 32):
                key_bytes = hashlib.md5(key_bytes).digest()

            if iv_prefix:
                iv_bytes, ciphertext = data[:16], data[16:]
            elif iv:
                iv_bytes = iv.encode("utf-8") if isinstance(iv, str) else iv
                ciphertext = data
            else:
                iv_bytes, ciphertext = data[:16], data[16:]

            cipher = AES.new(key_bytes[:16], AES.MODE_CBC, iv_bytes[:16])
            decrypted = unpad(cipher.decrypt(ciphertext), AES.block_size)
            return decrypted.decode("utf-8")
        except Exception as e:
            if DEFAULT_CONFIG.get("debug"):
                print(f"[兵字秘] AES解密失败: {e}")
            return None

    @staticmethod
    def base64_decode(data: str) -> Optional[str]:
        """诛仙剑·Base64解码"""
        try:
            return base64.b64decode(data).decode("utf-8")
        except:
            try:
                return base64.urlsafe_b64decode(data).decode("utf-8")
            except:
                return None

    @staticmethod
    def xor_decrypt(data: bytes, key: int = 18, prefix_bytes: int = 4096) -> bytes:
        """诛仙剑·XOR解密"""
        if not data:
            return data
        result = bytearray(data)
        for i in range(min(prefix_bytes, len(result))):
            result[i] ^= key
        return bytes(result)

    @staticmethod
    def url_decode(data: str) -> str:
        """诛仙剑·URL解码"""
        try:
            return unquote(data)
        except:
            return data

    @staticmethod
    def multi_layer_decrypt(data: str, methods: List[str]) -> Optional[str]:
        """诛仙剑·多层组合解密"""
        result = data
        for method in methods:
            if not result:
                break
            if method == "base64":
                result = BingZiMi.base64_decode(result)
            elif method == "url":
                result = BingZiMi.url_decode(result)
            elif method == "hex":
                try:
                    result = bytes.fromhex(result).decode("utf-8")
                except:
                    pass
        return result


# ── 2.3 斗字秘 · 战斗解析 ──

class DouZiMi:
    """斗字秘·战斗解析引擎（吞天魔罐）"""

    @staticmethod
    def clean_text(raw: Any) -> str:
        """斗字秘·净化术（清洗任意文本，不限于标题）"""
        if not raw:
            return "未知标题"
        text = str(raw)
        text = re.sub(r"<[^>]+>", "", text)
        text = html_module.unescape(text)
        text = re.sub(r"\s+", " ", text).strip()
        return text or "未知标题"

    # 兼容旧名称
    clean_title = clean_text

    @staticmethod
    def fix_pic(url: str, host: str = "", proxy_func: Callable = None) -> str:
        """斗字秘·修图术"""
        if not url:
            return ""
        if url.startswith("//"):
            url = "https:" + url
        elif url.startswith("/") and host:
            url = host.rstrip("/") + url
        elif not url.startswith("http") and host:
            url = host.rstrip("/") + "/" + url.lstrip("/")
        if proxy_func:
            return proxy_func(url)
        return url

    @staticmethod
    def extract_by_regex(html: str, patterns: List[Dict[str, str]]) -> Optional[str]:
        """斗字秘·正则多级提取"""
        for pat in patterns:
            pattern = pat.get("pattern", "")
            group = pat.get("group", 1)
            try:
                m = re.search(pattern, html, re.S | re.I)
                if m:
                    return m.group(group).strip()
            except:
                continue
        return None

    @staticmethod
    def parse_video_list(html: str, config: Dict = None) -> List[Dict]:
        """斗字秘·七十二变解析列表"""
        cfg = config or DEFAULT_CONFIG
        videos = []
        if not html:
            return videos

        # 尝试BS4
        if cfg.get("parsing", {}).get("use_bs4", True) and HAS_BS4:
            try:
                soup = BeautifulSoup(html, "html.parser")
                selector = cfg["parsing"].get("list_selector", "div.video-item")
                items = soup.select(selector)
                for item in items:
                    title_sel = cfg["parsing"].get("title_selector", "a.title")
                    title_tag = item.select_one(title_sel)
                    pic_sel = cfg["parsing"].get("pic_selector", "img")
                    img_tag = item.select_one(pic_sel)
                    link_sel = cfg["parsing"].get("link_selector", "a")
                    link_tag = item.select_one(link_sel)
                    remark_sel = cfg["parsing"].get("remark_selector", "span.remark")
                    remark_tag = item.select_one(remark_sel)

                    vid = link_tag.get("href", "") if link_tag else ""
                    # 更通用的ID提取
                    vid_match = re.search(r"/([^/]+?)(?:\.html?)?$", vid)
                    vid = vid_match.group(1) if vid_match else vid
                    title = DouZiMi.clean_text(title_tag.text) if title_tag else ""
                    pic = img_tag.get("src") or img_tag.get("data-src") or img_tag.get("data-original") or ""
                    remark = remark_tag.text.strip() if remark_tag else ""

                    if vid and title:
                        videos.append({
                            "vod_id": str(vid),
                            "vod_name": title,
                            "vod_pic": pic,
                            "vod_remarks": remark,
                        })
                if videos:
                    return videos
            except Exception as e:
                if cfg.get("debug"):
                    print(f"[斗字秘] BS4解析失败: {e}")

        # 回退到正则（斗字秘·三层回退）
        patterns = [
            r'<a[^>]*href="[^"]*\/([^\/]+?)\.html?"[^>]*>.*?<img[^>]*src="([^"]+)"[^>]*>.*?<h[1-6][^>]*>(.*?)<\/h[1-6]>',
            r'<div[^>]*class="video-item"[^>]*>.*?<a[^>]*href="[^"]*\/([^\/]+?)\.html?"[^>]*>(.*?)<\/a>.*?<img[^>]*src="([^"]+)"',
            r'<a[^>]*href="[^"]*\/([^\/]+?)\.html?"[^>]*>\s*<img[^>]*src="([^"]+)"[^>]*>\s*<span[^>]*>(.*?)<\/span>',
        ]
        for pattern in patterns:
            matches = re.findall(pattern, html, re.S)
            if matches:
                for m in matches:
                    vid, pic, title = (m[0], m[1], m[2]) if len(m) == 3 else (m[0], "", m[1])
                    if vid and title:
                        videos.append({
                            "vod_id": str(vid),
                            "vod_name": DouZiMi.clean_text(title),
                            "vod_pic": pic,
                            "vod_remarks": "",
                        })
                if videos:
                    return videos

        return videos


# ── 2.4 者字秘 · 不死之身 ──

class ZheZiMi:
    """者字秘·不死之身（无始钟）"""

    @staticmethod
    def safe_call(func: Callable, *args, **kwargs) -> Any:
        """者字秘·不死身：安全调用任何函数"""
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if DEFAULT_CONFIG.get("debug"):
                func_name = getattr(func, "__name__", repr(func))
                print(f"[者字秘] {func_name}治愈: {e}")
            return None

    @staticmethod
    def safe_get(d: Dict, key: str, default: Any = "") -> Any:
        """者字秘·安全取值（支持点号路径）"""
        if not isinstance(d, dict):
            return default
        if "." in key:
            parts = key.split(".")
            current = d
            for part in parts:
                if isinstance(current, dict):
                    current = current.get(part)
                else:
                    return default
            return current if current is not None else default
        return d.get(key, default)

    @staticmethod
    def retry_with_backoff(func: Callable, max_retries: int = 3,
                           backoff_factor: float = 1.0, *args, **kwargs) -> Any:
        """者字秘·指数退避重试"""
        for attempt in range(max_retries):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                delay = backoff_factor * (2 ** attempt)
                time.sleep(delay + random.uniform(0, 1))
        return None


# ── 2.5 皆字秘 · m3u8广告清洗 ──

class JieZiMi:
    """皆字秘·净世咒（仙珍图）"""

    @staticmethod
    def clean_m3u8(text: str, base_url: str = "", config: Dict = None) -> str:
        """皆字秘·清洗m3u8广告分片（修正MEDIA-SEQUENCE逻辑）"""
        cfg = config or DEFAULT_CONFIG
        clean_cfg = cfg.get("m3u8_clean", DEFAULT_CONFIG["m3u8_clean"])
        if not clean_cfg.get("enabled", True):
            return text

        try:
            lines = text.splitlines()
            if not lines or lines[0].strip() != "#EXTM3U":
                return text

            header_lines = []
            segments = []
            current_seg = {"tags": [], "uri": "", "dur": 0}
            in_seg = False
            original_sequence = 0

            for line in lines:
                s = line.strip()
                if not s:
                    continue
                if s.startswith("#EXTINF:"):
                    in_seg = True
                    dur_match = re.search(r"#EXTINF:([0-9.]+)", s)
                    current_seg["dur"] = float(dur_match.group(1)) if dur_match else 3.0
                    current_seg["tags"].append(line)
                elif s.startswith("#EXT-X-MEDIA-SEQUENCE:"):
                    seq_match = re.search(r"#EXT-X-MEDIA-SEQUENCE:(\d+)", s)
                    if seq_match:
                        original_sequence = int(seq_match.group(1))
                elif s.startswith("#"):
                    if in_seg:
                        current_seg["tags"].append(line)
                    else:
                        header_lines.append(line)
                else:
                    if in_seg:
                        current_seg["uri"] = s
                        segments.append(current_seg)
                        current_seg = {"tags": [], "uri": "", "dur": 0}
                        in_seg = False
                    else:
                        header_lines.append(line)

            if not segments:
                return text

            # 统计主路径
            stat = {}
            for seg in segments:
                key = JieZiMi._segment_key(seg["uri"], base_url)
                stat[key] = stat.get(key, 0.0) + seg["dur"]
            main_key = max(stat.items(), key=lambda x: x[1])[0] if stat else ("", "")

            # 过滤广告
            ad_keywords = clean_cfg.get("ad_keywords", DEFAULT_CONFIG["m3u8_clean"]["ad_keywords"])
            min_dur = clean_cfg.get("min_duration", 1.2)
            skip_n = clean_cfg.get("skip_first_n", 12)

            cleaned_segs = []
            removed = 0
            for idx, seg in enumerate(segments):
                uri = seg["uri"]
                is_ad = False
                if any(k in uri.lower() for k in ad_keywords):
                    is_ad = True
                if 0 < seg["dur"] <= min_dur:
                    is_ad = True
                if idx < skip_n:
                    key = JieZiMi._segment_key(uri, base_url)
                    if key != main_key:
                        is_ad = True
                if is_ad:
                    removed += 1
                    continue
                cleaned_segs.extend(seg["tags"])
                cleaned_segs.append(uri)

            # 修正：MEDIA-SEQUENCE = 原序列号 + 移除数量
            out = ["#EXTM3U"]
            out.extend([l for l in header_lines if not l.strip().startswith("#EXTM3U")])
            out.append(f"#EXT-X-MEDIA-SEQUENCE:{original_sequence + removed}")
            out.extend(cleaned_segs)
            out.append("#EXT-X-ENDLIST")
            return "\n".join(out)

        except Exception as e:
            if cfg.get("debug"):
                print(f"[皆字秘] m3u8清洗失败: {e}")
            return text

    @staticmethod
    def _segment_key(uri: str, base_url: str) -> Tuple[str, str]:
        try:
            full = urljoin(base_url, uri)
            parsed = urlparse(full)
            path = parsed.path
            parts = path.split("/")
            return parsed.netloc, "/".join(parts[:-1]) if len(parts) > 1 else parsed.netloc
        except:
            return uri, ""

    @staticmethod
    def absolutize_m3u8(text: str, base_url: str) -> str:
        """皆字秘·指路术：m3u8相对路径转绝对路径"""
        lines = []
        for line in text.splitlines():
            s = line.strip()
            if not s or s.startswith("#"):
                lines.append(line)
                continue
            lines.append(urljoin(base_url, s))
        return "\n".join(lines)


# ── 2.6 阵字秘 · 本地代理服务器 ──

class ZhenZiMi:
    """阵字秘·偷天阵（诛仙阵图）"""

    _server_instance = None
    _port = 0

    class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
        daemon_threads = True

    class ProxyHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            try:
                real_url = unquote(self.path[1:])
                if not real_url.startswith("http"):
                    self.send_response(400)
                    self.end_headers()
                    return

                config = ZhenZiMi._get_config()
                headers = {
                    "User-Agent": random_ua(config),
                    "Referer": config.get("host", ""),
                    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
                }
                r = requests.get(real_url, headers=headers, timeout=20)
                content = r.content

                proxy_cfg = config.get("proxy", {})
                if proxy_cfg.get("xor_decrypt"):
                    key = proxy_cfg.get("xor_key", 18)
                    prefix = proxy_cfg.get("xor_prefix_bytes", 4096)
                    decrypted = bytearray(content)
                    for i in range(min(prefix, len(decrypted))):
                        decrypted[i] ^= key
                    content = bytes(decrypted)

                self.send_response(200)
                ct = r.headers.get("Content-Type", "image/jpeg")
                self.send_header("Content-Type", ct)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(content)
            except Exception as e:
                self.send_response(502)
                self.end_headers()
                self.wfile.write(f"Proxy Error: {e}".encode())

        def do_HEAD(self):
            """支持HEAD请求（TVBox播放器探测用）"""
            try:
                real_url = unquote(self.path[1:])
                if not real_url.startswith("http"):
                    self.send_response(400)
                    self.end_headers()
                    return
                r = requests.head(real_url, timeout=10)
                self.send_response(r.status_code)
                for k, v in r.headers.items():
                    if k.lower() not in ("transfer-encoding", "content-encoding"):
                        self.send_header(k, v)
                self.end_headers()
            except Exception as e:
                self.send_response(502)
                self.end_headers()

        def do_OPTIONS(self):
            """支持OPTIONS请求（CORS预检）"""
            self.send_response(200)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "*")
            self.end_headers()

        def log_message(self, *args):
            pass

    @staticmethod
    def _get_config() -> Dict:
        return DEFAULT_CONFIG

    @classmethod
    def start_proxy(cls, config: Dict = None) -> int:
        """启动本地代理服务器"""
        if cls._server_instance:
            return cls._port

        cfg = config or DEFAULT_CONFIG
        proxy_cfg = cfg.get("proxy", {})
        ports = [proxy_cfg.get("port", 9979)] + proxy_cfg.get("fallback_ports", [])

        import socket
        for port in ports:
            try:
                sk = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sk.bind(("127.0.0.1", port))
                sk.close()
                server = cls.ThreadedHTTPServer(("127.0.0.1", port), cls.ProxyHandler)
                threading.Thread(target=server.serve_forever, daemon=True).start()
                cls._server_instance = server
                cls._port = port
                return port
            except:
                continue
        return 0

    @classmethod
    def proxy_url(cls, url: str) -> str:
        """生成代理URL"""
        if not cls._server_instance:
            cls.start_proxy()
        if cls._port == 0:
            return url
        return f"http://127.0.0.1:{cls._port}/{quote(url, safe='')}"


# ── 2.7 列字秘 · 虚空镜 ──

class LieZiMi:
    """列字秘·虚空镜（Referer伪装）"""

    @staticmethod
    def build_headers_with_referer(target_url: str, source_url: str = "", extra: Dict = None) -> Dict:
        """列字秘·构建带Referer伪装的请求头"""
        headers = build_headers(source_url or target_url, extra=extra)
        headers["Referer"] = source_url or target_url
        return headers

    @staticmethod
    def break_referer_lock(url: str, config: Dict = None) -> str:
        """列字秘·自动识别并穿透防盗链"""
        cfg = config or DEFAULT_CONFIG
        proxy_cfg = cfg.get("proxy", {})
        if proxy_cfg.get("enabled"):
            return ZhenZiMi.proxy_url(url)
        return url


# ── 2.8 前字秘 · 不死天刀 ──

class QianZiMi:
    """前字秘·不死天刀（13层播放提取）"""

    @staticmethod
    def extract_player_url(html: str, config: Dict = None) -> Optional[str]:
        """前字秘·十三重天眼：从播放页HTML提取视频地址"""
        cfg = config or DEFAULT_CONFIG
        layers = cfg.get("player_extract", {}).get("13_layers", [])
        if not layers:
            layers = DEFAULT_CONFIG["player_extract"]["13_layers"]

        for layer in layers:
            pattern = layer.get("pattern", "")
            if not pattern:
                continue
            try:
                m = re.search(pattern, html, re.S | re.I)
                if m:
                    url = m.group(1).strip()
                    # 还原转义的斜杠
                    url = url.replace("\\/", "/")
                    if url.startswith("http"):
                        return url
            except:
                continue
        return None


# ── 2.9 行字秘 · 行字诀 ──

class XingZiMi:
    """行字秘·行字诀（延迟控制）"""

    @staticmethod
    def random_delay(config: Dict = None):
        """行字秘·随机延迟"""
        cfg = config or DEFAULT_CONFIG
        delay_cfg = cfg.get("delay", DEFAULT_CONFIG["delay"])
        if delay_cfg.get("enabled", False):
            min_s = delay_cfg.get("min_seconds", 0.5)
            max_s = delay_cfg.get("max_seconds", 2.0)
            time.sleep(random.uniform(min_s, max_s))

    @staticmethod
    def paced_request(func: Callable, *args, **kwargs) -> Any:
        """行字秘·访问节奏控制（带jitter）"""
        XingZiMi.random_delay()
        return func(*args, **kwargs)


# ── 2.10 逆字秘 · 逆向工程（新增，融合布布爬虫）──

class NiZiMi:
    """逆字秘·逆向工程（Protobuf编解码 + SHA-256签名重建）"""

    @staticmethod
    def _varint(n: int) -> bytes:
        """Protobuf varint编码"""
        out = bytearray()
        while True:
            b = n & 0x7f
            n >>= 7
            if n:
                out.append(b | 0x80)
            else:
                out.append(b)
                return bytes(out)

    @staticmethod
    def _bytes_field(num: int, data: bytes) -> bytes:
        """Protobuf bytes字段编码"""
        return bytes([num << 3 | 2]) + NiZiMi._varint(len(data)) + data

    @staticmethod
    def _varint_field(num: int, val: int) -> bytes:
        """Protobuf varint字段编码"""
        return bytes([num << 3 | 0]) + NiZiMi._varint(val)

    @staticmethod
    def protobuf_encode(data: Dict, message_type: str = "Request") -> bytes:
        """逆字秘·Protobuf请求编码（简化版，支持常见字段类型）"""
        buf = bytearray()
        field_num = 1
        for key, value in data.items():
            if isinstance(value, bytes):
                buf += NiZiMi._bytes_field(field_num, value)
            elif isinstance(value, str):
                buf += NiZiMi._bytes_field(field_num, value.encode("utf-8"))
            elif isinstance(value, int):
                buf += NiZiMi._varint_field(field_num, value)
            field_num += 1
        return bytes(buf)

    @staticmethod
    def protobuf_decode(data: bytes, message_type: str = "Response") -> Dict:
        """逆字秘·Protobuf响应解码（支持wire type 0/2）"""
        i = 0
        fields = {}
        while i < len(data):
            tag = data[i]
            i += 1
            wt = tag & 7
            fno = tag >> 3
            if wt == 2:  # Length-delimited
                ln = 0
                sh = 0
                while i < len(data):
                    x = data[i]
                    i += 1
                    ln |= (x & 0x7f) << sh
                    if not x & 0x80:
                        break
                    sh += 7
                if i + ln <= len(data):
                    fields[fno] = data[i:i + ln]
                    i += ln
                else:
                    break
            elif wt == 0:  # Varint
                v = 0
                sh = 0
                while i < len(data):
                    x = data[i]
                    i += 1
                    v |= (x & 0x7f) << sh
                    if not x & 0x80:
                        break
                    sh += 7
                fields[fno] = v
            elif wt == 5:  # 32-bit
                if i + 4 <= len(data):
                    fields[fno] = int.from_bytes(data[i:i+4], 'little')
                    i += 4
                else:
                    break
            elif wt == 1:  # 64-bit
                if i + 8 <= len(data):
                    fields[fno] = int.from_bytes(data[i:i+8], 'little')
                    i += 8
                else:
                    break
            else:
                # 跳过未知wire type（不break，尝试继续解析）
                i += 1
        return fields

    @staticmethod
    def generate_signature(params: Dict, secret_key: str, method: str = "sha256") -> str:
        """逆字秘·SHA-256签名生成"""
        if method == "sha256":
            sign_src = "&".join(f"{k}={v}" for k, v in sorted(params.items()) if v is not None)
            sign_src += secret_key
            return hashlib.sha256(sign_src.encode("utf-8")).hexdigest().upper()
        elif method == "md5":
            return NiZiMi.generate_md5_sign(params, secret_key)
        return ""

    @staticmethod
    def generate_md5_sign(params: Dict, secret_key: str) -> str:
        """逆字秘·MD5签名生成"""
        sign_src = "&".join(f"{k}={v}" for k, v in sorted(params.items()) if v is not None)
        sign_src += secret_key
        return hashlib.md5(sign_src.encode("utf-8")).hexdigest()

    @staticmethod
    def build_decode_request(url: str, flag: str, finger: str, app_id: str, sk: str,
                             now: int = None, nonce_hex: str = None) -> bytes:
        """逆字秘·构建WASM风格解码请求（融合布布爬虫）"""
        if now is None:
            now = int(time.time() * 1000)
        if nonce_hex is None:
            nonce_hex = os.urandom(16).hex()
        sign_src = f"finger={finger}&id={app_id}&nonce={nonce_hex}&sk={sk}&time={now}&v=1"
        sign = hashlib.sha256(sign_src.encode("utf-8")).hexdigest().upper()

        buf = bytearray()
        buf += NiZiMi._bytes_field(1, url.encode("utf-8"))
        buf += NiZiMi._bytes_field(2, flag.encode("utf-8"))
        buf += NiZiMi._varint_field(3, now)
        buf += NiZiMi._bytes_field(4, nonce_hex.encode("utf-8"))
        buf += NiZiMi._bytes_field(5, sign.encode("utf-8"))
        buf += NiZiMi._bytes_field(6, app_id.encode("utf-8"))
        buf += NiZiMi._varint_field(7, 1)
        return bytes(buf)


# ═══════════════════════════════════════════════════════════════
#  第三章：基础设施（从2.0说明补充实现）
# ═══════════════════════════════════════════════════════════════

class ZheTianLogger:
    """结构化日志，按境界/模块标记"""
    LEVELS = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3}

    def __init__(self, level: str = "INFO"):
        self.level = self.LEVELS.get(level, 1)

    def debug(self, realm: str, msg: str):
        self._log("DEBUG", realm, msg)

    def info(self, realm: str, msg: str):
        self._log("INFO", realm, msg)

    def warning(self, realm: str, msg: str):
        self._log("WARNING", realm, msg)

    def error(self, realm: str, msg: str):
        self._log("ERROR", realm, msg)

    def _log(self, level: str, realm: str, msg: str):
        if self.LEVELS.get(level, 3) >= self.level:
            print(f"[{level}][{realm}] {msg}")


class RequestStats:
    """请求统计，量化成功率/耗时/降级"""

    def __init__(self):
        self.records = []
        self.lock = threading.Lock()

    def record(self, realm: str, success: bool, elapsed: float):
        with self.lock:
            self.records.append({"realm": realm, "success": success, "elapsed": elapsed})

    def snapshot(self) -> Dict:
        with self.lock:
            total = len(self.records)
            success = sum(1 for r in self.records if r["success"])
            return {
                "total": total,
                "success": success,
                "fail": total - success,
                "success_rate": f"{success / max(total, 1) * 100:.1f}%",
            }

    def report(self) -> str:
        with self.lock:
            total = len(self.records)
            success = sum(1 for r in self.records if r["success"])
            by_realm = {}
            for r in self.records:
                by_realm.setdefault(r["realm"], []).append(r)
            lines = [f"总请求: {total}, 成功: {success}, 成功率: {success / max(total, 1) * 100:.1f}%"]
            for realm, items in by_realm.items():
                s = sum(1 for i in items if i["success"])
                avg = sum(i["elapsed"] for i in items) / len(items)
                lines.append(f"  {realm}: {len(items)}次, 成功{s}次, 均耗时{avg:.2f}s")
            return "\n".join(lines)


class RealmConfig:
    """配置管理单例，支持YAML/JSON加载和热更新"""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._config = dict(DEFAULT_CONFIG)
        return cls._instance

    def load(self, path: str = None):
        if path and HAS_YAML and os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                override = yaml.safe_load(f)
                if override:
                    self._deep_merge(self._config, override)

    def _deep_merge(self, base: Dict, override: Dict):
        for k, v in override.items():
            if k in base and isinstance(base[k], dict) and isinstance(v, dict):
                self._deep_merge(base[k], v)
            else:
                base[k] = v

    def get(self, *keys, default=None):
        current = self._config
        for k in keys:
            if isinstance(current, dict) and k in current:
                current = current[k]
            else:
                return default
        return current

    def set(self, *keys, value):
        current = self._config
        for k in keys[:-1]:
            if k not in current or not isinstance(current[k], dict):
                current[k] = {}
            current = current[k]
        current[keys[-1]] = value


# ═══════════════════════════════════════════════════════════════
#  第四章：路由引擎（30项特征扫描）
# ═══════════════════════════════════════════════════════════════

class RealmAutoRouter:
    """大帝级自动路由引擎"""

    FEATURE_SCANNERS = {
        # 加密特征 (8项)
        "encrypt_aes": r"AES|aes|CryptoJS|crypto",
        "encrypt_base64_url": r"atob|btoa|base64|Base64",
        "encrypt_player_aaaa": r"player_[a-zA-Z0-9_]+\s*=\s*\{",
        "encrypt_eval": r"eval\s*\(",
        "encrypt_js_obfuscate": r"_0x[a-f0-9]+",
        "encrypt_xor": r"XOR|xor|charCodeAt|fromCharCode",
        "encrypt_token_sign": r"token=|sign=|timestamp=",
        "encrypt_crypto_js": r"CryptoJS",
        # 反爬特征 (5项)
        "anticrawl_cf": r"__cf_bm|cf-ray|challenge-platform|cdn-cgi",
        "anticrawl_captcha": r"g-recaptcha|h-captcha|captcha",
        "anticrawl_waf": r"403|access denied|waf",
        "anticrawl_referer": r"referer|Referer|防盗链",
        "anticrawl_ad_ts": r"/ad[^/]*\.ts|/gg/",
        # 混合内容特征 (5项)
        "mixed_novel": r"小说|阅读|章节|book|novel",
        "mixed_image": r"图集|写真|套图|gallery|image",
        "mixed_comic": r"漫画|manga|comic",
        "mixed_live": r"直播|stream|live",
        "mixed_music": r"音乐|音频|mp3|audio",
        # 高级特征 (4项)
        "advanced_wasm": r"\.wasm|WebAssembly|wasm",
        "advanced_iframe_nest": r"<iframe[^>]*>.*<iframe",
        "advanced_api_multi": r"/api/provide/vod",
        "advanced_dynamic_load": r"XHR|fetch|axios|ajax",
        # 现代特征 (3项)
        "modern_htmx": r"htmx\.min\.js|HX-Request|hx-get|data-hx-|hx-target|hx-swap",
        "modern_cloudflare": r"__cf_bm|cf-ray|challenge-platform|cdn-cgi|cloudflare",
        "modern_async_shell": r'id="app"|id="root"|__NEXT_DATA__|骨架屏|data-server-rendered',
        # 逆向特征 (3项)
        "reverse_protobuf": r"protobuf|\.proto|application/x-protobuf",
        "reverse_wasm": r"\.wasm|WebAssembly",
        "reverse_signature": r"sign=|sig=|signature",
        # 其他特征 (2项)
        "other_cdn": r"cdn|CDN|cloudfront|fastly",
        "other_cookie": r"cookie|Cookie|session|Session",
    }

    def __init__(self):
        self.cache = {}
        self.log = ZheTianLogger()

    def analyze(self, url: str) -> Dict:
        """分析站点特征，判定防御等级"""
        if url in self.cache:
            return self.cache[url]

        result = {
            "url": url,
            "defense_level": 0,
            "realm": "轮海",
            "features": {},
            "recommend_weapons": ["荒塔"],
            "cms_type": "未知",
            "modern": False,
        }

        if not HAS_REQUESTS:
            self.cache[url] = result
            return result

        try:
            headers = build_headers(url)
            r = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
            html = r.text[:50000]  # 只分析前50KB

            # 扫描特征
            features = {}
            for name, pattern in self.FEATURE_SCANNERS.items():
                matches = len(re.findall(pattern, html, re.IGNORECASE))
                if matches > 0:
                    features[name] = min(1.0, 0.3 + matches * 0.2)

            result["features"] = features

            # 现代站点特权判定
            modern_features = ["modern_htmx", "modern_cloudflare", "modern_async_shell"]
            if any(f in features for f in modern_features):
                result["realm"] = "洞天"
                result["defense_level"] = 4
                result["modern"] = True
                result["recommend_weapons"] = ["荒塔", "诛仙四剑", "吞天魔罐", "诛仙阵图", "虚空镜", "不死天刀"]
                self.cache[url] = result
                return result

            # 统计各类特征数量
            encrypt_count = sum(1 for f in features if f.startswith("encrypt_"))
            anticrawl_count = sum(1 for f in features if f.startswith("anticrawl_"))
            mixed_count = sum(1 for f in features if f.startswith("mixed_"))
            advanced_count = sum(1 for f in features if f.startswith("advanced_"))
            reverse_count = sum(1 for f in features if f.startswith("reverse_"))

            # 判定防御等级
            if reverse_count >= 2:
                result["defense_level"] = 4
                result["realm"] = "仙台"
                result["recommend_weapons"] = ["荒塔", "诛仙四剑", "吞天魔罐", "诛仙阵图", "虚空镜", "不死天刀", "逆字秘"]
            elif advanced_count >= 3:
                result["defense_level"] = 4
                result["realm"] = "仙台"
                result["recommend_weapons"] = ["荒塔", "诛仙四剑", "吞天魔罐", "诛仙阵图", "虚空镜", "不死天刀"]
            elif mixed_count >= 3:
                result["defense_level"] = 3
                result["realm"] = "化龙"
                result["recommend_weapons"] = ["荒塔", "诛仙四剑", "吞天魔罐", "诛仙阵图"]
            elif encrypt_count >= 3:
                result["defense_level"] = 2
                result["realm"] = "四极"
                result["recommend_weapons"] = ["荒塔", "诛仙四剑", "吞天魔罐"]
            elif anticrawl_count >= 2:
                result["defense_level"] = 1
                result["realm"] = "道宫"
                result["recommend_weapons"] = ["荒塔", "诛仙四剑"]
            else:
                result["defense_level"] = 0
                result["realm"] = "轮海"
                result["recommend_weapons"] = ["荒塔"]

            # Cloudflare检测追加
            if "anticrawl_cf" in features:
                result["recommend_weapons"].extend(["无始钟", "仙珍图"])

        except Exception as e:
            self.log.error("路由", f"分析失败: {e}")

        self.cache[url] = result
        return result

    def route(self, url: str):
        """分析并自动实例化最佳境界"""
        analysis = self.analyze(url)
        realm = analysis["realm"]
        return self._instantiate(realm, url)

    def _instantiate(self, realm: str, url: str):
        """根据境界名称实例化对应类"""
        realm_map = {
            "轮海": LunHai_BiAn,
            "道宫": DaoGong_ShenZang,
            "四极": SiJi_TongTian,
            "化龙": HuaLong_JiuBian,
            "仙台": XianTai_DiJiuTian,
            "洞天": DongTian_HengYu,
            "红尘仙": HongChenXian,
        }
        cls = realm_map.get(realm, LunHai_BiAn)
        instance = cls()
        instance.siteUrl = url
        instance.config.set("host", value=url)
        return instance

    def report(self) -> str:
        """输出已缓存的站点分析报告"""
        lines = ["=" * 60, "RealmAutoRouter 分析报告", "=" * 60]
        for url, analysis in self.cache.items():
            lines.append(f"\n站点: {url}")
            lines.append(f"  防御等级: {analysis['defense_level']}")
            lines.append(f"  推荐境界: {analysis['realm']}")
            lines.append(f"  推荐帝兵: {', '.join(analysis['recommend_weapons'])}")
            lines.append(f"  命中特征: {', '.join(analysis['features'].keys())}")
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
#  第五章：八境功法（融合所有实战代码）
# ═══════════════════════════════════════════════════════════════

class JieJingBase(BaseSpider):
    """抽象基类，统一接口契约"""
    realm_name = "基境"
    realm_level = 0
    defense_level = 0

    def __init__(self):
        super().__init__()
        self.config = RealmConfig()
        self.log = ZheTianLogger()
        self.stats = RequestStats()
        self.siteUrl = ""
        self._local = threading.local()

    def _get_session(self):
        if not hasattr(self._local, "s"):
            self._local.s = requests.Session()
            self._local.s.headers.update(self._build_headers())
        return self._local.s

    def _build_headers(self, extra: Dict = None) -> Dict:
        h = dict(self.config.get("headers") or {})
        h["Referer"] = self.siteUrl + "/" if self.siteUrl else ""
        h["Origin"] = self.siteUrl
        if extra:
            h.update(extra)
        return h

    def _random_ua(self) -> str:
        pool = self.config.get("ua_pool") or DEFAULT_CONFIG["ua_pool"]
        return random.choice(pool) if pool else DEFAULT_CONFIG["ua_pool"][0]

    def _get_json(self, path: str, params: Dict = None, headers: Dict = None) -> Optional[Dict]:
        """安全GET请求，自动解析JSON并校验code"""
        if not HAS_REQUESTS:
            return None
        try:
            url = self.siteUrl.rstrip("/") + path
            h = self._build_headers(headers)
            r = self._get_session().get(url, params=params, headers=h, timeout=15)
            if r.status_code != 200:
                return None
            data = r.json()
            code_field = self.config.get("response", "code_field", default="code")
            code_success = self.config.get("response", "code_success", default=200)
            if data.get(code_field) != code_success:
                return None
            return data
        except Exception as e:
            if self.config.get("debug"):
                self.log.error(self.realm_name, f"请求失败: {e}")
            return None

    def _post_json(self, path: str, data: bytes = None, headers: Dict = None) -> Optional[Dict]:
        """安全POST请求"""
        if not HAS_REQUESTS:
            return None
        try:
            url = self.siteUrl.rstrip("/") + path
            h = self._build_headers(headers)
            r = self._get_session().post(url, data=data, headers=h, timeout=20)
            if r.status_code not in (200, 201):
                return None
            return r.json()
        except Exception as e:
            if self.config.get("debug"):
                self.log.error(self.realm_name, f"POST失败: {e}")
            return None

    def init(self, extend=""):
        pass

    # ==================== 修复：补充 getName 方法 ====================
    def getName(self) -> str:
        return self.config.get("name", default="遮天爬虫")

    # ==================== 修复：补充 isVideoFormat 方法 ====================
    def isVideoFormat(self, url: str) -> bool:
        video_exts = ['.m3u8', '.mp4', '.flv', '.mkv', '.avi', '.ts', '.mpg']
        return any(ext in url.lower() for ext in video_exts)


    def manualVideoCheck(self) -> bool:
        return False

    def homeVideoContent(self):
        return self.homeContent(filter=True)

    def localProxy(self, param: Dict) -> List:
        try:
            url = unquote(param.get("url", ""))
            kind = param.get("kind", "")
            r = self._get_session().get(url, headers={"Referer": self.siteUrl}, timeout=30)
            if kind == "hls":
                text = r.text
                text = JieZiMi.absolutize_m3u8(text, url)
                text = JieZiMi.clean_m3u8(text, url, config=self.config._config)
                return [200, "application/vnd.apple.mpegurl", text.encode()]
            if kind == "img":
                return [200, r.headers.get("Content-Type", "image/jpeg"), r.content]
            return [200, r.headers.get("Content-Type"), r.content]
        except Exception as e:
            return [500, "text/plain", f"Proxy Error: {e}".encode()]


class LunHai_BiAn(JieJingBase):
    """轮海·彼岸——五接口圆满（防御等级0）"""
    realm_name = "轮海·彼岸"
    realm_level = 1
    defense_level = 0

    def homeContent(self, filter: bool = False) -> Dict:
        start = time.time()
        try:
            endpoints = self.config.get("endpoints", default={})
            home_path = endpoints.get("home", "index/home")
            api_base = self.config.get("api_base", default="/api/")
            d = self._get_json(api_base + home_path)
            if not d:
                return {"class": fallback_classes(self.config._config)}
            data = d.get("data") or {}
            cats = []
            for c in data.get("categories") or []:
                cats.append({"type_id": str(c.get("type_id")), "type_name": c.get("type_name")})
            if not cats:
                cats = fallback_classes(self.config._config)
            self.stats.record(self.realm_name, True, time.time() - start)
            return {"class": cats}
        except Exception as e:
            self.stats.record(self.realm_name, False, time.time() - start)
            self.log.error(self.realm_name, f"homeContent: {e}")
            return {"class": fallback_classes(self.config._config)}

    def categoryContent(self, tid: str, pg: str, filter: bool, extend: Dict) -> Dict:
        start = time.time()
        try:
            params = {
                "page": int(pg or 1),
                "limit": self.config.get("pagination", "page_size", default=20),
                "type": tid,
            }
            if extend and isinstance(extend, dict):
                params.update(extend)
            endpoints = self.config.get("endpoints", default={})
            category_path = endpoints.get("category", "filter/vod")
            api_base = self.config.get("api_base", default="/api/")
            d = self._get_json(api_base + category_path, params=params)
            if not d:
                return {"list": [], "page": int(pg or 1), "pagecount": 1, "limit": 0, "total": 0}
            items = d.get("data") or []
            videos = []
            for it in items:
                videos.append({
                    "vod_id": str(it.get("vod_id", "")),
                    "vod_name": it.get("vod_name", ""),
                    "vod_pic": DouZiMi.fix_pic(it.get("vod_pic", ""), self.siteUrl),
                    "vod_remarks": it.get("vod_remarks", ""),
                })
            page = int(pg or 1)
            has_more = len(items) >= self.config.get("pagination", "page_size", default=20)
            self.stats.record(self.realm_name, True, time.time() - start)
            return {
                "list": videos,
                "page": page,
                "pagecount": page + 1 if has_more else page,
                "limit": self.config.get("pagination", "page_size", default=20),
                "total": page * 20 if has_more else (page - 1) * 20 + len(items)
            }
        except Exception as e:
            self.stats.record(self.realm_name, False, time.time() - start)
            self.log.error(self.realm_name, f"categoryContent: {e}")
            return {"list": [], "page": int(pg or 1), "pagecount": 1, "limit": 0, "total": 0}

    def detailContent(self, ids: List[str]) -> Dict:
        start = time.time()
        try:
            results = []
            for vod_id in (ids or ["1"]):
                if not vod_id:
                    continue
                endpoints = self.config.get("endpoints", default={})
                detail_pattern = endpoints.get("detail", "vod/detail/{id}")
                api_base = self.config.get("api_base", default="/api/")
                detail_path = detail_pattern.replace("{id}", str(vod_id))
                d = self._get_json(api_base + detail_path, params={"vod_id": vod_id})
                if not d:
                    continue
                items = d.get("data") or []
                if items:
                    item = items[0]
                    detail = {
                        "vod_id": str(item.get("vod_id", "")),
                        "vod_name": item.get("vod_name", ""),
                        "vod_pic": DouZiMi.fix_pic(item.get("vod_pic", ""), self.siteUrl),
                        "vod_remarks": item.get("vod_remarks", ""),
                        "vod_content": DouZiMi.clean_text(item.get("vod_content", "")),
                        "vod_year": item.get("vod_year", ""),
                        "vod_actor": item.get("vod_actor", ""),
                        "vod_director": item.get("vod_director", ""),
                        "vod_area": item.get("vod_area", ""),
                        "vod_play_from": item.get("vod_play_from", ""),
                        "vod_play_url": item.get("vod_play_url", ""),
                    }
                    results.append(detail)
            self.stats.record(self.realm_name, True, time.time() - start)
            return {"list": results}
        except Exception as e:
            self.stats.record(self.realm_name, False, time.time() - start)
            self.log.error(self.realm_name, f"detailContent: {e}")
            return {"list": []}

    def playerContent(self, flag: str, id: str, vipFlags: str = None) -> Dict:
        start = time.time()
        try:
            if not id:
                return {"parse": 0, "url": "", "header": {}}
            header = {"Referer": self.siteUrl, "User-Agent": self._random_ua()}
            pb_cfg = self.config.get("protobuf", default={})
            if pb_cfg.get("enabled") and id and hasattr(self, "decode_url"):
                decoded = self.decode_url(id, flag)
                if decoded:
                    id = decoded
            self.stats.record(self.realm_name, True, time.time() - start)
            return {"parse": 0, "url": id, "header": header}
        except Exception as e:
            self.stats.record(self.realm_name, False, time.time() - start)
            self.log.error(self.realm_name, f"playerContent: {e}")
            return {"parse": 0, "url": id, "header": {}}

    def searchContent(self, key: str, quick: str, pg: str = "1") -> Dict:
        start = time.time()
        try:
            endpoints = self.config.get("endpoints", default={})
            search_path = endpoints.get("search", "search/index")
            api_base = self.config.get("api_base", default="/api/")
            d = self._get_json(api_base + search_path, params={"wd": key, "page": pg})
            if not d:
                return {"list": [], "page": int(pg), "pagecount": 1}
            items = d.get("data") or []
            videos = []
            for it in items:
                videos.append({
                    "vod_id": str(it.get("vod_id", "")),
                    "vod_name": it.get("vod_name", ""),
                    "vod_pic": DouZiMi.fix_pic(it.get("vod_pic", ""), self.siteUrl),
                    "vod_remarks": it.get("vod_remarks", ""),
                })
            self.stats.record(self.realm_name, True, time.time() - start)
            return {"list": videos, "page": int(pg), "pagecount": 1}
        except Exception as e:
            self.stats.record(self.realm_name, False, time.time() - start)
            self.log.error(self.realm_name, f"searchContent: {e}")
            return {"list": [], "page": int(pg), "pagecount": 1}


class DaoGong_ShenZang(LunHai_BiAn):
    """道宫·五脏神藏——代理防御（防御等级1）"""
    realm_name = "道宫·五脏神藏"
    realm_level = 2
    defense_level = 1

    def __init__(self):
        super().__init__()
        self.proxy_port = 0
        if self.config.get("proxy", "enabled", default=True):
            self.proxy_port = ZhenZiMi.start_proxy(self.config._config)

    def playerContent(self, flag: str, id: str, vipFlags: str = None) -> Dict:
        result = super().playerContent(flag, id, vipFlags)
        if self.proxy_port and ".m3u8" in id:
            # 清洗m3u8广告
            try:
                r = self._get_session().get(id, headers=result.get("header", {}), timeout=30)
                cleaned = JieZiMi.clean_m3u8(r.text, id, config=self.config._config)
                cleaned = JieZiMi.absolutize_m3u8(cleaned, id)
                # 返回代理URL
                proxy_url = ZhenZiMi.proxy_url(id)
                result["url"] = proxy_url
            except:
                pass
        return result


class SiJi_TongTian(DaoGong_ShenZang):
    """四极·四肢通天——加密破解（防御等级2）"""
    realm_name = "四极·四肢通天"
    realm_level = 3
    defense_level = 2

    def decode_url(self, code: str, flag: str) -> str:
        """四极·解密播放地址（融合布布爬虫的Protobuf解码）"""
        pb_cfg = self.config.get("protobuf") or {}
        if not pb_cfg.get("enabled"):
            return code

        try:
            body = NiZiMi.build_decode_request(
                code, flag,
                pb_cfg.get("decode_finger", ""),
                pb_cfg.get("decode_id", ""),
                pb_cfg.get("decode_sk", "")
            )
            endpoint = pb_cfg.get("endpoint", "/api.php/web/decode/url")
            r = self._get_session().post(
                self.siteUrl.rstrip("/") + endpoint,
                data=body,
                headers={"Content-Type": "application/x-protobuf"},
                timeout=20
            )
            fields = NiZiMi.protobuf_decode(r.content)
            if fields.get(1) != 1:
                return ""
            for k, v in fields.items():
                if isinstance(v, bytes) and b"http" in v:
                    idx = v.index(b"http")
                    m3u8 = v[idx:].decode("utf-8", "replace").rstrip("\x00")
                    return m3u8
            return ""
        except Exception as e:
            self.log.error(self.realm_name, f"decode_url: {e}")
            return ""

    def playerContent(self, flag: str, id: str, vipFlags: str = None) -> Dict:
        result = super().playerContent(flag, id, vipFlags)
        pb_cfg = self.config.get("protobuf") or {}
        if pb_cfg.get("enabled") and id:
            decoded = self.decode_url(id, flag)
            if decoded:
                result["url"] = decoded
        return result


class HuaLong_JiuBian(SiJi_TongTian):
    """化龙·九变登仙——九种协议（防御等级3）"""
    realm_name = "化龙·九变登仙"
    realm_level = 4
    defense_level = 3

    CONTENT_TYPES = ["video", "novel", "image", "comic", "audio", "live", "variety", "anime", "mix"]

    def detect_content_type(self, url: str) -> str:
        """化龙·九变：自动识别内容类型"""
        url_lower = url.lower()
        if any(x in url_lower for x in ["novel", "book", "chapter", "阅读"]):
            return "novel"
        elif any(x in url_lower for x in ["image", "pic", "gallery", "写真", "图集"]):
            return "image"
        elif any(x in url_lower for x in ["comic", "manga", "漫画"]):
            return "comic"
        elif any(x in url_lower for x in ["audio", "music", "mp3", "音乐"]):
            return "audio"
        elif any(x in url_lower for x in ["live", "stream", "直播"]):
            return "live"
        elif any(x in url_lower for x in ["variety", "综艺"]):
            return "variety"
        elif any(x in url_lower for x in ["anime", "动漫", "cartoon"]):
            return "anime"
        return "video"


class XianTai_DiJiuTian(HuaLong_JiuBian):
    """仙台·大帝——自动路由（防御等级4）"""
    realm_name = "仙台·大帝"
    realm_level = 5
    defense_level = 4

    def __init__(self):
        super().__init__()
        self.router = RealmAutoRouter()
        self.sub_spider = None

    def _ensure_sub_spider(self):
        if self.sub_spider is None:
            analysis = self.router.analyze(self.siteUrl)
            realm = analysis.get("realm", "轮海")
            if realm == "仙台":
                realm = "化龙"
            self.sub_spider = self.router._instantiate(realm, self.siteUrl)
        return self.sub_spider

    def homeContent(self, filter: bool = False) -> Dict:
        return self._ensure_sub_spider().homeContent(filter)

    def categoryContent(self, tid: str, pg: str, filter: bool, extend: Dict) -> Dict:
        return self._ensure_sub_spider().categoryContent(tid, pg, filter, extend)

    def detailContent(self, ids: List[str]) -> Dict:
        return self._ensure_sub_spider().detailContent(ids)

    def playerContent(self, flag: str, id: str, vipFlags: str = None) -> Dict:
        return self._ensure_sub_spider().playerContent(flag, id, vipFlags)

    def searchContent(self, key: str, quick: str, pg: str = "1") -> Dict:
        return self._ensure_sub_spider().searchContent(key, quick, pg)


class DongTian_HengYu(JieJingBase):
    """洞天境·横宇——现代HTMX/CloudFlare抗压（防御等级4）"""
    realm_name = "洞天境·横宇"
    realm_level = 7
    defense_level = 4
    USE_CFFI = False

    DISCOVER_TYPES = {
        "movie": "电影",
        "tv": "电视剧",
        "show": "综艺",
        "cartoon": "动漫",
    }

    def __init__(self):
        super().__init__()
        if self.USE_CFFI and not HAS_CFFI:
            raise RuntimeError("USE_CFFI=True 但 curl_cffi 未安装，请执行: pip install curl_cffi")

    def _fetch(self, url: str, headers: Dict = None, timeout: int = 10,
               htmx: bool = False, hx_target: str = "main", hx_current: str = "") -> Any:
        """洞天·fetch：带HTMX伪头部的请求"""
        h = self._build_headers(headers)
        if htmx:
            dt_cfg = self.config.get("洞天") or {}
            htmx_headers = dt_cfg.get("htmx", {}).get("headers", {})
            h.update(htmx_headers)
            h["HX-Target"] = hx_target
            h["HX-Current-URL"] = hx_current or f"{self.siteUrl}/"

        if self.USE_CFFI and HAS_CFFI:
            return cffi_requests.get(url, headers=h, timeout=timeout, impersonate="chrome131")
        return self._get_session().get(url, headers=h, timeout=timeout)

    def homeContent(self, filter: bool = False) -> Dict:
        classes = []
        for type_id, type_name in self.DISCOVER_TYPES.items():
            classes.append({"type_id": type_id, "type_name": type_name})
        return {"class": classes}

    def categoryContent(self, tid: str, pg: str, filter: bool, extend: Dict) -> Dict:
        start = time.time()
        try:
            dt_cfg = self.config.get("洞天") or {}
            endpoints = dt_cfg.get("endpoints", {})
            discover_pattern = endpoints.get("discover", "/discover/{type}")
            path = discover_pattern.replace("{type}", tid)

            url = self.siteUrl.rstrip("/") + path
            r = self._fetch(url, htmx=True)

            if not r.text or len(r.text) < 200:
                # fallback到查询参数式
                url = f"{self.siteUrl}/discover?type={tid}"
                r = self._fetch(url, htmx=False)

            videos = DouZiMi.parse_video_list(r.text, config=self.config._config)
            self.stats.record(self.realm_name, True, time.time() - start)
            return {"list": videos, "page": int(pg), "pagecount": 9999}
        except Exception as e:
            self.stats.record(self.realm_name, False, time.time() - start)
            self.log.error(self.realm_name, f"categoryContent: {e}")
            return {"list": [], "page": int(pg), "pagecount": 1}

    def detailContent(self, ids: List[str]) -> Dict:
        start = time.time()
        try:
            vod_id = ids[0] if ids else ""
            dt_cfg = self.config.get("洞天") or {}
            endpoints = dt_cfg.get("endpoints", {})
            play_pattern = endpoints.get("play", "/play/{src}/{vod}")
            path = play_pattern.replace("{vod}", vod_id).replace("{src}", "1")

            url = self.siteUrl.rstrip("/") + path
            # 播放页必须走普通GET（禁HX头）
            r = self._fetch(url, htmx=False)
            html = r.text

            # 从episodeList提取剧集
            regex_cfg = dt_cfg.get("regex", {})
            ep_pattern = regex_cfg.get("episode_list", "episodeList\\s*=\\s*(\\[.*?\\]);")
            episodes = []
            m = re.search(ep_pattern, html, re.S)
            if m:
                try:
                    ep_list = json.loads(m.group(1))
                    for ep in ep_list:
                        episodes.append(f"{ep.get('title','集')}${ep.get('url','')}")
                except:
                    pass

            if not episodes:
                episodes = [f"正片${vod_id}"]

            play_url = "#".join(episodes)
            self.stats.record(self.realm_name, True, time.time() - start)
            return {
                "list": [{
                    "vod_id": str(vod_id),
                    "vod_name": "",
                    "vod_pic": "",
                    "vod_play_from": "播放",
                    "vod_play_url": play_url,
                }]
            }
        except Exception as e:
            self.stats.record(self.realm_name, False, time.time() - start)
            self.log.error(self.realm_name, f"detailContent: {e}")
            return {"list": []}

    def playerContent(self, flag: str, id: str, vipFlags: str = None) -> Dict:
        start = time.time()
        try:
            if not id:
                return {"parse": 0, "url": "", "header": {}}

            # 播放页普通GET
            r = self._fetch(id, htmx=False)
            html = r.text

            # 从initPlayer提取m3u8
            dt_cfg = self.config.get("洞天") or {}
            regex_cfg = dt_cfg.get("regex", {})
            init_pattern = regex_cfg.get("init_player", "initPlayer\\(\\s*\\'[^\\']*\\'\\s*,\\s*\\'([^\\']+)\\'\\s*,")
            m = re.search(init_pattern, html, re.S)
            if m:
                m3u8 = m.group(1).replace("\\/", "/")
                header = {"Referer": self.siteUrl, "User-Agent": self._random_ua()}
                self.stats.record(self.realm_name, True, time.time() - start)
                return {"parse": 0, "url": m3u8, "header": header}

            # 兜底：直接找.m3u8
            m = re.search(r'(https?://[^\s"<>]+\.m3u8)', html)
            if m:
                header = {"Referer": self.siteUrl, "User-Agent": self._random_ua()}
                self.stats.record(self.realm_name, True, time.time() - start)
                return {"parse": 0, "url": m.group(1), "header": header}

            self.stats.record(self.realm_name, False, time.time() - start)
            return {"parse": 0, "url": id, "header": {}}
        except Exception as e:
            self.stats.record(self.realm_name, False, time.time() - start)
            self.log.error(self.realm_name, f"playerContent: {e}")
            return {"parse": 0, "url": id, "header": {}}

    def searchContent(self, key: str, quick: str, pg: str = "1") -> Dict:
        start = time.time()
        try:
            dt_cfg = self.config.get("洞天") or {}
            endpoints = dt_cfg.get("endpoints", {})
            search_pattern = endpoints.get("search", "/api/htmx/search?kw={kw}")
            path = search_pattern.replace("{kw}", quote(key))

            url = self.siteUrl.rstrip("/") + path
            r = self._fetch(url, htmx=True)
            videos = DouZiMi.parse_video_list(r.text, config=self.config._config)
            self.stats.record(self.realm_name, True, time.time() - start)
            return {"list": videos, "page": int(pg), "pagecount": 1}
        except Exception as e:
            self.stats.record(self.realm_name, False, time.time() - start)
            self.log.error(self.realm_name, f"searchContent: {e}")
            return {"list": [], "page": int(pg), "pagecount": 1}


class HongChenXian(XianTai_DiJiuTian):
    """红尘仙·万法归一——TVBox标准入口"""
    realm_name = "红尘仙"
    realm_level = 6

    def __init__(self):
        super().__init__()


# ═══════════════════════════════════════════════════════════════
#  第六章：入口与自检
# ═══════════════════════════════════════════════════════════════

def create_spider_for(url: str) -> BaseSpider:
    """一键自动路由：分析URL -> 判定境界 -> 实例化Spider"""
    router = RealmAutoRouter()
    return router.route(url)


# ── __all__ 声明 ──
__all__ = [
    # 入口
    "create_spider_for",
    # 配置
    "DEFAULT_CONFIG", "RealmConfig",
    # 基础设施
    "ZheTianLogger", "RequestStats",
    # 九秘
    "BingZiMi", "DouZiMi", "ZheZiMi", "JieZiMi", "ZhenZiMi",
    "LieZiMi", "QianZiMi", "XingZiMi", "NiZiMi",
    # 路由
    "RealmAutoRouter",
    # 八境
    "JieJingBase", "LunHai_BiAn", "DaoGong_ShenZang", "SiJi_TongTian",
    "HuaLong_JiuBian", "XianTai_DiJiuTian", "DongTian_HengYu", "HongChenXian",
]


# ═══════════════════════════════════════════════════════════════
#  第七章：主控程序（自检 + 命令行）
# ═══════════════════════════════════════════════════════════════

def self_test():
    """遮天法自检程序"""
    print("█" * 60)
    print("█" + " " * 18 + "遮天法 v3.1 自检程序" + " " * 19 + "█")
    print("█" * 60)
    print(f"Python版本: {sys.version}")
    print(f"requests: {'OK' if HAS_REQUESTS else 'MISSING'}")
    print(f"pycryptodome: {'OK' if HAS_CRYPTO else 'MISSING'}")
    print(f"beautifulsoup4: {'OK' if HAS_BS4 else 'MISSING'}")
    print(f"pyyaml: {'OK' if HAS_YAML else 'MISSING'}")
    print(f"curl_cffi: {'OK' if HAS_CFFI else 'MISSING'}")

    print("\n九秘模块检查:")
    secrets = ["BingZiMi", "DouZiMi", "ZheZiMi", "JieZiMi", "ZhenZiMi",
               "LieZiMi", "QianZiMi", "XingZiMi", "NiZiMi"]
    for name in secrets:
        status = "OK" if name in globals() else "MISSING"
        print(f"  {name}: {status}")

    print("\n基础设施检查:")
    infra = ["ZheTianLogger", "RequestStats", "RealmConfig", "RealmAutoRouter"]
    for name in infra:
        status = "OK" if name in globals() else "MISSING"
        print(f"  {name}: {status}")

    print("\n境界类检查:")
    realms = ["JieJingBase", "LunHai_BiAn", "DaoGong_ShenZang", "SiJi_TongTian",
              "HuaLong_JiuBian", "XianTai_DiJiuTian", "DongTian_HengYu", "HongChenXian"]
    for name in realms:
        status = "OK" if name in globals() else "MISSING"
        print(f"  {name}: {status}")

    print("\n功能测试:")
    # 测试临字秘
    try:
        ua = random_ua()
        print(f"  random_ua: {ua[:30]}... OK")
    except Exception as e:
        print(f"  random_ua: FAILED - {e}")

    # 测试兵字秘
    try:
        result = BingZiMi.base64_decode("aGVsbG8=")
        print(f"  BingZiMi.base64_decode: {result} OK")
    except Exception as e:
        print(f"  BingZiMi.base64_decode: FAILED - {e}")

    # 测试斗字秘
    try:
        result = DouZiMi.clean_text("<b>测试</b>&nbsp;标题")
        print(f"  DouZiMi.clean_text: {result} OK")
    except Exception as e:
        print(f"  DouZiMi.clean_text: FAILED - {e}")

    # 测试者字秘
    try:
        result = ZheZiMi.safe_call(lambda: 1 / 0)
        print(f"  ZheZiMi.safe_call: {result} OK")
    except Exception as e:
        print(f"  ZheZiMi.safe_call: FAILED - {e}")

    # 测试逆字秘
    try:
        data = {"url": "test", "flag": "hd"}
        encoded = NiZiMi.protobuf_encode(data)
        print(f"  NiZiMi.protobuf_encode: {len(encoded)} bytes OK")
    except Exception as e:
        print(f"  NiZiMi.protobuf_encode: FAILED - {e}")

    # 测试配置中心
    try:
        cfg = RealmConfig()
        val = cfg.get("debug", default=False)
        print(f"  RealmConfig.get: {val} OK")
    except Exception as e:
        print(f"  RealmConfig.get: FAILED - {e}")

    # 测试日志
    try:
        log = ZheTianLogger()
        log.info("自检", "日志系统正常")
        print("  ZheTianLogger: OK")
    except Exception as e:
        print(f"  ZheTianLogger: FAILED - {e}")

    # 测试统计
    try:
        stats = RequestStats()
        stats.record("测试", True, 0.5)
        print(f"  RequestStats: {stats.snapshot()} OK")
    except Exception as e:
        print(f"  RequestStats: FAILED - {e}")

    print("\n" + "█" * 60)
    print("遮天法 v3.1 就绪，九秘护道，万法不侵！")
    print("█" * 60)


def main():
    parser = argparse.ArgumentParser(description="遮天法 v3.1 - TVBox爬虫框架")
    parser.add_argument("url", nargs="?", help="目标站点URL")
    parser.add_argument("--self-test", action="store_true", help="运行自检程序")
    parser.add_argument("--realm", choices=["轮海", "道宫", "四极", "化龙", "仙台", "洞天", "红尘仙"],
                        help="手动指定境界")
    parser.add_argument("--test", choices=["home", "category", "detail", "player", "search"],
                        help="测试指定接口")
    parser.add_argument("--config", help="加载外部配置文件")
    args = parser.parse_args()

    if args.self_test or (not args.url and not args.config):
        self_test()
        return

    if args.config:
        config = RealmConfig()
        config.load(args.config)
        print(f"已加载配置: {args.config}")

    if args.url:
        print(f"\n分析站点: {args.url}")
        router = RealmAutoRouter()
        analysis = router.analyze(args.url)
        print(f"防御等级: {analysis['defense_level']}")
        print(f"推荐境界: {analysis['realm']}")
        print(f"推荐帝兵: {', '.join(analysis['recommend_weapons'])}")
        print(f"命中特征: {', '.join(analysis['features'].keys()) or '无'}")

        if args.realm:
            spider = router._instantiate(args.realm, args.url)
            print(f"\n手动指定境界: {args.realm}")
        else:
            spider = router.route(args.url)
            print(f"\n自动路由到: {spider.realm_name}")

        if args.test:
            print(f"\n测试接口: {args.test}")
            if args.test == "home":
                result = spider.homeContent()
                print(json.dumps(result, ensure_ascii=False, indent=2)[:500])
            elif args.test == "category":
                result = spider.categoryContent("1", "1", False, {})
                print(json.dumps(result, ensure_ascii=False, indent=2)[:500])
            elif args.test == "detail":
                result = spider.detailContent(["1"])
                print(json.dumps(result, ensure_ascii=False, indent=2)[:500])
            elif args.test == "player":
                result = spider.playerContent("HD", "test", "")
                print(json.dumps(result, ensure_ascii=False, indent=2)[:500])
            elif args.test == "search":
                result = spider.searchContent("测试", "1")
                print(json.dumps(result, ensure_ascii=False, indent=2)[:500])

        print("\n统计报告:")
        print(spider.stats.report())


# ════════════════════════════════════════════════════════════════
#  多多追剧 (duoduozhuiju.com) —— 纯 Python 实现（无 WASM 依赖）
#
#  站点特征：
#    · 发布页(duoduozhuiju.com)只做域名发布，真实线路在 js/config.js
#    · 前端 Vue3 + Vite，接口前缀 /api.php/web/
#    · 所有 API 需两个固定头：web-sign、X-Client
#    · 播放地址为加密串，需 POST /api.php/web/decode/url（Protobuf）
#    · 解码签名由 Rust/WASM 生成，此处已用纯 Python 复现（见 _ddzj_sign）
#
#  设计原则（沿用剧踪干净版方法论）：
#    1. 网络层只用框架原生 session，不自造兜底链
#    2. 不依赖"异常触发降级"（默影视吞异常，自适应逻辑是负资产）
#    3. 解析只用 JSON + 正则，零外部依赖
#    4. 线路用 $$$ 分隔（默影视自定义爬虫约定）
# ════════════════════════════════════════════════════════════════

import hashlib
import random

# ── 真实线路（同一站点多域名，内容完全一致，按顺序探测可用者）──
DDZJ_HOSTS = [
    "https://dduotv01.top",
    "https://323433ssdfd.top",
    "https://duoduosdf12223234334.top",
    "https://xds2435u23422342342u.top",
]

# ── 接口固定头（硬编码在前端 JS 中）──
DDZJ_WEB_SIGN = "ddtvf65f3a83d6d9ad6f"
DDZJ_X_CLIENT = "8f3d2a1c7b6e5d4c9a0b1f2e3d4c5b6a"

# ── 解码签名密钥（从 web_app_wasm_bg.wasm 运行时内存中提取）──
DDZJ_FINGER = "WF-2c064bc5b3400788f31b848849bc3a60f835423ba2dfe69d7ea93974c216e4f2"
DDZJ_SK = "WEB-50a8e9c84a1dc05669a692ded99a2dac46527229e607a7be15db88dbc59059d1"
DDZJ_APP_ID = "com.web.player"
DDZJ_V = 1

DDZJ_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"),
    "Accept": "application/json",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "X-Client": DDZJ_X_CLIENT,
    "web-sign": DDZJ_WEB_SIGN,
}

# 实测永久失效的线路（服务端固定报 "API返回错误"），直接过滤，省去用户逐个试错
DDZJ_SOURCE_BLACKLIST = ["CO4K"]

# ── 失效图床 → 多多当前活跃图床（同路径镜像，实测 22/22 可拉取）──
# 老图床 img.ffzy888.com / pps.vodfeiss.com 已彻底死亡（连接失败，全域名变体
# 不可达），但同一图片文件在 tupian.ffeiimg.com 按原路径仍可访问
# （2026-09-10 全量实测），域名级替换即可救回历史上传的海报。
DDZJ_PIC_HOST_MAP = {
    "img.ffzy888.com": "tupian.ffeiimg.com",
    "pps.vodfeiss.com": "tupian.ffeiimg.com",
    # 常见同源镜像 / 历史域名变体
    "img.ffzy.com": "tupian.ffeiimg.com",
    "ffzy888.com": "tupian.ffeiimg.com",
    "vodfeiss.com": "tupian.ffeiimg.com",
    "img.feiss.com": "tupian.ffeiimg.com",
    "tupian.ffzy888.com": "tupian.ffeiimg.com",
}

# 支持 https 且无防盗链的图片 CDN：http 一律升级为 https
# 爱奇艺图床 pic0~pic9 / m.iqiyipic 按后缀通配升级。
DDZJ_PIC_HTTPS_HOSTS = {
    "pic2.iqiyipic.com",
    "m.ykimg.com",
    "pic.rmb.bdstatic.com",
    "bkimg.cdn.bcebos.com",
    "i0.hdslb.com",
    "i1.hdslb.com",
    "i2.hdslb.com",
    "image.tmdb.org",
    "3img.hitv.com",
    "photocdn.sohu.com",
    "mtzy2.com",
}

# 主机后缀命中也强制 https 升级
DDZJ_PIC_HTTPS_SUFFIXES = (
    ".iqiyipic.com",
    ".bdstatic.com",
    ".bcebos.com",
    ".hdslb.com",
    ".ykimg.com",
    ".hitv.com",
)

DDZJ_PIC_DEAD_HOSTS = {
    "img.bwcgee.cn",
    "lain.bgm.tv",
    "img.bgm.tv",
    "xyslzy-vip-1-10.xysl.it.com",
    "zf.yxcsoft.cn",
    "www.subaibaiys.com",
    "image.5566ziyuan.com",
    "yczy5.com",
    "p.ssl.qhimg.com",
    "q7.itc.cn",
    "q8.itc.cn",
    "img1.doubanio.com",  # 重定向/防盗链需 Referer，直链不可用
    "img2.doubanio.com",
    "img3.doubanio.com",
    "img9.doubanio.com",
    "doubanio.com",
    "img.ffzy888.com",  # 已彻底死亡，优先走 HOST_MAP；未映射到时也当死图床
    "pps.vodfeiss.com",
    "www.ffzy888.com",
    "static.youku.com",  # 常 403
}

# 死图条目的人工兜底封面（按片名搜到的可直链海报，已逐条验证 200）
DDZJ_PIC_FALLBACK = {
    "11": "https://m.iqiyipic.com/u4/image/20260807/cc/35/pv_8685550989959400_d_601_m1.jpg",  # 星期三 第二季
    "110": "https://pic.rmb.bdstatic.com/bjh/251014/dump/5f26098f54777932f6823de3025d9dbe.png",  # 凌天独尊
    "115": "https://bkimg.cdn.bcebos.com/pic/4ec2d5628535e5dde7110de7a49fb0efce1b9d16c4cb",  # 都市古仙医
    "184": "https://mtzy2.com/upload/vod/20250907-1/7748a70eee30a596ab189a2601502da0.jpg",  # 少年 II 星球
    "309": "https://m.iqiyipic.com/u9/image/20260910/0c/76/pv_1563922594214400_d_601_m1.jpg",  # 废渊战鬼
    "555": "https://3img.hitv.com/preview/sp_images/2025/07/17/202507171458201414505.jpg",  # 妖神记 第九季
    "1151": "https://m.iqiyipic.com/u4/image/20260821/64/c9/pv_6365687358478400_d_601_m1.jpg",  # 坂本日常 Part 2
    "1263": "https://pic8.iqiyipic.com/image/20220403/a6/dc/v_166874427_m_601.jpg",  # 我家的熊孩子
    "1275": "https://bkimg.cdn.bcebos.com/pic/0823dd54564e9258eecce8069682d158cdbf4e59",  # 拜托了冰箱 第一季
    "1388": "https://pics4.baidu.com/feed/8c1001e93901213fdd24137362414cde2e2e95bb.jpeg@f_auto?token=a772592e4d150d2c4fd1edce83e6fefb",  # 惊人的星期六
    "1765": "https://m.iqiyipic.com/u6/image/20250314/1b/2e/pv_4289682143744000_d_601.jpg",  # 战·争 2025
    "1995": "https://m.iqiyipic.com/u0/image/20260719/4b/09/pv_5730372006956500_d_601_m1.jpg",  # 野党
    "2200": "https://pic7.iqiyipic.com/image/20260408/34/86/v_194456278_m_601.jpg",  # 梅根2.0
    "2234": "https://q8.itc.cn/q_70/images03/20250808/7c13c9b23e1d4991b786ed6b72e64c43.jpeg",  # 神墓
    "2279": "https://m.iqiyipic.com/u2/image/20260815/d7/31/pv_3229218893931800_d_601_m1.jpg",  # 爱，死亡和机器人 第二季
    "2301": "https://m.iqiyipic.com/u3/image/20260831/51/91/pv_8355058660781700_d_601_m1.jpg",  # 爱，死亡和机器人 第三季
    "2401": "https://pic5.iqiyipic.com/image/20240604/c5/98/a_100576909_m_601.jpg",  # 王国 第二季
    "2968": "https://pic7.iqiyipic.com/image/20260818/91/9f/a_101367731_m_601.jpg",  # K-POP：猎魔女团
    "3794": "https://m.iqiyipic.com/u1/image/20260830/62/78/pv_1184498148225000_d_601_m1.jpg",  # ONE：高中英雄们
    "4511": "https://m.iqiyipic.com/u6/image/20260814/7b/6d/pv_8108793745430700_d_601_m1.jpg",  # 行尸走肉 第五季
    "5350": "https://pic3.iqiyipic.com/image/20240628/ae/49/a_100007979_m_601_m11.jpg",  # 猫和老鼠
    "5543": "https://m.iqiyipic.com/u5/image/20230306/82/b6/pv_4151709617139700_d_601.jpg",  # 纸钞屋 第一季
    "5777": "https://m.iqiyipic.com/u6/image/20260714/2d/92/pv_3554096062096700_d_601_m1.jpg",  # 无赦之仇
    "6524": "https://pic5.iqiyipic.com/image/20260826/17/be/a_101405370_m_601.jpg",  # 精英律师
    "7090": "https://pic.rmb.bdstatic.com/bjh/231230/events/cb585dd340d530ed3828d1408f456a7e1831.jpeg@h_1280",  # 老友记 第一季
    "8858": "https://pic5.iqiyipic.com/image/20260826/17/be/a_101405370_m_601.jpg",  # 百家讲坛易经的奥秘
    "10105": "https://pic5.iqiyipic.com/image/20260826/17/be/a_101405370_m_601.jpg",  # 乘风破浪3 舞台纯享版
    "10654": "https://m.iqiyipic.com/u2/image/20260907/73/3a/pv_2340419134775600_d_601_m1.jpg",  # 欢愉的艺术
    "10884": "https://m.iqiyipic.com/u7/image/20260402/ac/d4/pv_5921287478456900_d_601.jpg",  # 怪奇物语 第一季
    "10885": "https://m.iqiyipic.com/u6/image/20260408/77/e5/pv_1040910461062200_d_601.jpg",  # 怪奇物语 第四季
    "11489": "https://pic4.iqiyipic.com/image/20251111/1f/e9/a_100705548_m_601.jpg",  # 猎犬
    "18250": "https://bkimg.cdn.bcebos.com/pic/0df3d7ca7bcb0a46506c1f996b63f6246a60afc0",  # 古惑仔之胜者为王
    "18746": "https://puui.qpic.cn/vcover_vt_pic/0/ikd754nyrvfa0661481537780/0",  # 死神
    "21580": "https://m.iqiyipic.com/u6/image/20260729/13/4c/pv_6080918482441300_d_601_m1.jpg",  # 甜蜜之家：重生
    "26570": "https://m.iqiyipic.com/u7/image/20250724/7f/93/pv_1861526122884900_d_601.jpg",  # 黑袍纠察队 第四季
    "27066": "https://m.iqiyipic.com/u6/image/20240702/5e/c8/pv_7871352653508200_d_601.jpg",  # V世代 第一季
    "27763": "https://m.iqiyipic.com/u4/image/20260907/32/a3/pv_8132858721013100_d_601_m1.jpg",  # 新乌托邦
    "28826": "https://m.iqiyipic.com/u0/image/20250929/29/e8/pv_6364083026149200_d_601.jpg",  # 女囚大逃亡
    "29018": "https://pic3.iqiyipic.com/image/20231113/7a/74/v_50076831_m_601_m18.jpg",  # 哈利波特4火焰杯
    "29946": "https://m.iqiyipic.com/u8/image/20240926/b4/de/pv_1464454027996100_d_601.jpg",  # 来吧!哪里怕
    "30507": "https://pic7.iqiyipic.com/image/20241204/c6/e5/v_178868095_m_601_m3.jpg",  # 蜡笔小新：我们的恐龙日记
    "34494": "https://pic5.iqiyipic.com/image/20260802/c0/20/a_101306226_m_601.jpg",  # 地狱尖兵
    "35870": "https://pic6.iqiyipic.com/image/20260122/51/25/a_100737091_m_601_m2.jpg",  # 真探 第一季
    "36874": "https://m.iqiyipic.com/u6/image/20210923/86/d6/pv_1830241653294400_d_601.jpg",  # 人肉叉烧包2之天诛地灭
    "37370": "https://pic2.iqiyipic.com/image/20240207/ad/46/a_100554971_m_601_m13.jpg",  # 极限挑战宝藏行 第四季·和美乡村季
    "39220": "https://pic7.iqiyipic.com/image/20251208/f2/68/a_100722366_m_601.jpg",  # 辐射
    "39289": "https://pic5.iqiyipic.com/image/20260826/17/be/a_101405370_m_601.jpg",  # 哥斯拉大战金刚2：帝国崛起
    "40486": "https://puui.qpic.cn/vcover_vt_pic/0/mzc0020092vizln1690958129820/0",  # 一人之下剧场版：锈铁重现
    "44335": "https://m.iqiyipic.com/u9/image/20251231/d9/37/pv_6851799861676600_d_601.jpg",  # 恶搞之家 第一季
    "45734": "https://pic5.iqiyipic.com/image/20260826/17/be/a_101405370_m_601.jpg",  # 魔女
    "45849": "https://m.iqiyipic.com/u8/image/20250417/83/77/pv_5208162039398000_d_601.jpg",  # 极限职业
    "46504": "https://pic5.iqiyipic.com/image/20231203/30/a6/v_174700195_m_601.jpg",  # 甜蜜家园2
    "48628": "https://m.iqiyipic.com/u7/image/20260315/c3/2f/pv_5492930915793500_d_601.jpg",  # 梦魇绝镇 第一季
    "51210": "https://pic2.iqiyipic.com/image/20260709/46/d2/v_112846298_m_601_m8.jpg",  # 僵尸
    "55093": "https://m.iqiyipic.com/u3/image/20260907/33/51/pv_6331194227080900_d_601.jpg",  # 小丑回魂2
    "58400": "https://m.iqiyipic.com/u5/image/20260727/2b/81/pv_1782111704594700_d_601_m1.jpg",  # 首尔破笑组
    "61633": "https://m.iqiyipic.com/u2/image/20260328/21/36/pv_7850496342155500_d_601.jpg",  # 小丑回魂
    "65192": "https://pic7.iqiyipic.com/image/20230529/59/43/v_172784089_m_601_1248_720.jpg",  # 囧爸喜事
    "66302": "https://pic5.iqiyipic.com/image/20260826/17/be/a_101405370_m_601.jpg",  # 猫和老鼠 真人版
    "71432": "https://pic0.iqiyipic.com/image/20260211/f8/05/a_100765331_m_601.jpg",  # 凶器
    "71620": "https://pic3.iqiyipic.com/image/20250911/db/c7/v_186722264_m_601.jpg",  # 深情眼团综·眼福不浅
    "71844": "https://pic5.iqiyipic.com/image/20260826/17/be/a_101405370_m_601.jpg",  # 武碎星河
    "72141": "https://m.iqiyipic.com/u4/image/20260301/5b/26/pv_8705605135764700_d_601.jpg",  # 进击的巨人 最终季 Part.2
    "72544": "https://pic5.iqiyipic.com/image/20260826/17/be/a_101405370_m_601.jpg",  # 假面骑士Build
    "73002": "https://pic8.iqiyipic.com/image/20220403/a6/dc/v_166874427_m_601.jpg",  # 我家的熊孩子
    "73952": "https://m.iqiyipic.com/u5/image/20250731/3c/2a/pv_7932317258273200_d_601.jpg",  # 重症外伤中心
    "74004": "https://m.iqiyipic.com/u1/image/20260807/39/7b/pv_2181590296795300_d_601_m1.jpg",  # 十二使者
    "74436": "https://puui.qpic.cn/vcover_vt_pic/0/mzc00200nc1cbum1615792624639/0",  # 火影忍者 疾风传
    "74512": "https://pic4.iqiyipic.com/image/20260710/d1/1e/a_100459186_m_601_m39.jpg",  # 大主宰
    "74692": "https://vcover-vt-pic.puui.qpic.cn/vcover_vt_pic/0/324olz7ilvo2j5f1754528590932/0",  # 吞噬星空 第三季
    "75008": "https://pic0.iqiyipic.com/image/20260827/ff/0b/a_100613847_m_601_m5.jpg",  # 逆天邪神第二季
    "75210": "https://pic8.iqiyipic.com/image/20240108/72/d8/v_175128184_m_601.jpg",  # 雾山五行之犀川幻紫林篇
    "76049": "https://pic2.iqiyipic.com/image/20231110/f6/4a/v_174416239_m_601.jpg",  # 无耻之徒 第一季
    "76138": "https://vcover-vt-pic.puui.qpic.cn/vcover_vt_pic/0/324olz7ilvo2j5f1754528590932/0",  # 吞噬星空剧场版
    "76151": "https://puui.qpic.cn/vcover_vt_pic/0/mzc002000he7xqq1576836196/0",  # 择天记 第五季
    "76454": "https://pic1.iqiyipic.com/image/20240628/44/1f/a_100006334_m_601_m9.jpg",  # 黑猫警长
    "76477": "https://m.iqiyipic.com/u6/image/20190726/17/42/uv_41334509909_d_601.jpg",  # 斗罗大陆2 绝世唐门 第一季(合集)
    "76480": "https://m.ykimg.com/0534000068CA140542AF331177B32F9F",  # 凡人修仙传(重制版)
    "77041": "https://i1.hdslb.com/bfs/archive/b6edd5ff129751a7ea16adb8675310311f4c3006.jpg",  # 这是我的西游 第二季
    "77043": "https://pic1.iqiyipic.com/image/20260821/a3/bb/v_113676833_m_601_m12.jpg",  # 蜘蛛侠：英雄无归 4K（没声音切换其他浏览器）
    "77216": "https://pic6.iqiyipic.com/image/20230629/c2/2e/a_100107641_m_601_m4.jpg",  # 妖神记合集
    "77281": "https://m.ykimg.com/0534000069C5E51113F960144E201694",  # 沧元图2
    "77539": "https://m.ykimg.com/0534000068B4FF5213EFA317EC852CA6",  # 二龙湖·“村”暖花开2
    "77620": "https://m.iqiyipic.com/u1/image/20241213/8b/2b/pv_6138674422605300_d_601.jpg",  # 苍空
    "77845": "https://m.iqiyipic.com/u4/image/20260908/9f/00/pv_2339616968929700_d_601_m1.jpg",  # 电锯惊魂
    "77957": "https://pic7.iqiyipic.com/image/20260516/59/b7/a_100825757_m_601.jpg",  # 后宫
    "79148": "https://pic0.iqiyipic.com/image/20250731/c7/5a/v_50077316_m_601_m32.jpg",  # 哈利波特与魔法石
    "79181": "https://pic9.iqiyipic.com/image/20231110/af/62/v_50076796_m_601_m14.jpg",  # 哈利波特与阿兹卡班的囚徒
    "79184": "https://pic3.iqiyipic.com/image/20231113/7a/74/v_50076831_m_601_m18.jpg",  # 哈利波特与火焰杯
    "79252": "https://m.iqiyipic.com/u4/image/20260518/e0/64/pv_3739396372782900_d_601.jpg",  # 楼下的房客(无字)
    "79319": "https://pic3.iqiyipic.com/image/20260623/d9/f8/a_100892223_m_601.jpg",  # 女学生
    "79320": "https://i2.hdslb.com/bfs/archive/84c4d9b856009dc02e566cfd36ae9c751043f11c.jpg",  # 处女的关系
    "79468": "https://gips3.baidu.com/it/u=2272537208,1233714237&fm=3074&app=3074&f=JPEG?w=744&h=1053&type=normal&func=",  # 爱神 未删减版
    "79547": "https://b0.bdstatic.com/ugc/personal_page_creator/ejGN8BYtbQbwfLaQxyUzGw495bb877cc9902cde1bc2db416bc3c5c.jpg",  # 仙逆剧场版
    "79598": "https://photocdn.tv.sohu.com/img/c_lfill,w_240,h_330/20260212/vrsa_ver_1770867087658_1010415.jpg",  # 哈利波特与密室
    "79624": "https://pic2.iqiyipic.com/image/20260602/9b/cd/a_100570559_m_601_m6.jpg",  # 万人之上
    "79680": "https://pic0.iqiyipic.com/image/20260129/50/a1/v_189543483_m_601_m3.jpg",  # 鬼灭之刃 兄妹的羁绊
    "79716": "https://pic2.iqiyipic.com/image/20231110/d9/46/v_50153384_m_601_m12.jpg",  # 埃及艳后 上
    "80171": "https://pic2.iqiyipic.com/image/20231113/09/cf/a_100013818_m_601_m11.jpg",  # 银河奥特曼S
    "80174": "https://pic1.iqiyipic.com/image/20250820/a8/9b/a_100667845_m_601.jpg",  # 欧布奥特曼
    "81213": "https://pic3.iqiyipic.com/image/20231113/f9/25/a_100012627_m_601_m12.jpg",  # 圣斗士星矢
    "82971": "https://pic.rmb.bdstatic.com/bjh/3f1f8ba3df5/250924/2d7c9dda01da4fe9384278672d459557.jpeg",  # 大唐乘风录
    "83082": "https://m.iqiyipic.com/u6/image/20260405/b6/07/pv_2962899832114200_d_601.jpg",  # 弥留之国的爱丽丝 第三季
    "83241": "https://m.iqiyipic.com/u2/image/20200213/fc/86/pv_12623682400_d_601.jpg",  # 我的僵尸女儿
    "83955": "https://m.iqiyipic.com/u9/image/20260606/ff/9c/pv_3515592101319800_d_601_m1.jpg",  # 朋友的妹妹只喜欢烦我
    "83956": "https://m.iqiyipic.com/u0/image/20260209/e1/8e/pv_1607239549447100_d_601.jpg",  # 许愿吧，精灵
    "83962": "https://m.iqiyipic.com/u2/image/20260903/c0/86/pv_2109395370610000_d_601_m1.jpg",  # 东岛丹三郎想成为假面骑士
    "84173": "https://m.iqiyipic.com/u7/image/20260427/42/3f/pv_2491226313713300_d_601_m1.jpg",  # 致不灭的你 第三季
    "84878": "https://m.iqiyipic.com/u2/image/20260309/83/d9/pv_6602326283083900_d_601.jpg",  # 回魂计
    "84996": "https://m.iqiyipic.com/u5/image/20260126/af/53/pv_8922992080465500_d_601.jpg",  # 古诺希亚
    "86075": "https://m.iqiyipic.com/u1/image/20260614/7a/18/pv_3865336410905400_d_601_m1.jpg",  # 人浮于爱
    "86081": "https://m.iqiyipic.com/u7/image/20251229/09/66/pv_1555098769290500_d_601.jpg",  # 小丑回魂：欢迎来到德里镇 第一季
    "86274": "https://m.iqiyipic.com/u5/image/20260418/8d/fc/pv_8192218993291100_d_601.jpg",  # 体能之巅3: 亚洲大挑战
    "86277": "https://pic9.iqiyipic.com/image/20250725/fa/6d/v_184182808_m_601.jpg",  # 豆豆饭饭
    "86284": "https://i0.hdslb.com/bfs/bangumi/image/4a932778675708bd6a6e3c6e3e24a9eaed6bf21d.jpg",  # 仙帝归来
    "86321": "https://pic7.iqiyipic.com/image/20260815/b2/f7/a_101360312_m_601.jpg",  # 操控游戏
    "86325": "https://m.iqiyipic.com/u4/image/20251110/00/48/pv_8501855010341500_d_601.jpg",  # 亲爱的X
    "86328": "https://p1.img.cctvpic.com/photoAlbum/vms/image/e60d064205e8a9664068f448f6c6331c.jpg",  # 乌蒙深处
    "86346": "https://i1.hdslb.com/bfs/archive/9fa06f75985e9a677d92decf02f9ae3d8ed14c78.jpg",  # 差点在迷宫深处被信任的伙伴杀掉
    "86348": "https://pics3.baidu.com/feed/6609c93d70cf3bc7e3cf51b2738443b1cc112a32.jpeg@f_auto?token=d1351dffb501db1675f46017952349c3",  # 咒术回战第三季
    "86379": "https://m.iqiyipic.com/u7/image/20260510/60/89/pv_7662789533853300_d_601_m1.jpg",  # 无尾熊绘日记
    "86380": "https://pics2.baidu.com/feed/730e0cf3d7ca7bcb4b39a2035bd4a773f724a84e.jpeg@f_auto?token=1d9e2a213fbdb06076b0a364144f6274",  # 九阳武神
    "86397": "https://pic5.iqiyipic.com/image/20251128/e6/84/a_100570787_m_601_m4.jpg",  # 傲世丹神
    "86415": "https://m.iqiyipic.com/u8/image/20251108/e1/06/pv_4608944151412100_d_601.jpg",  # 怪奇物语 第五季
    "86417": "https://pic5.iqiyipic.com/image/20260826/17/be/a_101405370_m_601.jpg",  # 吾岸
    "86418": "https://m.ykimg.com/05340000698D8E0670A43D1E22C4884B",  # 百炼成神第三季
    "86419": "https://i0.hdslb.com/bfs/archive/9089f51cccbdcf8d5e5f35fc7d375be660c461f5.jpg",  # 链锯人 剧场版：蕾塞篇
    "86424": "https://m.iqiyipic.com/u0/image/20260521/c7/8e/pv_5929309137010300_d_601_m1.jpg",  # 终末的女武神第三季
    "86444": "https://pic5.iqiyipic.com/image/20260826/17/be/a_101405370_m_601.jpg",  # 女神在线TV
    "86449": "https://pic5.iqiyipic.com/image/20260826/17/be/a_101405370_m_601.jpg",  # 乱"室"英雄
    "86454": "https://pic5.iqiyipic.com/image/20260826/17/be/a_101405370_m_601.jpg",  # 暖暖的味道
    "86455": "https://pic5.iqiyipic.com/image/20260826/17/be/a_101405370_m_601.jpg",  # 玩转桂林懒人包
    "86461": "https://bkimg.cdn.bcebos.com/pic/48540923dd54564e925886ae80878b82d158cdbfe1a9",  # 永生之太元仙府
    "86490": "https://pic8.iqiyipic.com/image/20251113/de/0d/a_100705364_m_601_m3.jpg",  # 鬼灭之刃 剧场版 无限城篇 第一部
    "86493": "https://i1.hdslb.com/bfs/archive/c1a88520a315f793dc08a6321542304e259d812e.jpg",  # 海绵宝宝：深海大冒险
    "86494": "https://m.iqiyipic.com/u9/image/20260531/9c/31/pv_2853003111004900_d_601_m1.jpg",  # 泛而不精的我被逐出了勇者队伍
    "86496": "https://pic7.iqiyipic.com/image/20260627/dc/b4/v_202838474_m_601.jpg",  # 现在多闻君是哪一面！？
    "86497": "https://q8.itc.cn/q_70/images03/20251231/3fc204f1223d450e899739ea38af0656.jpeg",  # 中国奇谭2
    "86515": "https://m.iqiyipic.com/u6/image/20240817/53/3c/pv_7929108594556400_d_601.jpg",  # 勇者处刑 惩罚勇者9004队服刑记录
    "86517": "https://m.iqiyipic.com/u1/image/20260318/54/f6/pv_1645743510178300_d_601.jpg",  # 魔术师库诺看得见一切
    "86519": "https://m.iqiyipic.com/u3/image/20260524/f3/7a/pv_2249774393598100_d_601_m1.jpg",  # 异国日记
    "86520": "https://m.iqiyipic.com/u9/image/20260905/cf/ab/pv_8602125741876200_d_601_m1.jpg",  # 贵族转生 ～得天眷顾一出生就获得最强力量～
    "86523": "https://m.iqiyipic.com/u3/image/20260731/c2/2f/pv_6749122633563400_d_601_m1.jpg",  # 黄金神威 最终章
    "86524": "https://m.iqiyipic.com/u0/image/20260415/e2/7f/pv_1711521109748700_d_601.jpg",  # 能帮我弄干净吗？
    "86532": "https://m.iqiyipic.com/u7/image/20260726/eb/df/pv_4697984560989900_d_601_m1.jpg",  # 魔王的女儿太温柔了！！
    "86533": "https://m.iqiyipic.com/u7/image/20260908/a1/7d/pv_4779805477641200_d_601_m1.jpg",  # 午夜的倾心旋律
    "86535": "https://m.iqiyipic.com/u6/image/20260826/26/5a/pv_7079614962916700_d_601_m1.jpg",  # 异世界的安泰全看社畜
    "86536": "https://m.iqiyipic.com/u2/image/20260408/07/d2/pv_5434372808913100_d_601.jpg",  # 达尔文事变
    "86539": "https://m.iqiyipic.com/u6/image/20260908/46/f6/pv_2488017650776300_d_601_m1.jpg",  # 安逸领主的愉快领地防卫
    "86542": "https://m.iqiyipic.com/u0/image/20260620/55/d0/pv_2698185102528300_d_601_m1.jpg",  # 优雅贵族的休假指南。
    "86547": "https://pic5.iqiyipic.com/image/20260826/17/be/a_101405370_m_601.jpg",  # 春日狂热
    "86549": "https://m.iqiyipic.com/u7/image/20260830/93/12/pv_8854005818069700_d_601_m1.jpg",  # 第一个男人
    "86561": "https://i1.hdslb.com/bfs/archive/e6de2472c9e33485e8d2f26a60fc345ae94f5ebd.jpg",  # 魔都精兵的奴隶第二季
    "86562": "https://m.iqiyipic.com/u4/image/20260415/4c/9f/pv_2887496242500900_d_601.jpg",  # 透明男子与人类女孩 ~两人迟早会成为夫妻~
    "86563": "https://m.iqiyipic.com/u2/image/20260207/2b/46/pv_1907249576511100_d_601.jpg",  # 「凭你也想讨伐魔王？」被勇者小队逐出队伍，只好在王都自在过活
    "86565": "https://pic4.iqiyipic.com/image/20260710/d1/1e/a_100459186_m_601_m39.jpg",  # 大主宰年番第二季
    "86568": "https://m.iqiyipic.com/u2/image/20260324/ca/c6/pv_4420435177393000_d_601.jpg",  # DARK MOON -黑之月：月之祭坛-
    "86569": "https://m.iqiyipic.com/u1/image/20260821/e9/77/pv_3248470874314600_d_601_m1.jpg",  # 地狱模式 ～喜欢速通游戏的玩家在废设定异世界无双～
    "86570": "https://m.iqiyipic.com/u2/image/20230905/b5/eb/pv_1743607742569700_d_601.jpg",  # 炎炎消防队 三之章 第2部分
    "86571": "https://m.iqiyipic.com/u5/image/20260907/99/dd/pv_6617567434700100_d_601_m1.jpg",  # 和机器人啪啪啪能算在经验次数里吗？
    "86575": "https://m.iqiyipic.com/u2/image/20260903/92/46/pv_6581469971556000_d_601_m1.jpg",  # 转生之后的我变成了龙蛋
    "86576": "https://m.iqiyipic.com/u0/image/20260708/a9/90/pv_6997794046260900_d_601_m1.jpg",  # 死亡账号
    "86578": "https://i2.hdslb.com/bfs/archive/3ecc0d4f67e13a6011f9349a30bda2a8d6a25984.jpg",  # 勇者之屑
    "86579": "https://pic5.iqiyipic.com/image/20260826/17/be/a_101405370_m_601.jpg",  # 命运-奇异赝品
    "86581": "https://pic5.iqiyipic.com/image/20260826/17/be/a_101405370_m_601.jpg",  # 相反的你和我
    "86584": "https://m.iqiyipic.com/u1/image/20260409/de/fc/pv_8971122031440700_d_601.jpg",  # 地狱乐第二季
    "86585": "https://m.iqiyipic.com/u6/image/20260529/b5/33/pv_2431866041064300_d_601_m1.jpg",  # 暗芝居第16季
    "86586": "https://m.iqiyipic.com/u7/image/20260607/f8/0f/pv_3327885292955100_d_601_m1.jpg",  # 皎洁迎宵之月
    "86587": "https://m.iqiyipic.com/u0/image/20260503/c1/1c/pv_3941542166359600_d_601_m1.jpg",  # 公主大人，接下来是“拷问”时间第二季
    "86590": "https://m.iqiyipic.com/u4/image/20260708/a9/ce/pv_1912864737692900_d_601_m1.jpg",  # 被邻国王子溺爱的反派女主
    "86592": "https://i2.hdslb.com/bfs/archive/1476ec3d0393a10f9a77f3f4d1317b16f9e4d330.jpg",  # 我推的孩子第三季
    "86595": "https://m.iqiyipic.com/u5/image/20250716/23/44/pv_2199237944753600_d_601.jpg",  # 卡片战斗先导者 Divinez 幻真星战篇
    "86598": "https://pic5.iqiyipic.com/image/20260826/17/be/a_101405370_m_601.jpg",  # 极限人生
    "86609": "https://m.iqiyipic.com/u4/image/20260208/5b/7f/pv_8707209467443100_d_601.jpg",  # 七王国的骑士 第一季
    "86628": "https://m.iqiyipic.com/u5/image/20260907/bf/4c/pv_4559209869488800_d_601_m1.jpg",  # 今天开始是人类
    "86629": "https://b0.bdstatic.com/ugc/personal_page_pad/3sGJ-28EhOOUycL8j_n5DA844196264c2dde6ea22647751ec66c76.jpg",  # 卧底洪小姐
    "86632": "https://pica.zhimg.com/v2-e24b7e7705a3347459cc7cd5e5433ed6_720w.jpg?source=172ae18b",  # 法官李汉英
    "86809": "https://m.iqiyipic.com/u3/image/20260704/f2/13/pv_2865837764725900_d_601_m1.jpg",  # 匹兹堡医护前线 第二季
    "86970": "https://q0.itc.cn/images01/20250914/745d03f392dd41ca905ead46fa0defb6.jpeg",  # 全信没收
    "87011": "https://pic.rmb.bdstatic.com/bjh/bc17f566c0c/260501/035d5dab4296c64e67851137e303c015.jpeg",  # 再见十八班
    "87035": "https://m.iqiyipic.com/u2/image/20260624/d1/78/pv_5603629802930900_d_601_m1.jpg",  # 给你宇宙
    "87116": "https://pic3.iqiyipic.com/image/20240529/3f/ae/v_112855833_m_601_m4.jpg",  # 斯巴达克斯：亚述家族
    "87221": "https://i1.hdslb.com/bfs/archive/1f03409429b4534427fcd92da077d56862a86d98.jpg",  # 单身即地狱 第五季
    "87500": "https://pic0.iqiyipic.com/image/20250208/30/f6/a_100007729_m_601_m15_579_772.jpg",  # 片厂风云（近似封面）
    "87717": "https://bkimg.cdn.bcebos.com/pic/6159252dd42a2834572be1fc55b5c9ea14cebfbc",  # 全面开战：兄弟会
    "87739": "https://i0.hdslb.com/bfs/archive/21966b79a443e3409fa436f08c7ed0cc8342bdd9.jpg",  # 咒术回战 死灭回游 前篇
    "87740": "https://pic8.iqiyipic.com/image/20200916/c4/05/a_100012673_m_601_m7.jpg",  # 名侦探光之美少女！
    "87744": "https://pic5.iqiyipic.com/image/20260826/17/be/a_101405370_m_601.jpg",  # 斗罗大陆第二季
    "87753": "https://m.iqiyipic.com/u6/image/20260906/75/35/pv_4904141184039800_d_601_m1.jpg",  # 莎拉的真伪人生
    "87829": "https://m.iqiyipic.com/u6/image/20260226/56/e0/pv_6510879376443500_d_601.jpg",  # 爱情怎么翻译？
    "87869": "https://pic2.iqiyipic.com/image/20231109/b2/85/v_137654881_m_601_m14.jpg",  # 犯罪现场 Zero
    "87870": "https://m.iqiyipic.com/u0/image/20260830/da/97/pv_4142885794521200_d_601_m1.jpg",  # 弱小英雄 第一季
    "87901": "https://i2.hdslb.com/bfs/archive/c7309ee77f5d4d297fd42eeb0a20be4dcd22f77d.jpg",  # 罗罗民宿
    "88033": "https://pic4.iqiyipic.com/image/20250422/a5/41/a_100591521_m_601_m6.jpg",  # 恋爱兄妹
    "88079": "https://m.iqiyipic.com/u8/image/20260520/d7/63/pv_2826531638100300_d_601_m1.jpg",  # 出差十五夜 第二季
    "88123": "https://pic5.iqiyipic.com/image/20251021/33/7d/v_188771103_m_601.jpg",  # 豆豆笑笑
    "88135": "https://m.iqiyipic.com/u3/image/20260803/bc/3d/pv_3374410912299300_d_601_m1.jpg",  # 弱小英雄 第二季
    "88136": "https://pic2.iqiyipic.com/image/20260507/30/22/a_100816820_m_601.jpg",  # 陷阱，致命的诱惑
    "88228": "https://pic5.iqiyipic.com/image/20260826/17/be/a_101405370_m_601.jpg",  # 文明之旅
    "88263": "https://pic5.iqiyipic.com/image/20260826/17/be/a_101405370_m_601.jpg",  # 17号音乐仓库第三季
    "88285": "https://pic5.iqiyipic.com/image/20260826/17/be/a_101405370_m_601.jpg",  # 大主宰年番年番
    "88293": "https://pic5.iqiyipic.com/image/20260826/17/be/a_101405370_m_601.jpg",  # 判处勇者刑
    "88347": "https://i0.hdslb.com/bfs/archive/f7fcf7c8f023fc2c05d5b0e0118319825061fa9a.jpg",  # 特工迷阵
    "88685": "https://m.iqiyipic.com/u2/image/20260830/7f/e5/pv_6947257598118200_d_601_m1.jpg",  # 极乐凶间 第二季
    "88724": "https://pic5.iqiyipic.com/image/20260826/17/be/a_101405370_m_601.jpg",  # 悬崖绝壁
    "88749": "https://m.iqiyipic.com/u5/image/20260908/bc/a3/pv_7747819114146700_d_601_m1.jpg",  # 帝王计划：怪兽遗产 第二季
    "88813": "https://i0.hdslb.com/bfs/archive/3029927045d4a92d4777b0e39e8b0f2885529735.jpg",  # 奉法而行
    "88820": "https://m.iqiyipic.com/u2/image/20260906/ec/20/pv_5306828439553100_d_601_m1.jpg",  # 法警小队
    "88835": "https://pic3.iqiyipic.com/image/20210916/e6/63/v_50326303_m_601_m13.jpg",  # 惊声尖叫7
    "88840": "https://imgs.aixifan.com/newUpload/205108_8f32b10b4a684eb79cbd46c38bb24cba.jpg",  # 动起来从前有只猫
    "88907": "https://m.iqiyipic.com/u8/image/20260829/a7/1b/pv_8112002408953100_d_601_m1.jpg",  # 订阅男友
    "88929": "https://i2.hdslb.com/bfs/archive/68cf6b963b439dc36b0898433a4e910a5e7baec6.jpg",  # 真相捕捉 第三季
    "88946": "https://i1.hdslb.com/bfs/archive/dc2eb18034a48aa07b70578f2edbc013d5924ff7.jpg",  # 海贼王(真人版) 第二季
    "88966": "https://m.iqiyipic.com/u7/image/20260615/d9/d2/pv_3374410912123700_d_601_m1.jpg",  # 首席女法医 第一季
    "89000": "https://m.iqiyipic.com/u4/image/20260612/9b/17/pv_7908252283297800_d_601_m1.jpg",  # 公鸡斗士
    "89015": "https://q1.itc.cn/q_70/images03/20260316/be5003100f5c49a7b6b33ba89156bdd3.jpeg",  # 正义女神国语
    "91586": "https://pic5.iqiyipic.com/image/20260826/17/be/a_101405370_m_601.jpg",  # 新狂蟒之灾
    "91644": "https://i1.hdslb.com/bfs/archive/4c47208f1ccf9d577b0b87150153039dc9c43bcd.jpg",  # 链锯人剧场版(蕾塞篇)
    "91646": "https://m.iqiyipic.com/u0/image/20260909/14/62/pv_8391156123993400_d_601_m1.jpg",  # 角头：斗阵欸
    "91983": "https://n.sinaimg.cn/sinakd20100/261/w1080h1581/20250825/0ff6-a9a7354f5cb4905088fd946a167fbf8a.jpg",  # 咒术回战涩谷事变×死灭回游剧场版
    "92273": "https://i2.hdslb.com/bfs/archive/4455ffbb3abe43df62894985643c177604123b26.jpg",  # 男生女生向前冲
    "92777": "https://m.iqiyipic.com/u7/image/20210713/c4/dc/pv_4551990374405500_d_601.jpg",  # 色即是空
    "92849": "https://m.iqiyipic.com/u1/image/20260618/11/31/pv_4114809989592400_d_601_m1.jpg",  # 放射危机
    "92859": "https://q6.itc.cn/q_70/images03/20251206/7575e561d5204e96a89a5235d991114a.jpeg",  # 浴血黑帮：不朽传奇
    "92886": "https://youjiaoku.gccdn.com/2021/12/20211231131831270.jpg",  # 超级飞侠 第十一季
    "92887": "https://bkimg.cdn.bcebos.com/pic/37d12f2eb9389b504fc2b61a8d62f2dde71190efc066",  # 超级飞侠 第九季
    "92972": "https://m.iqiyipic.com/u4/image/20260427/1a/e8/pv_5488920086580100_d_601_m1.jpg",  # 索命舞娘
    "93021": "https://m.iqiyipic.com/u4/image/20260424/33/fe/pv_2078110902149400_d_601.jpg",  # 春夏秋冬代行者 春之舞
    "93026": "https://yqk.j3kjn242sq.com/image/cover/2026/02/13/d65dbdfca1ff4f8587399acda013f4d4.jpeg",  # 他心不难测
    "93095": "https://m.iqiyipic.com/u2/image/20260616/02/18/pv_7767071094118600_d_601_m1.jpg",  # 女仆小姐的贪吃日常
    "93096": "https://m.iqiyipic.com/u1/image/20260618/4c/f3/pv_2148701496862100_d_601_m1.jpg",  # 最强的职业不是勇者也不是贤者好像是鉴定士(伪)的样子?
    "93099": "https://m.iqiyipic.com/u0/image/20260612/9d/ec/pv_2540158430527200_d_601_m1.jpg",  # 人工情报
    "93112": "https://m.iqiyipic.com/u8/image/20240925/d6/66/pv_4711621379494200_d_601.jpg",  # 欢迎来到实力至上主义教室 第四季
    "93113": "https://m.iqiyipic.com/u7/image/20260812/a9/40/pv_5646144593003100_d_601_m1.jpg",  # 异兽魔都 第二季
    "93114": "https://m.iqiyipic.com/u6/image/20240326/13/df/pv_3575754538960500_d_601.jpg",  # 转生成自动贩卖机的我今天也在迷宫徘徊 第三季
    "93116": "https://m.iqiyipic.com/u5/image/20260523/bb/00/pv_5825027576823500_d_601_m1.jpg",  # 最强王者的第二人生 第二季
    "93117": "https://nimg.ws.126.net/?url=http%3A%2F%2Fdingyue.ws.126.net%2F2026%2F0407%2F28b4e682j00td48oz0as8d001jj01vpm.jpg&thumbnail=660x2147483647&quality=80&type=jpg",  # 暴锋雨
    "93118": "https://pic1.iqiyipic.com/image/20260420/81/a1/v_197132533_m_601.jpg",  # 溜掉的大鱼比不上自己钓到的鱼
    "93154": "https://pic5.iqiyipic.com/image/20250403/d2/d9/a_100604817_m_601_m4.jpg",  # 石纪元 第四季 Part 3
    "93156": "https://pic8.iqiyipic.com/image/20260827/e0/d2/v_216893806_m_601.jpg",  # 冰之城墙
    "93157": "https://m.iqiyipic.com/u7/image/20260526/6b/d5/pv_8215481802959700_d_601_m1.jpg",  # 雾尾粉丝俱乐部
    "93167": "https://m.iqiyipic.com/u8/image/20260403/ca/99/pv_3201945254750300_d_601.jpg",  # 灰原君的青春二周目
    "93168": "https://m.iqiyipic.com/u5/image/20260825/e6/52/pv_4385139880487300_d_601_m1.jpg",  # 吃魔物的冒险者
    "93212": "https://m.iqiyipic.com/u5/image/20260408/1b/08/pv_8330993684951100_d_601.jpg",  # 猎犬 第二季
    "93215": "https://pic3.iqiyipic.com/image/20260823/8d/29/v_215561918_m_601.jpg",  # 自称恶役大小姐的婚约者观察记录。
    "97057": "https://m.iqiyipic.com/u7/image/20200107/74/07/pv_11149966400_d_601.jpg",  # 小书痴的下克上 〜为了成为图书管理员而不择手段〜 领主的养女
    "97058": "https://pic0.iqiyipic.com/image/20230629/a2/f8/a_100354210_m_601_m2.jpg",  # 入间同学入魔了 第四季
    "97059": "https://m.iqiyipic.com/u6/image/20260405/d2/62/pv_1425950067884500_d_601.jpg",  # 摩绪
    "97060": "https://m.iqiyipic.com/u2/image/20260909/d6/7b/pv_7579364286121700_d_601_m1.jpg",  # 落语朱音
    "97061": "https://m.iqiyipic.com/u4/image/20260910/06/46/pv_3818008626223700_d_601.jpg",  # 迦楠大人的白给是恶魔级
    "97062": "https://m.iqiyipic.com/u2/image/20260906/81/6c/pv_6490023064901000_d_601_m1.jpg",  # 楠木邸的神明庭院
    "97064": "https://m.iqiyipic.com/u2/image/20260616/aa/5d/pv_8831545174009100_d_601_m1.jpg",  # 主播女孩重度依赖
    "97065": "https://m.iqiyipic.com/u7/image/20260203/27/13/pv_1056953777913600_d_601.jpg",  # 黄泉的使者
    "97598": "https://bkimg.cdn.bcebos.com/pic/6a600c338744ebf81a4cb74495a2c02a6059252d090e",  # 猫和老鼠全集
    "101231": "https://gips1.baidu.com/it/u=932132706,633165869&fm=3074&app=3074&f=JPEG",  # 超级马力欧银河大电影
    "101251": "https://pic5.iqiyipic.com/image/20260826/17/be/a_101405370_m_601.jpg",  # 钻石王牌 第四季
    "101278": "https://pic5.iqiyipic.com/image/20260826/17/be/a_101405370_m_601.jpg",  # 日本三国
    "101313": "https://m.iqiyipic.com/u2/image/20260908/7f/58/pv_6129850599301200_d_601.jpg",  # 幽灵音乐会：遗失的歌曲
    "101321": "https://pic7.iqiyipic.com/image/20260609/cc/31/v_200637996_m_601.jpg",  # 尖帽子的魔法工坊
    "101322": "https://m.iqiyipic.com/u1/image/20260421/21/3e/pv_2650055151571200_d_601_m1.jpg",  # 异世界悠闲农家 第二季
    "101323": "https://m.iqiyipic.com/u7/image/20260729/db/27/pv_5376616868140800_d_601_m1.jpg",  # 废柴风纪委员与裙子长度不合规的JK的故事
    "101333": "https://m.iqiyipic.com/u1/image/20250324/02/86/pv_2976536651068300_d_601.jpg",  # 身为悲剧始作俑者的最强邪恶BOSS女王为民竭心尽力。 第二季
    "101334": "https://i2.hdslb.com/bfs/archive/ba2027737aef6e66f5c531bf71899a111467c5c3.jpg",  # 左撇子艾伦
    "101338": "https://m.iqiyipic.com/u7/image/20260908/32/d4/pv_1446806380487400_d_601_m1.jpg",  # 当前、正被打扰中！
    "101339": "https://m.iqiyipic.com/u9/image/20260619/d7/8e/pv_6092148804124400_d_601_m1.jpg",  # 女神“异世界转生想成为什么”我“勇者的肋骨”
    "101354": "https://m.iqiyipic.com/u9/image/20260906/e2/17/pv_7547277652176900_d_601_m1.jpg",  # 拜托了偶像公主
    "101380": "https://pic8.iqiyipic.com/image/20260909/5b/77/a_101467883_m_601.jpg",  # 租借女友 第五季
    "101381": "https://m.iqiyipic.com/u2/image/20260607/53/92/pv_6080918482259600_d_601_m1.jpg",  # 没有辣妹会对阿宅温柔!?
    "101440": "https://m.iqiyipic.com/u7/image/20260410/5f/87/pv_2634011834598500_d_601.jpg",  # 一叠间漫画咖啡屋生活！
    "101441": "https://m.iqiyipic.com/u4/image/20260905/91/00/pv_8857214481472900_d_601_m1.jpg",  # 杀手青春
    "101442": "https://m.iqiyipic.com/u5/image/20260610/97/3c/pv_5802566933077600_d_601_m1.jpg",  # 弱弱老师
    "101446": "https://m.iqiyipic.com/u5/image/20260710/85/fd/pv_1776496543591000_d_601_m1.jpg",  # 亢奋 第三季
    "101449": "https://m.iqiyipic.com/u5/image/20260529/94/4d/pv_5704702699673400_d_601_m1.jpg",  # 黑猫与魔女的教室
    "101457": "https://k.sinaimg.cn/n/sinakd20100/280/w1080h1600/20260505/d3db-533eca769bbead3ea8ef21696bbc0103.jpg/w700d1q75cms.jpg",  # 准备好了没2：我来了
    "101852": "https://m.iqiyipic.com/u3/image/20260623/3b/b9/pv_1382633112325500_d_601_m1.jpg",  # 隐欲囚笼
    "101936": "https://pic5.iqiyipic.com/image/20241017/d6/77/v_178624783_m_601_m1.jpg",  # 哆啦A梦：大雄与龙之骑士
    "102073": "https://b0.bdstatic.com/aa87091424e0eed42b36738dcb2c1c95.jpg",  # 雨霖铃第二千零二十六季
    "102192": "https://pic5.iqiyipic.com/image/20260826/17/be/a_101405370_m_601.jpg",  # 瑞克和莫蒂第九季
    "102862": "https://pic4.iqiyipic.com/image/20231110/6f/d9/v_108677046_m_601_m11.jpg",  # 惩罚者：最后一击
    "102863": "https://i0.hdslb.com/bfs/archive/ad8e5b12960ca80159e4900864fa013b808b31e0.jpg",  # 群体
    "102980": "https://i0.hdslb.com/bfs/archive/6f384f7a6110b1d317e935c6ce009571dd15457e.jpg",  # 金特务：本色回归
    "102981": "https://m.iqiyipic.com/u3/image/20260823/c4/d7/pv_5176877572171700_d_601_m1.jpg",  # 釜山行前传（首尔站）
    "103063": "https://gips1.baidu.com/it/u=4001860221,2517249291&fm=3074&app=3074&f=JPEG?w=850&h=1246&type=normal&func=",  # 攻壳机动队 THE GHOST
    "103068": "https://pic5.iqiyipic.com/image/20260826/17/be/a_101405370_m_601.jpg",  # 怪奇:伊藤润二令人彻夜难眠的奇异
    "103071": "https://m.iqiyipic.com/u9/image/20260705/6b/4c/pv_8903740100386600_d_601_m1.jpg",  # 末日地堡第三季
    "103100": "https://pic5.iqiyipic.com/image/20260826/17/be/a_101405370_m_601.jpg",  # 感谢对战。～大小姐才不玩格斗游
    "103120": "https://m.iqiyipic.com/u3/image/20260623/ff/e9/pv_5474481101431400_d_601_m1.jpg",  # 克雷瓦提斯2：魔兽之王与虚伪的勇者传承
    "103128": "https://pic5.iqiyipic.com/image/20260826/17/be/a_101405370_m_601.jpg",  # 要再做一次夫妇吗:伪装夫妇:
    "103151": "https://pic5.iqiyipic.com/image/20231109/de/43/v_135854365_m_601_m4.jpg",  # 仙履奇缘
    "103224": "https://gips0.baidu.com/it/u=2164534520,1536117032&fm=3074&app=3074&f=JPEG",  # 顾长歌:我天命大反派
    "103248": "https://m.iqiyipic.com/u7/image/20260901/5d/1a/pv_4747718843721000_d_601_m1.jpg",  # 鬼谜东宫
    "103254": "https://i1.hdslb.com/bfs/archive/f941b035142ee6e62244f405a8e6194365e24149.jpg",  # 炼气十万年特别篇 阳极天下
    "103377": "https://pic5.iqiyipic.com/image/20260826/17/be/a_101405370_m_601.jpg",  # 超级少女
    "103382": "https://m.iqiyipic.com/u4/image/20260726/c9/0e/pv_6376917680206500_d_601_m1.jpg",  # 死神千年血战篇(祸进谭)
    "103390": "https://m.iqiyipic.com/u7/image/20260729/13/0f/pv_5999899731810500_d_601_m1.jpg",  # 狂怒追缉
    "103391": "https://m.iqiyipic.com/u2/image/20260731/bc/a1/pv_4137270633459200_d_601_m1.jpg",  # 聪明镇
    "103463": "https://m.iqiyipic.com/u3/image/20260814/e1/c7/pv_8272435578424200_d_601_m1.jpg",  # 母狮第三季
    "106240": "https://bkimg.cdn.bcebos.com/pic/5fdf8db1cb13495439fcb8cb5d4e9258d0094aba",  # 凡人的品格
    "109212": "https://pic6.dfvah.top/upload/vod/20230830-1/e36aa19f085bd458e5d8f4bd74049409.jpg",  # 超级飞侠第八季
    "130533": "https://image.tmdb.org/t/p/w500/lVlZ6tNUWSCxnXfVWbvn42neua6.jpg",  # 艾米利亚诺·马丁内斯：守住时间的
    "131170": "https://pic5.iqiyipic.com/image/20231109/b8/dc/v_50084074_m_601_m16.jpg",  # 第六感城市观光第四季
    "131235": "https://m.iqiyipic.com/u0/image/20210415/7d/ff/pv_6371302516801300_d_601.jpg",  # 新西游记特别篇：春日野营
    "131271": "https://m.iqiyipic.com/u8/image/20260521/08/ff/pv_1201343630644100_d_601_m1.jpg",  # 生存王：部落战争
    "131703": "https://pic5.iqiyipic.com/image/20260826/17/be/a_101405370_m_601.jpg",  # 男生男生配
    "131805": "https://m.iqiyipic.com/u5/image/20260905/d8/e6/pv_4285671315456600_d_601.jpg",  # 欲罢不能：拉丁裔
    "131806": "https://pic1.iqiyipic.com/image/20191011/38/ef/a_100356082_m_601.jpg",  # 欲罢不能(德国版)
    "131914": "https://i2.hdslb.com/bfs/archive/cf07aa468db688b0bf53faf14e6ab628dbaccf3d.png",  # 女高推理班第一季
    "132007": "https://m.iqiyipic.com/u8/image/20210802/d8/64/pv_7798355560082700_d_601.jpg",  # 思想验证区域：TheCommunity
    "132010": "https://photocdn.sohu.com/kis/fengmian/1191/1191886/1191886_ver_big.jpg",  # 伊甸园第一季
    "132012": "https://pic4.iqiyipic.com/image/20260324/dc/ea/a_100788114_m_601.jpg",  # 同床异梦2：你是我的命运
    "132016": "https://m.iqiyipic.com/u5/image/20260905/c6/4d/pv_5721548182810300_d_601.jpg",  # 芬兰租房生活
    "132018": "https://m.iqiyipic.com/u5/image/20260909/24/32/pv_1173267826379700_d_601_m1.jpg",  # RunningMan2022
    "132019": "https://pic6.iqiyipic.com/image/20201225/58/57/v_155982140_m_601.jpg",  # RunningMan2021
    "132790": "https://image13.m1905.cn/uploadfile/2014/1027/20141027042625787482.jpg",  # 新古惑仔之少年激斗篇
    "132791": "https://image11.m1905.cn/uploadfile/2014/1027/20141027044632654428.jpg",  # 古惑仔3：只手遮天
    "132792": "https://bkimg.cdn.bcebos.com/pic/f2deb48f8c5494eef01f0f1b6badf7fe9925bc31d023",  # 古惑仔2：猛龙过江
    "136398": "https://pic.rmb.bdstatic.com/bjh/news/886adea3df2862bf28300e67bf5f92bc.png",  # 侠探杰克第四季
    "139576": "https://b.bdstatic.com/4fa3672fc060893a4f85c35723805538.jpeg",  # 蜘蛛侠英雄远征
}

# 官方发布页：域名轮换的真正来源（DDZJ_HOSTS 只是它挂掉时的备份）
DDZJ_PUBLISHER = "https://duoduozhuiju.com"


# ═══════════════ Protobuf 极简编解码（仅够本站用）═══════════════
def _pb_varint(n):
    out = bytearray()
    n = int(n)
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            break
    return bytes(out)


def _pb_bytes(fno, payload):
    if isinstance(payload, str):
        payload = payload.encode("utf-8")
    return _pb_varint((fno << 3) | 2) + _pb_varint(len(payload)) + payload


def _pb_int(fno, n):
    return _pb_varint((fno << 3) | 0) + _pb_varint(n)


def _pb_parse(blob):
    """返回 {field_no: value}，varint 为 int，length-delimited 为 bytes"""
    out = {}
    i = 0
    n = len(blob)
    while i < n:
        key = 0
        shift = 0
        while True:
            x = blob[i]
            i += 1
            key |= (x & 0x7F) << shift
            shift += 7
            if not (x & 0x80):
                break
        fn, wt = key >> 3, key & 7
        if wt == 0:
            v = 0
            s = 0
            while True:
                x = blob[i]
                i += 1
                v |= (x & 0x7F) << s
                s += 7
                if not (x & 0x80):
                    break
            out[fn] = v
        elif wt == 2:
            ln = 0
            s = 0
            while True:
                x = blob[i]
                i += 1
                ln |= (x & 0x7F) << s
                s += 7
                if not (x & 0x80):
                    break
            out[fn] = blob[i:i + ln]
            i += ln
        else:
            break
    return out


def _ddzj_sign(nonce, t):
    """复现 WASM 的签名：SHA256(finger=..&id=..&nonce=..&sk=..&time=..&v=1) 大写"""
    raw = "finger=%s&id=%s&nonce=%s&sk=%s&time=%d&v=%d" % (
        DDZJ_FINGER, DDZJ_APP_ID, nonce, DDZJ_SK, t, DDZJ_V)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest().upper()


def _ddzj_build_body(code, flag):
    """构造 decode/url 的 Protobuf 请求体（字段号固定）"""
    t = int(time.time() * 1000)
    nonce = "".join(random.choice("0123456789abcdef") for _ in range(32))
    return (_pb_bytes(1, code)      # 加密串
            + _pb_bytes(2, flag)    # 线路名（vodFrom）
            + _pb_int(3, t)         # 毫秒时间戳
            + _pb_bytes(4, nonce)   # 32 位随机 hex
            + _pb_bytes(5, _ddzj_sign(nonce, t))
            + _pb_bytes(6, DDZJ_APP_ID)
            + _pb_int(7, DDZJ_V))


def _join_val(v):
    """vod_area / vod_class 可能是 list 也可能是 str"""
    if v is None:
        return ""
    if isinstance(v, (list, tuple)):
        return ",".join(str(x) for x in v if x)
    return str(v)


class Spider(LunHai_BiAn):
    """多多追剧 —— 继承轮海境，JSON 接口 + 纯 Python 解码"""
    realm_name = "多多追剧"
    realm_level = 1
    defense_level = 0

    def __init__(self):
        super().__init__()
        self.siteUrl = DDZJ_HOSTS[0]
        self._host = None
        self._cats = None          # [(type_id, type_name), ...]
        self._cache_until = 0
        self._web_sign = DDZJ_WEB_SIGN
        self._x_client = DDZJ_X_CLIENT

    # ───────── 网络层：标准 session，无兜底链 ─────────
    def _build_headers(self, extra=None):
        h = dict(DDZJ_HEADERS)
        # 运行时可能已通过 _refresh_sign 更新
        if getattr(self, "_web_sign", None):
            h["web-sign"] = self._web_sign
        if getattr(self, "_x_client", None):
            h["X-Client"] = self._x_client
        h["Referer"] = self._host_or_default() + "/"
        if extra:
            h.update(extra)
        return h

    def _host_or_default(self):
        return self._host or self.siteUrl

    def _refresh_sign(self, host=None):
        """从站点前端 JS 刷新 web-sign / X-Client（签名轮换时自动恢复）"""
        host = (host or self._host_or_default()).rstrip("/")
        try:
            sess = self._get_session()
            html = sess.get(host + "/", headers={
                "User-Agent": DDZJ_HEADERS["User-Agent"],
                "Accept": "text/html",
            }, timeout=12, verify=False).text or ""
            js_url = ""
            for cand in re.findall(r'src=["\']([^"\']+)["\']', html):
                if "assets/index" in cand and cand.endswith(".js"):
                    js_url = cand
                    break
            if not js_url:
                for cand in re.findall(r'src=["\']([^"\']+)["\']', html):
                    if "/assets/" in cand and cand.endswith(".js") and ("index" in cand or "app" in cand):
                        js_url = cand
                        break
            if not js_url:
                return False
            if not js_url.startswith("http"):
                js_url = host + ("/" if not js_url.startswith("/") else "") + js_url
            js = sess.get(js_url, headers={"User-Agent": DDZJ_HEADERS["User-Agent"]},
                          timeout=15, verify=False).text or ""
            sm = re.search(r'web-sign["\']?\s*[:=]\s*["\']([a-zA-Z0-9]+)["\']', js)
            if not sm:
                sm = re.search(r'=\s*["\'](ddtv[a-zA-Z0-9]+)["\']', js)
            cm = re.search(r'X-Client["\']?\s*[:=]\s*["\']([a-fA-F0-9]+)["\']', js)
            ok = False
            if sm:
                self._web_sign = sm.group(1)
                DDZJ_HEADERS["web-sign"] = self._web_sign
                ok = True
            if cm:
                self._x_client = cm.group(1)
                DDZJ_HEADERS["X-Client"] = self._x_client
                ok = True
            return ok
        except Exception:
            return False

    def _discover_domains(self):
        """从官方发布页 js/config.js 读取最新线路 —— 域名随时轮换，不能只靠硬编码"""
        try:
            r = self._get_session().get(
                DDZJ_PUBLISHER + "/js/config.js",
                headers=dict(DDZJ_HEADERS, Referer=DDZJ_PUBLISHER + "/"),
                timeout=10, verify=False)
            if r.status_code != 200:
                return []
            out = []
            for h in re.findall(r"host\s*:\s*['\"]([^'\"]+)['\"]", r.text or ""):
                h = h.strip().rstrip("/")
                if not h:
                    continue
                if not h.startswith("http"):
                    h = "https://" + h
                if h not in out:
                    out.append(h)
            return out
        except Exception:
            return []

    def _probe(self, h):
        """探测域名是否可用"""
        try:
            headers = dict(DDZJ_HEADERS, Referer=h + "/")
            if getattr(self, "_web_sign", None):
                headers["web-sign"] = self._web_sign
            if getattr(self, "_x_client", None):
                headers["X-Client"] = self._x_client
            r = self._get_session().get(
                h + "/api.php/web/index/home",
                headers=headers, timeout=10, verify=False)
            if r.status_code == 401 or (
                r.status_code == 200 and "signature" in (r.text or "").lower()
                and "categories" not in (r.text or "")
            ):
                if self._refresh_sign(h):
                    headers["web-sign"] = getattr(self, "_web_sign", headers.get("web-sign"))
                    headers["X-Client"] = getattr(self, "_x_client", headers.get("X-Client"))
                    r = self._get_session().get(
                        h + "/api.php/web/index/home",
                        headers=headers, timeout=10, verify=False)
            return r.status_code == 200 and "categories" in (r.text or "")
        except Exception:
            return False

    def _ensure_host(self):
        """确定可用域名：优先发布页最新线路，其次硬编码备份"""
        if self._host:
            return self._host
        seen = set()
        for h in self._discover_domains() + list(DDZJ_HOSTS):
            if h in seen:
                continue
            seen.add(h)
            if self._probe(h):
                self._host = h
                self.siteUrl = h
                return h
        self._host = DDZJ_HOSTS[0]
        self.siteUrl = self._host
        return self._host

    def _api(self, path, **params):
        """标准 JSON GET：非 200 直接抛异常（域名失效则丢弃缓存，下次重新发现）"""
        host = self._ensure_host()
        url = host + "/api.php/web" + path
        try:
            r = self._get_session().get(url, params=params, headers=self._build_headers(),
                                        timeout=20, verify=False)
        except Exception:
            self._host = None      # 域名可能已切换，丢弃缓存让下次重新发现
            raise
        # 签名失效时自动从前端 JS 刷新一次再重试
        if r.status_code == 401 or (
            r.status_code == 200 and isinstance(r.text, str)
            and "signature error" in r.text
        ):
            if self._refresh_sign(host):
                try:
                    r = self._get_session().get(url, params=params, headers=self._build_headers(),
                                                timeout=20, verify=False)
                except Exception:
                    self._host = None
                    raise
        if r.status_code != 200:
            self._host = None
            raise RuntimeError("HTTP %s: %s" % (r.status_code, url))
        try:
            return r.json()
        except Exception:
            self._host = None
            raise RuntimeError("非 JSON 响应: %s" % url)

    def _api_data(self, path, **params):
        j = self._api(path, **params)
        if j.get("code") not in (200, 1):
            raise RuntimeError("接口返回 code=%s msg=%s" % (j.get("code"), j.get("msg")))
        return j.get("data")

    # ───────── 分类缓存 ─────────
    def _load_cats(self):
        if self._cats:
            return self._cats
        d = self._api_data("/index/home")
        cats = []
        if isinstance(d, dict):
            for c in (d.get("categories") or []):
                tid = c.get("type_id")
                tname = c.get("type_name")
                if tname:
                    cats.append((str(tid), str(tname)))
        if not cats:
            cats = [("1", "电影"), ("2", "剧集"), ("3", "动漫"), ("4", "综艺")]
        self._cats = cats
        return cats

    def _tid_to_name(self, tid):
        for k, v in self._load_cats():
            if str(k) == str(tid):
                return v
        return ""

    # ───────── 卡片归一化 ─────────
    def _pick_raw_pic(self, v):
        """从条目里尽量捞出海报字段（兼容空/list/嵌套）"""
        if not isinstance(v, dict):
            return ""
        for key in ("vod_pic", "pic", "cover", "vod_pic_thumb", "vodPic", "poster", "img"):
            val = v.get(key)
            if val is None or val == "":
                continue
            if isinstance(val, (list, tuple)):
                for item in val:
                    if isinstance(item, dict):
                        s = item.get("url") or item.get("src") or item.get("vod_pic") or ""
                    else:
                        s = item
                    s = str(s or "").strip()
                    if s:
                        return s
                continue
            if isinstance(val, dict):
                s = val.get("url") or val.get("src") or val.get("vod_pic") or ""
                s = str(s or "").strip()
                if s:
                    return s
                continue
            s = str(val).strip()
            if s:
                return s
        return ""

    def _fix_pic(self, url, vid=None):
        """归一化海报URL并做多层修复。

        重要结论（2026-09 实测）：
        - 接口本身极少空海报（约 1/400）
        - 豆瓣防盗链 418，但站点常用反代（zxki/imgs.php/meilinvps）可直出
        - 反代 URL 不要解开成 doubanio 直链，否则端上必挂
        - 其余问题主要是 http 混合内容 + 少量死图床
        """
        vid_s = str(vid) if vid is not None and str(vid) != "" else None

        def _fallback():
            if vid_s and vid_s in DDZJ_PIC_FALLBACK:
                return self._force_https(DDZJ_PIC_FALLBACK[vid_s])
            return ""

        if url is None or url == "":
            return _fallback()

        if isinstance(url, (list, tuple)):
            url = next((x for x in url if x), "")
            if isinstance(url, dict):
                url = url.get("url") or url.get("src") or ""
        elif isinstance(url, dict):
            url = url.get("url") or url.get("src") or url.get("vod_pic") or ""

        u = str(url).strip()
        if not u or u.lower() in ("null", "none", "undefined", "n/a", "-"):
            return _fallback()

        # 协议相对路径
        if u.startswith("//"):
            u = "https:" + u
        elif u.startswith("/"):
            u = self._host_or_default().rstrip("/") + u

        try:
            from urllib.parse import urlparse
            p = urlparse(u)
            host = (p.netloc or "").lower()
            host_noport = host.split(":")[0]

            # ---------- 1) 可用图片反代：原样保留，只升 https ----------
            # 这些反代专门绕过豆瓣 418，解开反而挂
            if self._is_pic_proxy_host(host_noport, u):
                return self._force_https(u)

            # ---------- 2) 域名镜像（死图床 -> 镜像）----------
            mapped = DDZJ_PIC_HOST_MAP.get(host) or DDZJ_PIC_HOST_MAP.get(host_noport)
            if not mapped and host_noport.startswith("www."):
                mapped = DDZJ_PIC_HOST_MAP.get(host_noport[4:])
            if mapped:
                u2 = "https://" + mapped + (p.path or "/")
                if p.query:
                    u2 += "?" + p.query
                return u2

            # ---------- 3) 死图床 / 人工兜底 ----------
            dead = (
                host_noport in DDZJ_PIC_DEAD_HOSTS
                or host in DDZJ_PIC_DEAD_HOSTS
                or any(host_noport.endswith("." + d) or host_noport == d
                       for d in DDZJ_PIC_DEAD_HOSTS)
            )
            # 豆瓣直链（无反代）端上基本 418
            if "doubanio.com" in host_noport:
                dead = True

            if dead or (vid_s and vid_s in DDZJ_PIC_FALLBACK):
                fb = _fallback()
                if fb:
                    return fb
                if dead:
                    return ""

            # ---------- 4) 统一 https ----------
            return self._force_https(u)
        except Exception:
            fb = _fallback()
            return fb or self._force_https(u)

    @staticmethod
    def _is_pic_proxy_host(host, url=""):
        """站点用来绕过防盗链的图片反代，必须保留，不可 unwrap"""
        if not host:
            return False
        proxy_hosts = (
            "api.zxki.cn",
            "cms.meilinvps.com",
            "douban.gexuanyi.top",
            "image.baidu.com",  # /search/down?url=
        )
        if host in proxy_hosts or host.endswith(".zxki.cn"):
            return True
        # IP:port 反代 imgs.php
        if host.replace(".", "").replace(":", "").isdigit() or (
            host.count(".") == 3 and ":" in host
        ):
            if "imgs.php" in url or "img.php" in url or "url=" in url:
                return True
        if "img.php" in url or "imgs.php" in url or "imgfdl" in url:
            # 任意 host 的 img.php?url= 反代
            if "url=" in url:
                return True
        return False

    @staticmethod
    def _force_https(u):
        """海报链接尽量走 https，避免 TVBox/WebView 混合内容拦截。
        纯 IP:端口 反代往往没有证书，强行 https 会 SSLError，故保持原协议。
        """
        if not u:
            return u
        u = str(u).strip()
        if u.startswith("//"):
            return "https:" + u
        if not u.startswith("http://"):
            return u
        try:
            from urllib.parse import urlparse
            host = (urlparse(u).netloc or "").split(":")[0]
            # IPv4 裸 IP：多数反代无 SSL
            parts = host.split(".")
            if len(parts) == 4 and all(p.isdigit() for p in parts):
                return u
        except Exception:
            pass
        return "https://" + u[len("http://"):]

    def _card(self, v):
        vid = v.get("vod_id") if isinstance(v, dict) else None
        raw_pic = self._pick_raw_pic(v) if isinstance(v, dict) else ""
        return {
            "vod_id": str(vid or ""),
            "vod_name": str((v or {}).get("vod_name") or "").strip(),
            "vod_pic": self._fix_pic(raw_pic, vid),
            "vod_remarks": str((v or {}).get("vod_remarks") or "").strip(),
        }

    def _as_list(self, d):
        if isinstance(d, list):
            return d
        if isinstance(d, dict):
            for k in ("list", "items", "data", "videos"):
                if isinstance(d.get(k), list):
                    return d[k]
        return []

    # ───────── 六接口 ─────────
    def getName(self):
        return "多多追剧"

    def homeContent(self, filter=False):
        d = self._api_data("/index/home")
        result = {"class": []}
        # 分类
        if isinstance(d, dict):
            for c in (d.get("categories") or []):
                result["class"].append({
                    "type_id": str(c.get("type_id") or ""),
                    "type_name": str(c.get("type_name") or ""),
                })
        if not result["class"]:
            result["class"] = [{"type_id": tid, "type_name": nm}
                               for tid, nm in self._load_cats()]
        # 首页内容：推荐 + 各分类精选
        vlist = []
        seen = set()
        if isinstance(d, dict):
            for v in (d.get("recommend") or []):
                c = self._card(v)
                if c["vod_id"] and c["vod_id"] not in seen:
                    seen.add(c["vod_id"])
                    vlist.append(c)
            for c in (d.get("categories") or []):
                for v in (c.get("videos") or []):
                    card = self._card(v)
                    if card["vod_id"] and card["vod_id"] not in seen:
                        seen.add(card["vod_id"])
                        vlist.append(card)
        result["list"] = vlist
        self._cats = [(x["type_id"], x["type_name"]) for x in result["class"]]
        return result

    def categoryContent(self, tid, pg, filter, extend):
        try:
            pg = int(pg)
        except (TypeError, ValueError):
            pg = 1
        if pg < 1:
            pg = 1
        tname = self._tid_to_name(tid)
        params = {"page": pg, "sort": "hits"}
        if tname:
            params["type_name"] = tname          # 实测 type_name 才生效，type_id 会被忽略
        else:
            params["type_id"] = str(tid)
        for k in ("class", "area", "year"):
            if extend.get(k):
                params[k] = extend[k]
        lst = self._as_list(self._api_data("/filter/vod", **params))
        videos = [self._card(v) for v in lst if v.get("vod_id")]
        result = {"list": videos, "page": pg, "limit": len(videos)}
        if videos:
            # 站点不返回总数，给出"还有下一页"的宽松值，翻到空页自然停止
            result["pagecount"] = pg + 1
        return result

    def detailContent(self, ids):
        vid = (ids or [""])[0]
        d = self._api_data("/vod/get_detail", vod_id=vid)
        if isinstance(d, list):
            d = d[0] if d else {}
        d = d or {}
        play_from = str(d.get("vod_play_from") or "")
        play_url = str(d.get("vod_play_url") or "")
        # 线路黑名单过滤
        if DDZJ_SOURCE_BLACKLIST and play_from:
            srcs = play_from.split("$$$")
            urls = play_url.split("$$$")
            keep = [(s, u) for s, u in zip(srcs, urls) if s not in DDZJ_SOURCE_BLACKLIST]
            if keep:
                play_from = "$$$".join(x[0] for x in keep)
                play_url = "$$$".join(x[1] for x in keep)
        item = {
            "vod_id": str(d.get("vod_id") or vid),
            "vod_name": str(d.get("vod_name") or "").strip(),
            "vod_pic": self._fix_pic(self._pick_raw_pic(d) or d.get("vod_pic"), d.get("vod_id") or vid),
            "type_name": str(d.get("type_name") or self._tid_to_name(d.get("type_id")) or "").strip(),
            "vod_year": str(d.get("vod_year") or "").strip(),
            "vod_area": _join_val(d.get("vod_area")),
            "vod_remarks": str(d.get("vod_remarks") or "").strip(),
            "vod_actor": str(d.get("vod_actor") or "").strip(),
            "vod_director": str(d.get("vod_director") or "").strip(),
            "vod_lang": str(d.get("vod_lang") or "").strip(),
            "vod_class": _join_val(d.get("vod_class")),
            "vod_content": re.sub(r"<[^>]+>", " ", str(d.get("vod_content") or "")).strip(),
            "vod_play_from": play_from,
            "vod_play_url": play_url,
        }
        return {"list": [item], "pagecount": 1}

    def searchContent(self, key, quick=True, pg="1"):
        try:
            pg = int(pg)
        except (TypeError, ValueError):
            pg = 1
        if pg < 1:
            pg = 1
        lst = self._as_list(self._api_data("/search/index", wd=key, page=pg))
        videos = [self._card(v) for v in lst if v.get("vod_id")]
        result = {"list": videos, "page": pg}
        if videos:
            result["pagecount"] = pg + 1
        return result

    def playerContent(self, flag, id, vipFlags=None):
        """id 是加密串（非 http），需 POST decode/url 换真实地址"""
        code = str(id or "").strip()
        src = str(flag or "").strip()
        # 已经是直链（或 localProxy 回环），直接播放
        if code.startswith("http://") or code.startswith("https://"):
            return {"parse": 0, "playUrl": "", "url": code, "header": {}}
        if not code:
            return {"parse": 0, "playUrl": "", "url": "", "header": {}}
        # 形如 https://ddzj.local/?c=xxx&f=yyy 的包装形式也能还原
        m = re.search(r"[?&]c=([^&]+)", code)
        if m:
            from urllib.parse import unquote
            code = unquote(m.group(1))
            fm = re.search(r"[?&]f=([^&]+)", str(id))
            if fm and not src:
                src = unquote(fm.group(1))
        host = self._ensure_host()
        body = _ddzj_build_body(code, src)
        r = self._get_session().post(
            host + "/api.php/web/decode/url", data=body, timeout=15, verify=False,
            headers=dict(self._build_headers(),
                         **{"Content-Type": "application/x-protobuf",
                            "Accept": "application/x-protobuf"}))
        if r.status_code != 200:
            return {"parse": 0, "playUrl": "", "url": "",
                    "message": "解码服务 HTTP %s" % r.status_code}
        f = _pb_parse(r.content)
        ok = f.get(1)
        msg = (f.get(2) or b"").decode("utf-8", "replace")
        data = (f.get(3) or b"").decode("utf-8", "replace")
        if ok == 1 and data:
            return {"parse": 0, "playUrl": "", "url": data, "header": {}}
        # 解码失败：把原始串交回播放器，并把原因带出去
        return {"parse": 0, "playUrl": "", "url": code,
                "message": msg or "解码失败"}

    def localProxy(self, param):
        """直链无需特殊头，这里做通用转发兜底"""
        try:
            url = param.get("url") or ""
            if not url:
                return [200, "text/plain", ""]
            r = self._get_session().get(url, headers={
                "User-Agent": DDZJ_HEADERS["User-Agent"],
                "Referer": self._host_or_default() + "/",
            }, timeout=20, verify=False, stream=False)
            return [r.status_code,
                    r.headers.get("Content-Type", "application/octet-stream"),
                    r.content]
        except Exception as e:
            return [502, "text/plain", str(e)]
