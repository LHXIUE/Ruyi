# -*- coding: utf-8 -*-
"""
可可影视 APP (kkdy) —— OK影视 / Pyramid Python 源
=================================================

【配置】
    {
        "key": "kkdy_app",
        "name": "可可影视APP",
        "type": 3,
        "api": "./py/kkdy_app.py",
        "searchable": 1,
        "quickSearch": 1,
        "filterable": 1,
        "ext": ""
    }

【接口来源】
    逆向自官方 Android 客户端 (com.salmon.film.video), 服务端为
    https://vcache.ybsdkl.cn, 数据与网页版同源但走 JSON API,
    无需应对网页版的 cdndefend JS 挑战, 速度快且稳定。

【鉴权机制】
    1. 签名: sign = HMAC-SHA1(raw, HASH), 其中
           raw = method|path|queryString|ts|appId=..&deviceCreatedAt=..&deviceId=..|
       queryString 为参数按键名排序后以 & 连接; method 用小写 "get"。
    2. 响应加密: AES-256-CBC + PKCS7, 密钥/IV 来自客户端 libutil.so
       与网页 KKYS.Settings.KEYS 交叉验证一致。
    3. 解密用纯 Python 实现, 不依赖 OpenSSL/Crypto, 保证在手机上可运行。

【接口清单】
    /v6/vod/home.capi            首页 (banners + blocks)
    /vod/channel/list.capi       分类列表 (channelId, next=page=N, category, year, sort)
    /v2/vod/detail.capi          详情 (playSources 内含全部线路/剧集/m3u8 直链)
    /vod/playUnits.capi          备用播放接口
    /v3/vod/specialTopics.capi   专题分组列表 (每组 header 为专题分类, data 为专题)
    /vod/specialTopic/categoryTopics.capi  某专题分类下的专题列表
    /vod/specialTopic/vods.capi  专题影片列表 (specialTopicId, next=page=N)
    /vod/timeline.capi           时间线合集影片列表 (timelineId, next=page=N)
    /search/list                 搜索 (APP 内部路由, 服务端未开放, 故搜索走网页版)

    剧集结构: playSources[i].list[j].playUrls[0].url 即 m3u8, 且不需要 Referer。

【v2 修复说明】
    1. 分类页/详情页偶发空白
       接口调用由"单次"改为"最多 3 次重试 + 超时递增"; 分类首空时自动去掉
       筛选条件再拉一次; 首页接口异常时回退到电影分类第一页。
    2. 点进影片后播放空白(主因)
       服务端只有 selected 线路会返回真实剧集列表, 其余线路 list 恒为空
       (实测某剧 17 条线路里仅 1 条有数据, 其余 total 有值但 list 为 [])。
       原实现把 8 条线路全部列出却共用主线路的 episodeId, 用户切线路后
       episodePlayUrl 拿不到地址 -> 播放器收到空 url -> 白屏。
       现改为: 剧集串内嵌 siteId(vodId|siteId|episodeId), 播放时按线路取址,
       取不到自动回退主线路, 再回退到详情里缓存的直链。
    3. 串片(播放内容与选片不符)
       部分线路用主线路的 episodeId 去请求, 服务端会返回完全不相干影片的
       地址。新增 _same_vod 校验(jvods 路径须含 _vodId_), 拒绝后回退。
    4. 集数/线路显示不全
       线路上限 8 -> 12, 排序改为"有真实剧集的线路优先 + 集数多者优先"。
    5. 简介空白
       约三成影片 summary 为空, 现用类型/年份/地区兜底生成。
    6. 图片加载不出
       新增多域名自动探测, 并支持在 extend 里手动指定 imgHost。
    7. 选了分类/年代, 列表却显示成别的分类(v3)
       a) 展示串味: 列表接口不返回分类与地区字段, 只能从 labels 猜, 而
          labels 把"分类/地区/影片tag"混在一起(实测有 "KTV" "aaa" "儿子"
          "已收高清双语"), 原来取最后一位导致"选动作却显示科幻"。
          现改为: 白名单过滤脏标签 + 优先采用用户当前选中的分类/地区。
       b) 翻页掉筛选: 结果翻完后服务端会返回不相干的默认列表(实测"泰剧
          +2023"第3页变成欧美剧)。现按分类命中率判定, 失效即按到底处理,
          并记录每个筛选组合的末页, 超出直接返回空而不是脏数据。
       c) 年份误判: "更新至20261021期"被宽松正则提取成 2026, 已改为独立
          成词匹配。
    8. 新增"地区"筛选项(v3): 取值采集自详情 data.area 字段(服务端无字典
       接口), 实测命中 5/5, 且可与分类、年代三者组合生效。
    9. 筛选项去重(v3): 分类里删掉归属地区的词(日本电影、欧美)、同义项
       (内地剧≈大陆剧、海外剧≈欧美剧、中国动漫≈国产动漫、动漫≈动画、
        中国综艺≈大陆综艺、纪录≈纪录片)以及查不到结果的冷门项。
       地区里的"香港"和"中国香港"实测筛选结果交集为 0(库里两种写法是
       两批完全不同的片子), 直接删会漏片, 因此合并成同一个选项, 内部
       两种写法都查再交错合并, 界面只留一项但数据不丢。

【v4 专题说明】
    抓包确认的三个专题接口 (签名/加密与其它接口一致):
        /v3/vod/specialTopics.capi             专题总列表(按专题分类分组, next=page=N 翻页)
        /vod/specialTopic/categoryTopics.capi  指定专题分类下的专题(topicCategoryId)
        /vod/specialTopic/vods.capi            普通专题的影片列表(specialTopicId)
        /vod/timeline.capi                     时间线合集的影片列表(timelineId)
    专题分两种: 普通专题(如"邵氏经典影片")与时间线合集(如"漫威宇宙", 内部
    按系列再分组), 影片条目均带 vod/detail?vodId=N 链接, 播放与正片一致。
    实现:
        1. 新增"专题"频道(type_id=zhuanti), 首页筛选提供"专题分类"下拉
           (取自 specialTopics.capi 的分组 header, 运行时拉取+缓存)。
        2. 专题列表页: 未选分类 -> 全站专题平铺(翻页); 选了分类 -> 该分类
           下的专题(翻页)。专题卡片 vod_id 用 zt{id}/tl{id} 前缀区分类型。
        3. 点进专题 -> 自动翻完全部页(上限 50 页/500 部), 所有影片按顺序
           展示为"集"。多播放接口(默认 4 条, 影片超 200 部时自动收窄为 2 条):
             主线路: "片名$影片vodId"       -- 走该片主线路(详情第 1 条线路)
             线路N : "片名$影片vodId@N-1"   -- 走该片详情第 N 条线路的第 1 集
           线路是"懒解析"的: 详情页不逐片拉详情(300 部片会打爆接口), 只在
           用户点击时才取该片详情并按下标定位线路, 下标越界自动回落主线路,
           串片校验(_same_vod)与缓存直链兜底均照常生效。
        4. 广告位(_vod=ad_topic/ad_timeline/data 为字符串的组)一律跳过。

【extend 配置示例】(可选)
    {"api": "https://vcache.ybsdkl.cn", "imgHost": "https://vres.wkcyvs.cn"}

作者: 自动生成  日期: 2026-10-21  (v4 专题版)
"""

import sys
import os
import re
import json
import time
import hmac
import hashlib
import urllib.parse

# 让框架能找到 base 包 (部分环境 __file__ 未定义, 需容错)
try:
    sys.path.append('..')
    sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
except Exception:
    try:
        sys.path.append('..')
    except Exception:
        pass

try:
    import requests
except ImportError:
    requests = None

try:
    import urllib3
    urllib3.disable_warnings()
except Exception:
    pass

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider(object):
        def init(self, extend=""):
            pass

        def getName(self):
            return ""

        def isVideoFormat(self, url):
            return False

        def manualVideoCheck(self):
            return False

        def destroy(self):
            pass

        def fetch(self, url, headers=None, params=None, timeout=15, **kwargs):
            import requests as _rq
            return _rq.get(url, headers=headers, params=params,
                           timeout=timeout, verify=False)


# ==================================================================
#  纯 Python AES-256-CBC 解密 (PKCS7)
# ==================================================================

_SBOX = [
    0x63, 0x7c, 0x77, 0x7b, 0xf2, 0x6b, 0x6f, 0xc5, 0x30, 0x01, 0x67, 0x2b, 0xfe, 0xd7, 0xab, 0x76,
    0xca, 0x82, 0xc9, 0x7d, 0xfa, 0x59, 0x47, 0xf0, 0xad, 0xd4, 0xa2, 0xaf, 0x9c, 0xa4, 0x72, 0xc0,
    0xb7, 0xfd, 0x93, 0x26, 0x36, 0x3f, 0xf7, 0xcc, 0x34, 0xa5, 0xe5, 0xf1, 0x71, 0xd8, 0x31, 0x15,
    0x04, 0xc7, 0x23, 0xc3, 0x18, 0x96, 0x05, 0x9a, 0x07, 0x12, 0x80, 0xe2, 0xeb, 0x27, 0xb2, 0x75,
    0x09, 0x83, 0x2c, 0x1a, 0x1b, 0x6e, 0x5a, 0xa0, 0x52, 0x3b, 0xd6, 0xb3, 0x29, 0xe3, 0x2f, 0x84,
    0x53, 0xd1, 0x00, 0xed, 0x20, 0xfc, 0xb1, 0x5b, 0x6a, 0xcb, 0xbe, 0x39, 0x4a, 0x4c, 0x58, 0xcf,
    0xd0, 0xef, 0xaa, 0xfb, 0x43, 0x4d, 0x33, 0x85, 0x45, 0xf9, 0x02, 0x7f, 0x50, 0x3c, 0x9f, 0xa8,
    0x51, 0xa3, 0x40, 0x8f, 0x92, 0x9d, 0x38, 0xf5, 0xbc, 0xb6, 0xda, 0x21, 0x10, 0xff, 0xf3, 0xd2,
    0xcd, 0x0c, 0x13, 0xec, 0x5f, 0x97, 0x44, 0x17, 0xc4, 0xa7, 0x7e, 0x3d, 0x64, 0x5d, 0x19, 0x73,
    0x60, 0x81, 0x4f, 0xdc, 0x22, 0x2a, 0x90, 0x88, 0x46, 0xee, 0xb8, 0x14, 0xde, 0x5e, 0x0b, 0xdb,
    0xe0, 0x32, 0x3a, 0x0a, 0x49, 0x06, 0x24, 0x5c, 0xc2, 0xd3, 0xac, 0x62, 0x91, 0x95, 0xe4, 0x79,
    0xe7, 0xc8, 0x37, 0x6d, 0x8d, 0xd5, 0x4e, 0xa9, 0x6c, 0x56, 0xf4, 0xea, 0x65, 0x7a, 0xae, 0x08,
    0xba, 0x78, 0x25, 0x2e, 0x1c, 0xa6, 0xb4, 0xc6, 0xe8, 0xdd, 0x74, 0x1f, 0x4b, 0xbd, 0x8b, 0x8a,
    0x70, 0x3e, 0xb5, 0x66, 0x48, 0x03, 0xf6, 0x0e, 0x61, 0x35, 0x57, 0xb9, 0x86, 0xc1, 0x1d, 0x9e,
    0xe1, 0xf8, 0x98, 0x11, 0x69, 0xd9, 0x8e, 0x94, 0x9b, 0x1e, 0x87, 0xe9, 0xce, 0x55, 0x28, 0xdf,
    0x8c, 0xa1, 0x89, 0x0d, 0xbf, 0xe6, 0x42, 0x68, 0x41, 0x99, 0x2d, 0x0f, 0xb0, 0x54, 0xbb, 0x16,
]

_INV = [0] * 256
for _i, _v in enumerate(_SBOX):
    _INV[_v] = _i

_RCON = [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1b, 0x36]


def _xtime(a):
    return ((a << 1) ^ 0x1b) & 0xff if a & 0x80 else (a << 1)


def _gmul(a, b):
    r = 0
    while b:
        if b & 1:
            r ^= a
        a = _xtime(a)
        b >>= 1
    return r


# 预计算逆混合列用的 9/11/13/14 倍表, 避免逐字节循环
_M9 = [_gmul(x, 9) for x in range(256)]
_M11 = [_gmul(x, 11) for x in range(256)]
_M13 = [_gmul(x, 13) for x in range(256)]
_M14 = [_gmul(x, 14) for x in range(256)]


def _expand_key(key):
    nk = len(key) // 4
    nr = nk + 6
    w = [list(key[4 * i:4 * i + 4]) for i in range(nk)]
    for i in range(nk, 4 * (nr + 1)):
        t = list(w[i - 1])
        if i % nk == 0:
            t = t[1:] + t[:1]
            t = [_SBOX[x] for x in t]
            t[0] ^= _RCON[i // nk - 1]
        elif nk > 6 and i % nk == 4:
            t = [_SBOX[x] for x in t]
        pw = w[i - nk]
        w.append([pw[0] ^ t[0], pw[1] ^ t[1], pw[2] ^ t[2], pw[3] ^ t[3]])
    return w, nr


def _aes_decrypt_cbc(key, iv, data):
    """AES-CBC 解密 + PKCS7 去填充"""
    if not data or len(data) < 16:
        return b""
    w, nr = _expand_key(key)
    out = bytearray()
    prev = list(iv)
    n = len(data) - (len(data) % 16)
    for off in range(0, n, 16):
        blk = data[off:off + 16]
        # 状态: 列主序
        s = [[blk[4 * c + r] for c in range(4)] for r in range(4)]
        # 末轮密钥
        for c in range(4):
            wk = w[nr * 4 + c]
            for r in range(4):
                s[r][c] ^= wk[r]
        for rnd in range(nr - 1, -1, -1):
            # InvShiftRows: 第 r 行右移 r
            for r in range(1, 4):
                row = s[r]
                s[r] = row[-r:] + row[:-r]
            # InvSubBytes
            for r in range(4):
                row = s[r]
                s[r] = [_INV[row[0]], _INV[row[1]], _INV[row[2]], _INV[row[3]]]
            # AddRoundKey
            for c in range(4):
                wk = w[rnd * 4 + c]
                s[0][c] ^= wk[0]
                s[1][c] ^= wk[1]
                s[2][c] ^= wk[2]
                s[3][c] ^= wk[3]
            # InvMixColumns
            if rnd:
                for c in range(4):
                    a0, a1, a2, a3 = s[0][c], s[1][c], s[2][c], s[3][c]
                    s[0][c] = _M14[a0] ^ _M11[a1] ^ _M13[a2] ^ _M9[a3]
                    s[1][c] = _M9[a0] ^ _M14[a1] ^ _M11[a2] ^ _M13[a3]
                    s[2][c] = _M13[a0] ^ _M9[a1] ^ _M14[a2] ^ _M11[a3]
                    s[3][c] = _M11[a0] ^ _M13[a1] ^ _M9[a2] ^ _M14[a3]
        # 输出 + 去 CBC 链接
        for c in range(4):
            for r in range(4):
                out.append(s[r][c] ^ prev[4 * c + r])
        prev = list(blk)
    # 去 PKCS7
    if out:
        pad = out[-1]
        if 0 < pad <= 16 and pad <= len(out):
            out = out[:-pad]
    return bytes(out)


# ==================================================================
#  业务常量
# ==================================================================

API_BASE = "https://vcache.ybsdkl.cn"
IMG_BASE = "https://vres.wkcyvs.cn"
WEB_BASE = "https://www.kkys18.com"

APP_ID = "kkdy"
PACKAGE = "kkys18.com"
HASH_KEY = b"te@9fs#5tbf8#dx7zw8nx"
AES_KEY = b"ayt5wy5afwmwrpb19k9s3psx3dymyd0n"
AES_IV = b"b3t069ijy7pirw0j"

UA = "okhttp/4.9.0"
TIMEOUT = 15

CHANNELS = [
    ("1", "电影"),
    ("2", "连续剧"),
    ("3", "动漫"),
    ("4", "综艺"),
    ("6", "短剧"),
    ("zhuanti", "专题"),
]

GENRES = {
    "1": ["动作", "喜剧", "爱情", "科幻", "恐怖", "剧情", "战争", "犯罪",
          "动画", "奇幻", "武侠", "冒险", "悬疑", "惊悚", "历史", "古装",
          "家庭", "传记", "歌舞", "儿童", "职场", "短片"],
    "2": ["国产剧", "港台剧", "日韩剧", "欧美剧", "海外剧", "短剧"],
    "3": ["国产动漫", "日韩动漫", "欧美动漫", "动画电影"],
    "4": ["综艺", "纪录片"],
    "6": ["短剧"],
}

SORTS = [("1", "综合"), ("2", "最新"), ("3", "最热"), ("4", "评分")]


def _clean(txt):
    if not txt:
        return ""
    txt = re.sub(r"<br\s*/?>", "\n", txt, flags=re.I)
    txt = re.sub(r"<[^>]+>", "", txt)
    txt = (txt.replace("&nbsp;", " ").replace("&amp;", "&")
              .replace("&quot;", '"').replace("&#39;", "'")
              .replace("&lt;", "<").replace("&gt;", ">")
              .replace("&ldquo;", "“").replace("&rdquo;", "”"))
    return re.sub(r"[ \t\r\f\v]+", " ", txt).strip()

# ==================================================================
#  v2 修复补丁
# ------------------------------------------------------------------
#  修复问题:
#   1. 分类页偶发空白      -> 接口调用加重试, 首空回退, 图片域名自动探测
#   2. 点影片打开空白      -> 只列真实有剧集的线路, 剧集串内嵌 siteId,
#                             不再依赖进程内 _src_map 缓存
#   3. 剧集显示不全        -> 主线路完整剧集展开, 线路上限 8 -> 12,
#                             无独立剧集的线路自动回退主线路
#   4. 简介空白            -> 无 summary 时用类型/年份/地区兜底
#   5. 图片加载不出        -> 多域名探测 + 支持 extend 手动指定 imgHost
# ==================================================================

# 图片域名候选(按顺序探测, 取第一个可返回图片的)
IMG_HOSTS = [
    "https://vres.wkcyvs.cn",
    "https://www.kkys18.com",
]

MAX_SOURCES = 12      # 详情页最多展示的线路数
RETRY = 2             # 接口失败重试次数
TOPIC_PAGE_LIMIT = 50   # 专题详情最多翻页数(防死循环)
TOPIC_VOD_LIMIT = 500   # 专题详情最多收录影片数
TOPIC_LINE_COUNT = 4    # 专题详情默认提供的线路数(主线路 + N 条备用)

# ------------------------------------------------------------------
# 分类字典
# 服务端没有开放筛选字典接口(试过 filter.capi / category.capi 等均 40005),
# 列表接口也不返回选项。这里的取值是从各频道 items.labels[].url 里
# 采集出来的真实 category 参数值, 已剔除低频与脏标签
# (站点把影片 tag 和分类混在一个 labels 里, 会出现 "KTV" "aaa" "儿子" 之类)
# 实测: 用这些值筛选命中率 21/21, 且 category+year 组合可同时生效。
# ------------------------------------------------------------------
# 已剔除的重复项(括号为删除依据):
#   ch1 日本电影(属地区, 地区项已有"日本")、动画电影(与"动画"同义)
#   ch2 内地剧(与"大陆剧"筛选结果 Jaccard=0.50)、海外剧(与"欧美剧"同义)
#   ch3 中国动漫(与"国产动漫"同义)、动漫(与"动画"同义)、欧美(属地区)
#   ch4 中国综艺(与"大陆综艺"同义)、纪录(与"纪录片"同义)
#   ch6 宅斗/假千金/商战/家族/末世/系统/穿书/养成/娇妻系列/替嫁/脑洞/治愈/
#       美女总裁/带球跑(长尾冷门, 保留高频的 26 项)
GENRES = {
    "1": ["剧情", "动作", "喜剧", "爱情", "科幻", "恐怖", "悬疑", "惊悚",
          "犯罪", "战争", "家庭", "历史", "古装", "奇幻", "冒险", "武侠",
          "动画", "短片", "音乐", "运动", "儿童", "纪录片"],
    "2": ["国产剧", "大陆剧", "香港剧", "台湾剧", "日本剧", "韩国剧",
          "泰剧", "欧美剧", "剧情", "爱情", "家庭", "喜剧", "悬疑",
          "惊悚", "奇幻", "科幻", "恐怖", "武侠", "古装", "历史", "犯罪",
          "同性", "纪录片", "短片"],
    "3": ["国产动漫", "日本动漫", "日韩动漫", "欧美动漫", "动画", "动态漫画",
          "2D动画", "动画电影", "玄幻", "热血", "竞技", "搞笑", "恋爱",
          "治愈", "日常", "冒险", "科幻", "动作", "奇幻", "家庭", "爱情",
          "悬疑", "惊悚", "恐怖", "犯罪", "喜剧", "短片", "古装", "穿越",
          "重生", "爽文", "神怪", "异能", "励志", "神话"],
    "4": ["大陆综艺", "港台综艺", "日韩综艺", "欧美综艺", "歌舞", "真人秀",
          "脱口秀", "情感", "观察", "竞演", "音乐", "职场", "文化",
          "科技", "采访", "纪录片", "青春成长", "舞台艺术", "喜剧", "家庭"],
    "6": ["短剧", "甜宠", "豪门", "赘婿", "逆袭", "复仇", "穿越系列",
          "宫斗", "权谋", "虐恋", "闪婚", "隐婚", "萌宝", "团宠",
          "真千金", "神医", "修仙", "玄幻", "都市", "校园", "纯爱", "职场",
          "大女主", "打脸", "爽文"],
}

SORTS = [("1", "综合"), ("2", "最新"), ("3", "最热"), ("4", "评分")]

# 地区取值: 从详情接口 data.area 字段采集(服务端同样不提供字典接口)。
# 实测传这些值筛选命中率 5/5, 且可与 category / year 三者组合生效。
AREAS = ["中国大陆", "香港", "中国台湾", "日本", "韩国", "泰国",
         "新加坡", "马来西亚", "越南", "印度", "美国", "加拿大", "英国",
         "法国", "德国", "意大利", "西班牙", "俄罗斯", "澳大利亚"]

# 同一地区在库里存在两种写法, 实测 "中国香港" 与 "香港" 筛选结果交集为 0
# (是两批完全不同的片子), 直接删掉任一个都会漏片。所以界面上只保留一个
# 选项, 查询时两个值都查一遍再合并去重。
AREA_ALIAS = {
    "香港": ["中国香港", "香港"],
}

# 地区关键词: labels 里形如 "日本电影" "大陆综艺" "欧美动漫" 的都算地区
AREA_WORDS = ("大陆", "内地", "中国", "国产", "香港", "港台", "台湾", "澳门",
              "日本", "韩国", "欧美", "美国", "英国", "法国", "泰国", "印度",
              "新加坡", "马来西亚", "越南", "俄罗斯", "西班牙", "德国",
              "意大利", "加拿大", "澳大利亚", "海外")

# 合法分类白名单(各频道并集 + 通用类型词), labels 里不在其中的一律按脏标签丢弃
TYPE_OK = set()
for _v in GENRES.values():
    TYPE_OK.update(_v)
TYPE_OK.update(["剧情", "动作", "喜剧", "爱情", "科幻", "恐怖", "悬疑", "惊悚",
                "犯罪", "战争", "家庭", "历史", "古装", "奇幻", "冒险", "武侠",
                "动画", "短片", "音乐", "运动", "儿童", "纪录片", "记录片",
                "传记", "歌舞", "职场", "青春", "校园", "同性", "伦理", "励志",
                "治愈", "日常", "搞笑", "恋爱", "热血", "竞技", "玄幻", "穿越",
                "重生", "爽文", "神怪", "异能", "神话", "美食", "文化", "科技",
                "情感", "观察", "竞演", "脱口秀", "真人秀", "短剧", "动漫"])


class Spider(BaseSpider):

    # ---------------- 生命周期 ----------------

    def init(self, extend=""):
        e = (extend or "").strip()
        cfg = {}
        if e.startswith("{"):
            try:
                cfg = json.loads(e)
            except Exception:
                cfg = {}

        self.api = (cfg.get("api") or "").strip().rstrip("/") or API_BASE
        if not self.api.startswith("http"):
            self.api = "https://" + self.api

        self.img_host = (cfg.get("imgHost") or "").rstrip("/") or IMG_BASE
        self._img_checked = bool(cfg.get("imgHost"))

        self.device_id = "jBhI4St6bnqhUdhlECUhJ"
        self.device_created = "1792557507482"
        self._sess = None
        self._web = None
        # vid -> {"main": 主线路siteId, "urls": {episodeId: m3u8}, "eps": [(id,title,url)]}
        self._detail = {}
        # 筛选条件 -> 最后一页页码(服务端翻到末尾会返回空, 再翻会掉回默认列表)
        self._page_end = {}
        # 专题: zt/tl 前缀 id -> {name,pic,group,count,sum}; 专题分类缓存
        self._zt_names = {}
        self._zt_cats = None
        return True

    def getName(self):
        return "可可影视APP"

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def destroy(self):
        for s in (self._sess, self._web):
            try:
                if s is not None:
                    s.close()
            except Exception:
                pass
        self._sess = None
        self._web = None

    # ---------------- 网络层 ----------------

    def _session(self):
        if self._sess is None and requests is not None:
            s = requests.Session()
            s.headers.update({"User-Agent": UA, "Accept": "application/json",
                              "Connection": "keep-alive"})
            try:
                ad = requests.adapters.HTTPAdapter(pool_connections=8,
                                                   pool_maxsize=8, max_retries=0)
                s.mount("https://", ad)
                s.mount("http://", ad)
            except Exception:
                pass
            self._sess = s
        return self._sess

    def _sign(self, path, qs, ts, method="get"):
        extra = "appId=%s&deviceCreatedAt=%s&deviceId=%s" % (
            APP_ID, self.device_created, self.device_id)
        raw = "%s|%s|%s|%s|%s|" % (method, path, qs, ts, extra)
        return hmac.new(HASH_KEY, raw.encode("utf-8"), hashlib.sha1).hexdigest()

    def _once(self, path, params=None, timeout=TIMEOUT):
        """单次请求 + 解密, 失败返回 {}"""
        sess = self._session()
        if sess is None:
            return {}
        p = dict(params or {})
        for k, v in (("os", "android"), ("appId", APP_ID),
                     ("userChannel", "c1"), ("userLevel", "1")):
            p.setdefault(k, v)
        qs = "&".join("%s=%s" % (k, p[k]) for k in sorted(p))
        ts = str(int(time.time() * 1000))
        headers = {
            "appid": APP_ID,
            "package": PACKAGE,
            "deviceid": self.device_id,
            "devicecreatedat": self.device_created,
            "channelid": "c1",
            "os": "android",
            "userid": "",
            "x-token": "",
            "ts": ts,
            "sign": self._sign(path, qs, ts),
            "Accept": "application/json",
            "User-Agent": UA,
        }
        try:
            r = sess.get(self.api + path, params=p, headers=headers,
                         timeout=timeout, verify=False)
            body = r.content or b""
        except Exception:
            return {}

        try:
            return json.loads(body.decode("utf-8"))
        except Exception:
            pass
        try:
            txt = _aes_decrypt_cbc(AES_KEY, AES_IV, body).decode("utf-8")
            return json.loads(txt)
        except Exception:
            return {}

    def _call(self, path, params=None, retry=None):
        """带重试的接口调用。网络抖动是分类页/详情页空白的主因之一。"""
        retry = RETRY if retry is None else retry
        last = {}
        for i in range(retry + 1):
            r = self._once(path, params, timeout=TIMEOUT + i * 5)
            if r:
                code = str(r.get("code", ""))
                if code in ("200", "0", ""):
                    return r
                last = r
                # 业务错误码不重试, 直接返回让上层判断
                return r
            if i < retry:
                try:
                    time.sleep(0.3 * (i + 1))
                except Exception:
                    pass
        return last

    # ---------------- 数据转换 ----------------

    def _ensure_img_host(self, path, group):
        """首次取图时探测可用的图片域名, 结果缓存"""
        if self._img_checked or requests is None:
            return self.img_host
        self._img_checked = True
        p = path if str(path).startswith("/") else "/" + str(path)
        probe = ("/" + str(group) + p) if group else p
        for h in IMG_HOSTS:
            try:
                r = requests.get(h + probe, headers={"User-Agent": UA},
                                 timeout=8, verify=False, stream=True)
                ct = (r.headers.get("Content-Type") or "").lower()
                ok = (r.status_code == 200 and ("image" in ct or "octet" in ct))
                try:
                    r.close()
                except Exception:
                    pass
                if ok:
                    self.img_host = h
                    break
            except Exception:
                continue
        return self.img_host

    def _img(self, path, group):
        if not path:
            return ""
        path = str(path)
        if path.startswith("http"):
            return path
        host = self._ensure_img_host(path, group)
        if not path.startswith("/"):
            path = "/" + path
        if group:
            return "%s/%s%s" % (host, group, path)
        return host + path

    @staticmethod
    def _nm(x):
        if isinstance(x, dict):
            return x.get("name") or x.get("title") or x.get("id") or ""
        if x is None:
            return ""
        return str(x)

    def _nm_list(self, arr):
        if not arr:
            return ""
        if isinstance(arr, dict):
            return self._nm(arr)
        if isinstance(arr, (list, tuple)):
            return " / ".join([v for v in (self._nm(x) for x in arr) if v])
        return str(arr)

    @staticmethod
    def _epname(t):
        """剧集名里不能出现 $ # | (会破坏 TVBox 的播放串格式)"""
        t = str(t or "").replace("$", "").replace("#", "").replace("|", "").strip()
        return t or "正片"

    @staticmethod
    def _pick_year(*labels):
        """
        严格提取年份: 年份必须独立成词(前后不能再是数字)。
        综艺的 bottomLabel 常为 "更新至20261021期", 宽松正则会误提 "2026"。
        """
        for x in labels:
            for m in re.finditer(r"(?<!\d)(19\d{2}|20[0-2]\d)(?!\d)", str(x or "")):
                y = int(m.group(1))
                if 1930 <= y <= 2030:
                    return m.group(1)
        return ""

    @staticmethod
    def _pick_score(*labels):
        for x in labels:
            s = str(x or "").strip()
            if re.match(r"^\d+(\.\d+)?\s*分?$", s) and s:
                return s.rstrip("分")
        return ""

    def _split_labels(self, it):
        """
        站点的 labels 把"分类 / 地区 / 影片tag"混在一起, 实测脏值包括
        "KTV" "aaa" "儿子" "冷战" "已收高清双语" "America's" 等。
        这里只保留白名单内的分类, 并单独识别地区, 其余一律丢弃 ——
        否则用户选了"动作", 卡片上却显示成"科幻 / 已收高清双语"。
        """
        area, tags = "", []
        for lb in (it.get("labels") or []):
            raw = self._nm(lb)
            for part in re.split(r"[/、,，\s]+", str(raw)):
                p = (part or "").strip()
                if not p:
                    continue
                if not area and any(k in p for k in AREA_WORDS):
                    area = p
                if p in TYPE_OK and p not in tags:
                    tags.append(p)
        return area, tags

    def _to_vod(self, it, cat_hint="", area_hint=""):
        """
        列表条目 -> OK影视 vod。
        列表接口既不返回地区也不返回分类字段, 只能从 labels 里猜, 而 labels
        里脏值很多(实测选"日本"时有的条目 labels 里挂着"大陆综艺")。
        所以优先采用用户当前选中的筛选项, 保证"选什么就显示什么"。
        """
        tr = it.get("topRightLabel") or ""
        tl = it.get("topLeftLabel") or ""
        bl = it.get("bottomLabel") or ""
        area, tags = self._split_labels(it)
        if cat_hint or area_hint:
            # 同时选了分类和地区就都展示, 例如 "动作 美国"
            area = " ".join([x for x in (cat_hint, area_hint) if x])
        # 两者都没选时才用从 labels 猜出来的地区
        return {
            "vod_id": str(it.get("id", "")),
            "vod_name": (it.get("title") or "").strip(),
            "vod_pic": self._img(it.get("imagePath"), it.get("imageGroup")),
            "vod_remarks": bl or tr,
            "vod_year": self._pick_year(tl, tr, bl),
            "vod_area": area,
            "vod_score": self._pick_score(tl, tr),
            "vod_actor": "",
            "vod_director": "",
            "vod_content": "",
            "vod_tag": " / ".join(tags),
        }

    def _collect(self, data, out, seen, strict=True):
        if isinstance(data, dict):
            if "id" in data and "title" in data:
                url = str(data.get("url") or "")
                ok = ("vod/detail" in url) if strict else bool(data.get("imagePath") or url)
                if ok:
                    vid = str(data.get("id"))
                    if vid and vid not in seen:
                        seen.add(vid)
                        out.append(self._to_vod(data))
            for v in data.values():
                self._collect(v, out, seen, strict)
        elif isinstance(data, list):
            for v in data:
                self._collect(v, out, seen, strict)

    # ---------------- 专题 (v4) ----------------

    @staticmethod
    def _topic_ref(url):
        """
        从专题 url 里解析出 (类型, id):
            specialTopic/vods?specialTopicId=755 -> ("zt", "755")  普通专题
            vod/timeline?timelineId=617          -> ("tl", "617")  时间线合集
        """
        u = str(url or "")
        m = re.search(r"specialTopicId=(\d+)", u)
        if m:
            return "zt", m.group(1)
        m = re.search(r"timelineId=(\d+)", u)
        if m:
            return "tl", m.group(1)
        return "", ""

    def _topic_card(self, it):
        """
        专题条目(总列表/分类列表) -> vod 卡片。
        总列表条目字段: coverPathVertical/Horizontal, count="共N部"
        分类列表在 header 里: coverPathHorizontal, count=89(数字)
        vod_id 带 zt/tl 前缀, 名称/封面/简介记入 _zt_names 供详情兜底。
        """
        typ, tid = self._topic_ref(it.get("url"))
        if not tid:
            return None
        prefix = "zt" if typ == "zt" else "tl"
        key = prefix + tid
        name = (it.get("title") or "").strip()
        if not name:
            return None
        count = str(it.get("count") or "")
        if count.isdigit():
            count = "共%s部" % count
        pic = (it.get("coverPathVertical") or it.get("coverPathHorizontal") or "")
        group = (it.get("coverGroupVertical") or it.get("coverGroupHorizontal") or "")
        summary = _clean(it.get("summary") or "")
        self._zt_names[key] = {"name": name, "pic": pic, "group": group,
                               "count": count, "sum": summary}
        return {
            "vod_id": key,
            "vod_name": name,
            "vod_pic": self._img(pic, group),
            "vod_remarks": count,
            "vod_year": "", "vod_area": "", "vod_score": "",
            "vod_actor": "", "vod_director": "",
            "vod_content": summary,
            "vod_tag": "专题",
        }

    def _topic_categories(self):
        """专题分类下拉项(取自 specialTopics.capi 分组 header, 缓存)"""
        if self._zt_cats is not None:
            return self._zt_cats
        cats, seen = [], set()
        for pg in (1, 2):
            d = self._call("/v3/vod/specialTopics.capi",
                           {"next": "" if pg == 1 else "page=%d" % pg}, retry=1)
            dd = d.get("data") or {}
            for g in (dd.get("items") or []):
                if not isinstance(g, dict):
                    continue
                h = g.get("header") or {}
                cid = str(h.get("id") or "")
                nm = (h.get("title") or "").strip()
                if cid and nm and cid not in seen:
                    seen.add(cid)
                    cats.append({"n": nm, "v": cid})
            if not dd.get("next"):
                break
        self._zt_cats = cats
        return cats

    def _category_topics(self, pg, ext):
        """专题频道列表: 未选分类=全站专题平铺; 选了分类=该分类下的专题"""
        tc = (ext.get("tc") or "").strip()
        items, seen = [], set()
        if tc:
            d = self._call("/vod/specialTopic/categoryTopics.capi",
                           {"topicCategoryId": tc,
                            "next": "" if pg == 1 else "page=%d" % pg})
            dd = d.get("data") or {}
            groups = dd.get("items") or []
            # 分类接口按组返回, header 是专题, data 是预览影片, 只取 header
            for g in groups:
                if not isinstance(g, dict):
                    continue
                h = g.get("header")
                if isinstance(h, dict) and h.get("url"):
                    card = self._topic_card(h)
                    if card and card["vod_id"] not in seen:
                        seen.add(card["vod_id"])
                        items.append(card)
        else:
            d = self._call("/v3/vod/specialTopics.capi",
                           {"next": "" if pg == 1 else "page=%d" % pg})
            dd = d.get("data") or {}
            for g in (dd.get("items") or []):
                if not isinstance(g, dict):
                    continue
                arr = g.get("data")
                if not isinstance(arr, list):
                    continue   # 广告位 data 是字符串
                for it in arr:
                    if not isinstance(it, dict) or not it.get("url"):
                        continue
                    card = self._topic_card(it)
                    if card and card["vod_id"] not in seen:
                        seen.add(card["vod_id"])
                        items.append(card)
        nxt = bool(dd.get("next")) and bool(items)
        pagecount = (pg + 1) if nxt else pg
        limit = len(items) or 20
        return {"list": items, "page": pg, "pagecount": pagecount,
                "limit": limit, "total": limit * pagecount}

    def _topic_detail(self, ref):
        """
        专题 -> 影片合集详情。自动翻完全部分页(上限 TOPIC_PAGE_LIMIT 页),
        影片按顺序作为"集"展示, 播放串"片名$影片vodId"。纯数字 id 交给
        playerContent 走"主线路第一集"逻辑, 电影直接播, 剧集播第 1 集。
        """
        typ = "tl" if ref.startswith("tl") else "zt"
        tid = re.sub(r"\D", "", ref)
        if not tid:
            return {"list": []}
        meta = self._zt_names.get(ref) or {}

        eps, seen, nxt, pg = [], set(), "", 0
        while pg < TOPIC_PAGE_LIMIT and len(eps) < TOPIC_VOD_LIMIT:
            pg += 1
            if typ == "tl":
                d = self._call("/vod/timeline.capi",
                               {"timelineId": tid, "next": nxt})
            else:
                d = self._call("/vod/specialTopic/vods.capi",
                               {"specialTopicId": tid, "next": nxt})
            dd = d.get("data") or {}
            added = 0
            for g in (dd.get("items") or []):
                if not isinstance(g, dict):
                    continue
                # 普通专题: items 直接是影片; 时间线: 组内 data 是影片,
                # 广告位组(_vod=ad_*) 的 data 是字符串, 自动跳过
                arr = g.get("data") if typ == "tl" else [g]
                if not isinstance(arr, list):
                    continue
                for it in arr:
                    if not isinstance(it, dict):
                        continue
                    vid = str(it.get("id") or "")
                    title = (it.get("title") or "").strip()
                    if not vid or not title or vid in seen:
                        continue
                    if "vod/detail" not in str(it.get("url") or ""):
                        continue
                    seen.add(vid)
                    eps.append((title, vid))
                    added += 1
            nxt = str(dd.get("next") or "")
            if not nxt or not added:
                break

        if not eps:
            return {"list": []}
        # 影片太多时收窄线路数, 避免播放串过大
        n_lines = TOPIC_LINE_COUNT
        if len(eps) > 200:
            n_lines = max(2, TOPIC_LINE_COUNT - 2)
        play_from, play_url = [], []
        for k in range(n_lines):
            if k == 0:
                # 主线路: 纯 vodId, 由 playerContent 自动取该片主线路第 1 集
                seg = "#".join("%s$%s" % (self._epname(t), v) for t, v in eps)
                label = "主线路"
            else:
                # 备用线路: @k -> 取该片详情第 k 条线路(即第 k+1 条)的第 1 集
                seg = "#".join("%s$%s@%d" % (self._epname(t), v, k)
                               for t, v in eps)
                label = "线路%d" % (k + 1)
            play_from.append(label)
            play_url.append(seg)
        return {"list": [{
            "vod_id": ref,
            "vod_name": meta.get("name") or ("专题%s" % tid),
            "vod_pic": self._img(meta.get("pic"), meta.get("group")) if meta.get("pic") else "",
            "type_name": "专题",
            "vod_year": "", "vod_area": "", "vod_lang": "", "vod_score": "",
            "vod_actor": "", "vod_director": "",
            "vod_remarks": meta.get("count") or ("%d部" % len(eps)),
            "vod_content": meta.get("sum") or ("本专题共收录 %d 部影片。" % len(eps)),
            "vod_play_from": "$$$".join(play_from),
            "vod_play_url": "$$$".join(play_url),
        }]}

    # ---------------- 框架接口 ----------------

    def homeContent(self, filter):
        classes = [{"type_id": cid, "type_name": name} for cid, name in CHANNELS]
        result = {"class": classes}
        if filter:
            filters = {}
            for cid, _ in CHANNELS:
                if cid == "zhuanti":
                    # 专题: 只有"专题分类"一个筛选项, 取值运行时拉取
                    tc_vals = [{"n": "全部", "v": ""}]
                    try:
                        tc_vals += self._topic_categories()
                    except Exception:
                        pass
                    filters[cid] = [{"key": "tc", "name": "专题分类",
                                     "value": tc_vals}]
                    continue
                gs = GENRES.get(cid, [])
                filters[cid] = [
                    {"key": "category", "name": "分类",
                     "value": [{"n": "全部", "v": ""}] + [{"n": g, "v": g} for g in gs]},
                    {"key": "area", "name": "地区",
                     "value": [{"n": "全部", "v": ""}] + [{"n": a, "v": a} for a in AREAS]},
                    {"key": "year", "name": "年份",
                     "value": [{"n": "全部", "v": ""}] +
                              [{"n": str(y), "v": str(y)} for y in range(2026, 2004, -1)]},
                    {"key": "sort", "name": "排序",
                     "value": [{"n": n, "v": v} for v, n in SORTS]},
                ]
            result["filters"] = filters
        return result

    def homeVideoContent(self):
        d = self._call("/v6/vod/home.capi")
        out, seen = [], set()
        data = d.get("data") or {}
        if isinstance(data, dict):
            self._collect(data.get("blocks"), out, seen)
            if not out:
                self._collect(data.get("blocks"), out, seen, strict=False)
            if not out:
                self._collect(data, out, seen, strict=False)
        if not out:
            # 首页接口异常时回退到电影分类第一页, 避免首页空白
            try:
                out = (self.categoryContent("1", "1", False, {}) or {}).get("list") or []
            except Exception:
                out = []
        return {"list": out}

    def categoryContent(self, tid, pg, filter, extend):
        try:
            pg = int(pg or 1)
        except Exception:
            pg = 1
        if pg < 1:
            pg = 1
        ext = extend or {}
        # 专题频道单独处理(channelId 等参数不适用)
        if str(tid) == "zhuanti":
            try:
                return self._category_topics(pg, ext)
            except Exception:
                return {"list": [], "page": pg, "pagecount": pg,
                        "limit": 0, "total": 0}
        params = {"channelId": str(tid)}
        cat_hint, area_hint = "", ""
        for k in ("category", "year", "area", "language", "sort"):
            v = (ext.get(k) or "").strip()
            if v:
                if k == "sort" and v == "1":
                    continue
                if k == "category":
                    cat_hint = v
                elif k == "area":
                    area_hint = v
                    continue   # 地区可能对应多个实际取值, 下面单独拼
                params[k] = v

        # 同一地区在库里可能有多种写法("香港" / "中国香港"), 逐个查再合并去重
        area_vals = AREA_ALIAS.get(area_hint) or ([area_hint] if area_hint else [""])

        # 同一筛选条件下是否已到末尾: 服务端翻完返回 0 条, 再翻就掉回默认列表
        fkey = str(tid) + "|" + "&".join(
            "%s=%s" % (k, params[k]) for k in sorted(params)) + "|area=" + area_hint
        end = self._page_end.get(fkey) or 0
        if end and pg > end:
            return {"list": [], "page": pg, "pagecount": end,
                    "limit": 21, "total": 21 * end}

        data, seen_id = {}, set()
        buckets = []
        for av in area_vals:
            p = dict(params)
            if av:
                p["area"] = av
            if pg > 1:
                p["next"] = "page=%d" % pg
            d = self._call("/vod/channel/list.capi", p)
            dd = d.get("data") or {}
            one = []
            for it in (dd.get("items") or []):
                vid = str(it.get("id") or "")
                if vid and vid not in seen_id:
                    seen_id.add(vid)
                    one.append(it)
            buckets.append(one)
            if dd.get("next"):
                data = dd

        # 多种写法时交错取值, 保证每种写法都能出现在第一页
        # (直接截断会让后一种写法永远看不到)
        items = []
        i = 0
        while len(items) < 21:
            added = False
            for b in buckets:
                if i < len(b):
                    items.append(b[i])
                    added = True
                    if len(items) >= 21:
                        break
            if not added:
                break
            i += 1

        # 结果翻完后服务端会返回一堆不相干的默认数据(实测"泰剧+2023"第3页变成欧美剧)。
        # 按分类命中率判断本页筛选是否还生效, 失效就当作到底, 宁可显示"暂无数据"
        # 也不要显示成别的分类。
        if cat_hint and items:
            hit = 0
            for it in items:
                if cat_hint in self._split_labels(it)[1]:
                    hit += 1
            if hit * 2 < len(items):
                items, data = [], {}

        vods, seen = [], set()
        for it in items:
            vid = str(it.get("id") or "")
            if not vid or vid in seen:
                continue
            if not (it.get("title") or "").strip():
                continue
            seen.add(vid)
            vods.append(self._to_vod(it, cat_hint, area_hint))

        has_next = bool(data.get("next")) and bool(items)
        limit = len(vods) or 21
        pagecount = (pg + 1) if has_next else pg
        if not has_next:
            self._page_end[fkey] = pg
        return {
            "list": vods,
            "page": pg,
            "pagecount": pagecount,
            "limit": limit,
            "total": limit * pagecount,
        }

    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        raw = str(ids[0]).strip()
        # 专题详情: zt{id}=普通专题, tl{id}=时间线合集
        if raw.startswith("zt") or raw.startswith("tl"):
            try:
                return self._topic_detail(raw)
            except Exception:
                return {"list": []}
        mm = re.search(r"(\d+)", str(ids[0]))
        if not mm:
            return {"list": []}
        vid = mm.group(1)

        d = self._call("/v2/vod/detail.capi", {"vodId": vid})
        v = d.get("data") or {}
        if not v:
            return {"list": []}

        srcs = v.get("playSources") or []

        def _key(x):
            s = x.get("sort")
            return (0 if x.get("selected") else 1,
                    -(s if isinstance(s, int) else 0))

        # 只有 selected 线路会带真实剧集列表, 其余线路 list 恒为空
        # (实测 17 条线路里只有 1 条有 list), 因此按"是否有剧集"分开处理
        valid = sorted([x for x in srcs if x.get("list")], key=_key)
        others = sorted([x for x in srcs if not x.get("list")],
                        key=lambda x: (-(x.get("total") or 0),
                                       -(x.get("sort") or 0)))
        main = valid[0] if valid else (others[0] if others else None)
        eps = (main.get("list") if main else None) or []
        main_sid = str(main.get("siteId") or "") if main else ""

        # 缓存: 主线路 siteId + 每集直链(接口失败时兜底)
        info = self._detail.setdefault(vid, {"main": "", "urls": {}, "eps": []})
        info["main"] = main_sid
        info["urls"] = {}
        info["eps"] = []
        for e in eps:
            eid = str(e.get("id") or "")
            if not eid:
                continue
            url = ""
            pu = e.get("playUrls") or []
            if pu:
                url = (pu[0] or {}).get("url") or ""
            info["eps"].append((eid, self._epname(e.get("title")), url))
            if url:
                info["urls"][eid] = url

        play_from, play_url = [], []
        if info["eps"]:
            base = "#".join("%s$%s|%s|%s" % (t, vid, main_sid, eid)
                            for eid, t, _ in info["eps"])
            used = {}
            ordered = valid + others
            for s in ordered[:MAX_SOURCES]:
                sid = str(s.get("siteId") or "")
                if not sid:
                    continue
                label = str(s.get("name") or sid or "线路")
                if label in used:
                    used[label] += 1
                    label = "%s-%d" % (label, used[label])
                else:
                    used[label] = 1
                if s.get("list"):
                    seg = base
                else:
                    # 该线路无独立剧集: 复用主线路 episodeId 但带自己的 siteId,
                    # 播放取不到地址时自动回退主线路, 不会白屏
                    seg = "#".join("%s$%s|%s|%s" % (t, vid, sid, eid)
                                   for eid, t, _ in info["eps"])
                play_from.append(label)
                play_url.append(seg)

        directors = v.get("directors") or []
        actors = v.get("actors") or []
        # 详情的 labels 同样是"分类 + 地区 + tag"混排, 先按白名单过滤
        _darea, dtags = self._split_labels(v)
        labels = dtags or [self._nm(x) for x in (v.get("labels") or [])]
        labels = [x for x in labels if x]

        content = _clean(v.get("summary") or "")
        if not content:
            bits = []
            if labels:
                bits.append(" / ".join(labels))
            y = self._nm(v.get("year"))
            if y:
                bits.append(str(y))
            a = self._nm_list(v.get("area"))
            if a:
                bits.append(a)
            content = " · ".join([b for b in bits if b]) or (v.get("title") or "")

        vod = {
            "vod_id": vid,
            "vod_name": v.get("title", ""),
            "vod_pic": self._img(v.get("imagePath"), v.get("imageGroup")),
            "type_name": " ".join(labels),
            "vod_year": self._nm(v.get("year")),
            "vod_area": self._nm_list(v.get("area")),
            "vod_lang": self._nm_list(v.get("language")),
            "vod_remarks": v.get("bottomLabel", "") or v.get("topLeftLabel", ""),
            "vod_actor": self._nm_list(actors),
            "vod_director": self._nm_list(directors),
            "vod_content": content,
            "vod_score": str(v.get("score", "") or ""),
            "vod_play_from": "$$$".join(play_from),
            "vod_play_url": "$$$".join(play_url),
        }
        return {"list": [vod]}

    # ---------------- 播放 ----------------

    @staticmethod
    def _same_vod(u, vod_id):
        """
        校验取回的 m3u8 是否属于当前影片。
        实测: 用主线路的 episodeId 去请求其它线路时, 服务端会返回
        一个完全不相干影片的地址(如 2_386100_6295985), 直接播会串片。
        jvods 路径格式为 /.../{n}_{vodId}_{resId}/index.m3u8, 据此校验。
        """
        if not u:
            return False
        if "_%s_" % vod_id in u:
            return True
        # 非 jvods 结构(第三方直链)不做形态校验
        return "/jvods/" not in u

    def _pack(self, u):
        return {"parse": 0, "playUrl": "", "url": u,
                "header": {"User-Agent": UA,
                           "Referer": "https://www.kkys18.com/"}}

    def _empty(self):
        return {"parse": 0, "playUrl": "", "url": "",
                "header": {"User-Agent": UA}}

    def _resolve(self, vod_id, sid, ep_id):
        info = self._detail.get(vod_id) or {}
        if not info:
            # 进程重建后缓存丢失 -> 重拉详情重建
            try:
                self.detailContent([vod_id])
            except Exception:
                pass
            info = self._detail.get(vod_id) or {}

        main_sid = info.get("main") or ""
        cands = []
        for s in (sid, main_sid):
            if s and s not in cands:
                cands.append(s)

        fallback = ""
        for s in cands:
            r = self._call("/vod/episodePlayUrl",
                           {"vodId": vod_id, "siteId": s, "episodeId": ep_id},
                           retry=1)
            data = r.get("data") or []
            u = ""
            if isinstance(data, list) and data:
                u = (data[0] or {}).get("url") or ""
            if not u:
                continue
            if self._same_vod(u, vod_id):
                return self._pack(u)
            # 串片地址: 记下来, 只有万不得已才用
            if not fallback:
                fallback = u

        # 接口挂了 -> 用详情里缓存的直链兜底
        cached = (info.get("urls") or {}).get(ep_id) or ""
        if cached:
            return self._pack(cached)

        # 再兜底: 主线路第一集
        eps = info.get("eps") or []
        if eps and main_sid:
            eid0 = eps[0][0]
            if eid0 != ep_id:
                r = self._call("/vod/episodePlayUrl",
                               {"vodId": vod_id, "siteId": main_sid,
                                "episodeId": eid0}, retry=1)
                data = r.get("data") or []
                if isinstance(data, list) and data:
                    u = (data[0] or {}).get("url") or ""
                    if u and self._same_vod(u, vod_id):
                        return self._pack(u)
            u0 = eps[0][2] or ""
            if u0 and self._same_vod(u0, vod_id):
                return self._pack(u0)
        if fallback:
            return self._pack(fallback)
        return self._empty()

    def playerContent(self, flag, id, vipFlags):
        """
        id 格式: vodId|siteId|episodeId  (新)
                 vodId|episodeId        (旧版兼容)
                 vodId                  (专题: 该片主线路第 1 集)
                 vodId@k                (专题: 该片详情第 k 条线路第 1 集)
        """
        raw = str(id or "").strip()
        if raw.startswith("http"):
            return self._pack(raw)

        m = re.match(r"^(\d+)\|([^|\s]+)\|(\d+)$", raw)
        if m:
            return self._resolve(m.group(1), m.group(2), m.group(3))

        m = re.match(r"^(\d+)\|(\d+)$", raw)
        if m:
            return self._resolve(m.group(1), "", m.group(2))

        # 专题的备用线路: 取该片详情第 k 条线路的第 1 集
        mk = re.match(r"^(\d+)@(\d+)$", raw)
        if mk:
            return self._play_line(mk.group(1), int(mk.group(2)), flag, vipFlags)

        m3 = re.search(r"(\d+)", raw)
        if not m3:
            return self._empty()
        # 只给了 vodId -> 取主线路第一集
        try:
            d = self.detailContent([m3.group(1)])
        except Exception:
            d = {}
        lst = d.get("list") or []
        if not lst:
            return self._empty()
        first = (lst[0].get("vod_play_url") or "").split("$$$")[0].split("#")[0]
        if "$" not in first:
            return self._empty()
        return self.playerContent(flag, first.split("$", 1)[1], vipFlags)

    def _play_line(self, vod_id, idx, flag, vip):
        """
        按线路下标播放某片第一集(专题备用线路专用)。
        下标越界或该线路为空时自动回落主线路; 详情拉取失败返回空。
        """
        try:
            d = self.detailContent([vod_id])
        except Exception:
            d = {}
        lst = d.get("list") or []
        if not lst:
            return self._empty()
        segs = (lst[0].get("vod_play_url") or "").split("$$$")
        if not segs or not segs[0]:
            return self._empty()
        if idx < 0 or idx >= len(segs):
            idx = 0
        seg = segs[idx].split("#")[0]
        if "$" not in seg:
            seg = segs[0].split("#")[0]
        if "$" not in seg:
            return self._empty()
        return self.playerContent(flag, seg.split("$", 1)[1], vip)

    # ---------------- 搜索 (网页版兜底) ----------------

    def _web_session(self):
        if requests is None:
            return None
        if self._web is not None:
            return self._web
        s = requests.Session()
        s.headers.update({
            "User-Agent": ("Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"),
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
        })
        try:
            r = s.get(WEB_BASE + "/", timeout=TIMEOUT, verify=False)
            txt = r.text or ""
            if "cdndefend" in txt:
                mm = re.search(r"\[\s*'([0-9A-Fa-f]{40})'\s*", txt)
                if mm:
                    c = mm.group(1).upper()
                    n1 = int(c[0], 16)
                    for i in range(0, 300000):
                        dg = hashlib.sha1((c + str(i)).encode()).digest()
                        if dg[n1] == 0xB0 and dg[n1 + 1] == 0x0B:
                            s.cookies.set("cdndefend_js_cookie", c + str(i),
                                          domain="www.kkys18.com", path="/")
                            break
        except Exception:
            pass
        self._web = s
        return s

    def _web_token(self, sess):
        try:
            r = sess.get(WEB_BASE + "/", timeout=TIMEOUT, verify=False)
            mm = re.search(r'name="t"[^>]*value="([^"]*)"', r.text or "")
            if mm:
                return mm.group(1).replace("&", "&")
        except Exception:
            pass
        return ""

    def _web_search(self, key, pg):
        sess = self._web_session()
        if sess is None:
            return []
        t = self._web_token(sess)
        params = [("k", key)]
        if t:
            params.append(("t", t))
        if int(pg or 1) > 1:
            params.append(("page", str(pg)))
        html = ""
        for i in range(2):
            try:
                r = sess.get(WEB_BASE + "/search?" + urllib.parse.urlencode(params),
                             timeout=TIMEOUT + i * 5, verify=False)
                html = r.text or ""
                if 'search-result-item' in html:
                    break
            except Exception:
                pass
            # 挑战过期则重建会话
            try:
                self._web = None
                sess = self._web_session()
                if sess is None:
                    return []
                t = self._web_token(sess)
                params = [("k", key)] + ([("t", t)] if t else [])
                if int(pg or 1) > 1:
                    params.append(("page", str(pg)))
            except Exception:
                pass

        items, seen = [], set()
        marker = 'class="search-result-item"'
        pos = 0
        while True:
            i = html.find(marker, pos)
            if i < 0:
                break
            start = html.rfind("<a ", 0, i)
            nxt = html.find(marker, i + len(marker))
            blk = html[start: nxt if nxt > 0 else len(html)]
            pos = i + len(marker)

            mm = re.search(r'href="(/detail/(\d+)\.html)"', blk)
            if not mm:
                continue
            vid = mm.group(2)
            if vid in seen:
                continue
            seen.add(vid)

            mt = re.search(r'<div class="title">(.*?)</div>', blk, re.S)
            title = _clean(mt.group(1)) if mt else ""
            mc = re.search(r'<div class="search-result-item-header">\s*<div>(.*?)</div>', blk, re.S)
            cat = _clean(mc.group(1)) if mc else ""

            cover = ""
            for c in re.findall(r'(?:data-original|data-src|src)="([^"]+)"', blk):
                if "placeholder" in c or "/p/logo" in c:
                    continue
                if not re.search(r"\.(jpg|jpeg|png|webp|gif)", c, re.I):
                    continue
                cover = c if c.startswith("http") else ("https:" + c if c.startswith("//") else self.img_host + c)
            if cover.startswith("https://www.kkys18.com/vod1/"):
                cover = self.img_host + cover[len("https://www.kkys18.com"):]

            tags = [_clean(x) for x in re.findall(r"<span>(.*?)</span>", blk, re.S)]
            year = next((x for x in tags if re.fullmatch(r"(19|20)\d{2}", x)), "")

            items.append({
                "vod_id": vid,
                "vod_name": title,
                "vod_pic": cover,
                "vod_remarks": cat,
                "vod_year": year,
                "vod_area": "",
                "vod_score": "",
                "vod_actor": "",
                "vod_director": "",
                "vod_content": "",
                "vod_tag": "",
            })
        return items

    def searchContent(self, key, quick, pg="1"):
        items = self._web_search(key, pg)
        return {"list": items, "page": int(pg or 1)}

    def localProxy(self, param):
        try:
            param = param or {}
            url = param.get("url") or param.get("path")
            if not url:
                return ""
            if not url.startswith("http"):
                url = self.img_host + (url if url.startswith("/") else "/" + url)
            if requests is None:
                return b""
            idx = url.find("/", 8)
            tail = url[idx:] if idx > 0 else url
            hosts = [self.img_host] + [x for x in IMG_HOSTS if x != self.img_host]
            for h in hosts:
                try:
                    r = requests.get(h + tail, headers={"User-Agent": UA},
                                     timeout=20, verify=False, stream=True)
                    if r.status_code == 200:
                        return r.content
                except Exception:
                    continue
            return b""
        except Exception as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)
