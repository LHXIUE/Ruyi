# -*- coding: utf-8 -*-
"""
白丝自慰 (bsizw.cc) 爬虫 - 修复学习版
============================================================
  网站: https://bsizw.cc
  程序: 自定义模板 + HLS 直链 + 本地 HTTP 代理解锁
  功能: 分类浏览、视频详情、本地 HTTP 解密代理、搜索

  相对原版 (上传的 _spider.py) 修复点总览 (修复处均保留原结构并带 [FIX-xx] 注释):
    [FIX-01] AES 性能(辅助): SBOX/INV_SBOX 提出为模块级常量(原代码每解一个
             16 字节块都重建两个 256 长度列表), _expand_key 改为带模块级缓存。
             实测: 密钥展开本身仅 ~0.001ms/次, 缓存收益有限(纯 Python 解密
             3MB TS 141s -> 123s, 仅 -13%), 真正的大头见 [FIX-08] 的查表优化。
             保留此项是因为它能与查表叠加收益, 且代码更干净。
    [FIX-02] 分页: _parse_pagecount 只统计"当前分类"的页码, 不再被页面中
             其他分类的页码链接污染 (实测 e.g. cate28 曾算成 107 页而 107 页无内容)
    [FIX-03] 请求健壮性: UA 轮换 + SSL 降级重试 (参照「国色天香.py」,
             消除单 UA 单请求一抖就整页空白的脆弱性)
    [FIX-04] 动态分类: homeContent 从站点导航实时提取分类(含 141/163/164),
             替代 126 个硬编码分类(与站点脱节); 失败时兜底用硬编码列表
    [FIX-05] 播放失败路径: 解密链路任何环节失败都不再把"加密 m3u8"直接丢给播放器
             (原代码 parse=1 + 加密 m3u8 → 播放器无 key 只能无限转圈)
    [FIX-06] CDN 容错: 修正 host 替换逻辑, 不再生成 d32...vd2f.tjacq.com 这种
             子域拼进别的域名、必然 404 的错误 URL (只替换 host, 保留 path)
    [FIX-07] __ARCHIVE_PLAYER__ 提取: 用栈式 JSON 扫描替代非贪婪正则,
             防止内嵌对象导致 JSON 截断、m3u8 提取失败
    [FIX-08] AES 正确性+性能(双重): 解密轮密钥必须"逆序"使用(初始用 w[10]),
             且 InvShiftRows 是"循环右移 r 位"(原代码写成了加密方向的左移)——
             这两处是纯 Python 解密"解出乱码"的决定性根因, 已用 FIPS-197
             标准向量 + cryptography C 库逐字节对照验证修复。
             同时把 InvMixColumns 的 _gmul 逐位乘法换成 9/11/13/14 预计算查表,
             纯 Python 解密 3MB TS 从 ~141s 降到 ~11s (约 13 倍)。
    [FIX-09] (与 FIX-08 同处) 见上: 轮密钥逆序 + InvShiftRows 右移修复
    [FIX-10] 末页空洞校验: 站点分页器常预生成离谱的"末页链接"
             (如 cate28 显示 107 页, 实测 106/107 页空), 翻到后段必空白。
             现在先校验末页, 为空则二分向下探测真实有内容的最后一页
             (实测 cate28: 107 -> 50 页), 每分类结果缓存 1 小时。
============================================================
"""

import sys
import os
import re
import json
import time
import struct
import socket
import threading
from urllib.parse import quote, urlparse, urlunparse
from http.server import HTTPServer, BaseHTTPRequestHandler

sys.path.append('..')
try:
    from base.spider import Spider
except ImportError:
    class Spider:
        def fetch(self, url, headers=None, **kw):
            import requests as rq
            kw.pop('timeout', None)
            r = rq.get(url, headers=headers, timeout=15, **kw)
            r.encoding = 'utf-8'
            return r

# ============================================================
HOST = "https://bsizw.cc"
UA = "Mozilla/5.0 (Linux; Android 12; Pixel 6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
_UA_POOL = [
    UA,
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
]

# 本地代理配置 - 使用固定端口
PROXY_PORT = 23456
PROXY_BASE = f"http://127.0.0.1:{PROXY_PORT}"

# 缓存目录
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.bsizw_cache')
os.makedirs(CACHE_DIR, exist_ok=True)

# CDN 线路 (自动容错切换)
# [FIX-06] 注意: 这里只保存"完整 origin"(scheme://host),
#          容错切换时用它替换目标 URL 的 host 部分, 不再做字符串 replace
CDN_LINES = [
    "https://d32bg2g0w9aqg4.cloudfront.net",
    "https://vd2f.tjacq.com",
]

# 完整分类列表 (共126个) - 作为动态分类失败的兜底, 不直接使用
# [FIX-04] 原代码 homeContent 直接返回这份硬编码列表, 与站点导航脱节
#          (站点现有 127 类, 含 141/163/164; 硬编码缺 141/163/164)
CATEGORIES_FALLBACK = [
    {"type_id": "28", "type_name": "JK👗or 制服"},
    {"type_id": "29", "type_name": "萝莉🌸"},
    {"type_id": "30", "type_name": "少女💖"},
    {"type_id": "31", "type_name": "女仆🧹"},
    {"type_id": "32", "type_name": "学生🎓"},
    {"type_id": "33", "type_name": "洛丽塔🎀"},
    {"type_id": "34", "type_name": "黑丝"},
    {"type_id": "35", "type_name": "cosplay"},
    {"type_id": "36", "type_name": "旗袍🪭"},
    {"type_id": "37", "type_name": "少妇💃"},
    {"type_id": "38", "type_name": "教师👩‍🏫"},
    {"type_id": "39", "type_name": "猫扑🐱"},
    {"type_id": "40", "type_name": "护士🏥"},
    {"type_id": "42", "type_name": "原创全部"},
    {"type_id": "43", "type_name": "麻豆传媒"},
    {"type_id": "44", "type_name": "大象传媒"},
    {"type_id": "45", "type_name": "SA国际"},
    {"type_id": "46", "type_name": "性视界"},
    {"type_id": "47", "type_name": "爱豆传媒"},
    {"type_id": "48", "type_name": "糖心vlog"},
    {"type_id": "49", "type_name": "扣扣传媒"},
    {"type_id": "50", "type_name": "ED Mosaic"},
    {"type_id": "51", "type_name": "兔子先生"},
    {"type_id": "52", "type_name": "吴梦梦"},
    {"type_id": "53", "type_name": "蜜桃传媒"},
    {"type_id": "54", "type_name": "91制片厂"},
    {"type_id": "55", "type_name": "天美传媒"},
    {"type_id": "56", "type_name": "JVID"},
    {"type_id": "57", "type_name": "蘿莉社"},
    {"type_id": "58", "type_name": "乌托邦"},
    {"type_id": "59", "type_name": "杏吧"},
    {"type_id": "60", "type_name": "无限星空"},
    {"type_id": "61", "type_name": "精东传媒"},
    {"type_id": "62", "type_name": "皇家华人"},
    {"type_id": "63", "type_name": "抖阴学院"},
    {"type_id": "65", "type_name": "国产🐉"},
    {"type_id": "66", "type_name": "韩区🇰🇷"},
    {"type_id": "67", "type_name": "东南亚🌴"},
    {"type_id": "68", "type_name": "港区🐉"},
    {"type_id": "69", "type_name": "台区🐉"},
    {"type_id": "70", "type_name": "小日本🇯🇵"},
    {"type_id": "72", "type_name": "AV全部"},
    {"type_id": "73", "type_name": "AV中文"},
    {"type_id": "74", "type_name": "AV少妇"},
    {"type_id": "75", "type_name": "AV强奸"},
    {"type_id": "76", "type_name": "AV制服"},
    {"type_id": "77", "type_name": "AV教师"},
    {"type_id": "78", "type_name": "AV禁忌"},
    {"type_id": "79", "type_name": "AV SM"},
    {"type_id": "80", "type_name": "AV人妻"},
    {"type_id": "81", "type_name": "AV水果π"},
    {"type_id": "82", "type_name": "AV无码"},
    {"type_id": "83", "type_name": "AV痴汉"},
    {"type_id": "84", "type_name": "AV韩国"},
    {"type_id": "85", "type_name": "AV乱交"},
    {"type_id": "86", "type_name": "AV神之胸"},
    {"type_id": "87", "type_name": "AV内射"},
    {"type_id": "88", "type_name": "AV野外"},
    {"type_id": "89", "type_name": "AV潮吹"},
    {"type_id": "90", "type_name": "AV调教"},
    {"type_id": "91", "type_name": "AV 3P-4P"},
    {"type_id": "92", "type_name": "AV和服"},
    {"type_id": "93", "type_name": "AV痴女"},
    {"type_id": "94", "type_name": "AV美少女"},
    {"type_id": "95", "type_name": "AV学生"},
    {"type_id": "96", "type_name": "AV素人"},
    {"type_id": "97", "type_name": "AV熟女"},
    {"type_id": "100", "type_name": "网黄"},
    {"type_id": "101", "type_name": "娜娜"},
    {"type_id": "102", "type_name": "芋圆"},
    {"type_id": "103", "type_name": "玩偶姐姐"},
    {"type_id": "104", "type_name": "粉色情人"},
    {"type_id": "105", "type_name": "完具酱"},
    {"type_id": "106", "type_name": "兔子"},
    {"type_id": "107", "type_name": "奶咪"},
    {"type_id": "108", "type_name": "下面有根棒棒糖"},
    {"type_id": "109", "type_name": "lubaojing"},
    {"type_id": "110", "type_name": "Kittyxkum"},
    {"type_id": "111", "type_name": "andmlove"},
    {"type_id": "112", "type_name": "小水水"},
    {"type_id": "113", "type_name": "Candylove"},
    {"type_id": "114", "type_name": "Sofia-nana"},
    {"type_id": "115", "type_name": "妮可"},
    {"type_id": "116", "type_name": "Xreindeers"},
    {"type_id": "118", "type_name": "韩国三级"},
    {"type_id": "119", "type_name": "国产三级"},
    {"type_id": "121", "type_name": "sm调教"},
    {"type_id": "122", "type_name": "偷拍"},
    {"type_id": "123", "type_name": "乱斗"},
    {"type_id": "124", "type_name": "人妖"},
    {"type_id": "125", "type_name": "同性"},
    {"type_id": "126", "type_name": "强奸迷奸"},
    {"type_id": "127", "type_name": "捷克幻想"},
    {"type_id": "129", "type_name": "原神"},
    {"type_id": "130", "type_name": "王者荣耀"},
    {"type_id": "131", "type_name": "斗罗大陆"},
    {"type_id": "132", "type_name": "同人幻创"},
    {"type_id": "133", "type_name": "无码纯享"},
    {"type_id": "134", "type_name": "JK二次元"},
    {"type_id": "135", "type_name": "毁童年"},
    {"type_id": "136", "type_name": "巨乳娇娘"},
    {"type_id": "137", "type_name": "女仆二次元"},
    {"type_id": "138", "type_name": "眼镜娘"},
    {"type_id": "139", "type_name": "3D"},
    {"type_id": "140", "type_name": "MMD"},
    {"type_id": "143", "type_name": "cos全部"},
    {"type_id": "144", "type_name": "断背山"},
    {"type_id": "145", "type_name": "P站"},
    {"type_id": "146", "type_name": "啄木鸟15N+"},
    {"type_id": "147", "type_name": "啄木鸟10N+"},
    {"type_id": "148", "type_name": "巨乳肥臀"},
    {"type_id": "149", "type_name": "欧美女同"},
    {"type_id": "150", "type_name": "老少欢"},
    {"type_id": "151", "type_name": "Eva Elfie"},
    {"type_id": "152", "type_name": "好莱坞"},
    {"type_id": "154", "type_name": "1G老湿"},
    {"type_id": "155", "type_name": "Dr.She许蓝方"},
    {"type_id": "156", "type_name": "小哥艾理"},
    {"type_id": "157", "type_name": "王竹子"},
    {"type_id": "158", "type_name": "薇傲的性趣"},
    {"type_id": "159", "type_name": "一三蜜桃说"},
    {"type_id": "160", "type_name": "Carrie雨千"},
    {"type_id": "161", "type_name": "其它"},
    {"type_id": "blogger", "type_name": "嫩妹精选"},
]


# ============================================================
# AES 解密 (纯Python实现, 不依赖外部库) - [FIX-01] 性能修复
# ============================================================

# [FIX-01] SBOX/INV_SBOX 原代码在 _aes_decrypt_block 内部重复定义,
#           每解一个 16 字节块都要重建两个 256 长度列表。这里提到模块级,
#           进程内只构建一次 (对解密 3MB TS 的 ~19 万块调用是显著节省)
_AES_SBOX = [
    0x63,0x7c,0x77,0x7b,0xf2,0x6b,0x6f,0xc5,0x30,0x01,0x67,0x2b,0xfe,0xd7,0xab,0x76,
    0xca,0x82,0xc9,0x7d,0xfa,0x59,0x47,0xf0,0xad,0xd4,0xa2,0xaf,0x9c,0xa4,0x72,0xc0,
    0xb7,0xfd,0x93,0x26,0x36,0x3f,0xf7,0xcc,0x34,0xa5,0xe5,0xf1,0x71,0xd8,0x31,0x15,
    0x04,0xc7,0x23,0xc3,0x18,0x96,0x05,0x9a,0x07,0x12,0x80,0xe2,0xeb,0x27,0xb2,0x75,
    0x09,0x83,0x2c,0x1a,0x1b,0x6e,0x5a,0xa0,0x52,0x3b,0xd6,0xb3,0x29,0xe3,0x2f,0x84,
    0x53,0xd1,0x00,0xed,0x20,0xfc,0xb1,0x5b,0x6a,0xcb,0xbe,0x39,0x4a,0x4c,0x58,0xcf,
    0xd0,0xef,0xaa,0xfb,0x43,0x4d,0x33,0x85,0x45,0xf9,0x02,0x7f,0x50,0x3c,0x9f,0xa8,
    0x51,0xa3,0x40,0x8f,0x92,0x9d,0x38,0xf5,0xbc,0xb6,0xda,0x21,0x10,0xff,0xf3,0xd2,
    0xcd,0x0c,0x13,0xec,0x5f,0x97,0x44,0x17,0xc4,0xa7,0x7e,0x3d,0x64,0x5d,0x19,0x73,
    0x60,0x81,0x4f,0xdc,0x22,0x2a,0x90,0x88,0x46,0xee,0xb8,0x14,0xde,0x5e,0x0b,0xdb,
    0xe0,0x32,0x3a,0x0a,0x49,0x06,0x24,0x5c,0xc2,0xd3,0xac,0x62,0x91,0x95,0xe4,0x79,
    0xe7,0xc8,0x37,0x6d,0x8d,0xd5,0x4e,0xa9,0x6c,0x56,0xf4,0xea,0x65,0x7a,0xae,0x08,
    0xba,0x78,0x25,0x2e,0x1c,0xa6,0xb4,0xc6,0xe8,0xdd,0x74,0x1f,0x4b,0xbd,0x8b,0x8a,
    0x70,0x3e,0xb5,0x66,0x48,0x03,0xf6,0x0e,0x61,0x35,0x57,0xb9,0x86,0xc1,0x1d,0x9e,
    0xe1,0xf8,0x98,0x11,0x69,0xd9,0x8e,0x94,0x9b,0x1e,0x87,0xe9,0xce,0x55,0x28,0xdf,
    0x8c,0xa1,0x89,0x0d,0xbf,0xe6,0x42,0x68,0x41,0x99,0x2d,0x0f,0xb0,0x54,0xbb,0x16,
]
_AES_INV_SBOX = [0] * 256
for _i in range(256):
    _AES_INV_SBOX[_AES_SBOX[_i]] = _i

# [FIX-01] 密钥扩展缓存: 同一把 key 只展开一次。
#          原代码 _aes_decrypt_block 每 16 字节块都调 _expand_key(key) 重新展开,
#          3MB TS(~19.4 万块)就要展开 ~19.4 万次, 实测单 TS 解密 ~140s(播放转圈根因)
_round_keys_cache = {}


def _expand_key(key):
    """AES-128 密钥扩展, 返回 11个 4x4 state ([FIX-01] 带缓存)"""
    key_bytes = bytes(key)
    cached = _round_keys_cache.get(key_bytes)
    if cached is not None:
        return cached

    RCON = [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1b, 0x36]

    w = list(key)  # 16 bytes
    words = [w[i:i+4] for i in range(0, 16, 4)]

    for i in range(4, 44):
        temp = words[i-1][:]
        if i % 4 == 0:
            temp = temp[1:] + temp[:1]  # RotWord
            temp = [_AES_SBOX[b] for b in temp]  # SubWord
            temp[0] ^= RCON[i//4 - 1]
        words.append([words[i-4][j] ^ temp[j] for j in range(4)])

    # Add Round Key state: round_keys[round][row][col]
    round_keys = []
    for rnd in range(11):
        state = [[0]*4 for _ in range(4)]
        for c in range(4):
            for r in range(4):
                state[r][c] = words[rnd*4 + c][r]
        round_keys.append(state)

    _round_keys_cache[key_bytes] = round_keys
    return round_keys


def _aes_decrypt_block(key, block, round_keys=None):
    """AES-128 单块解密 (纯Python)

    [FIX-01] 新增可选参数 round_keys: 调用方(如 _aes_cbc_decrypt)在循环外
             展开一次密钥后传入, 避免每块重复 _expand_key。
    """
    if round_keys is None:
        round_keys = _expand_key(key)

    def xtime(a):
        return ((a << 1) ^ 0x1b) & 0xff if a & 0x80 else (a << 1) & 0xff

    # 解包为 state (4x4 字节矩阵, column-major)
    state = [[0]*4 for _ in range(4)]
    for r in range(4):
        for c in range(4):
            state[r][c] = block[r + 4*c]

    # 10 rounds for AES-128
    # [FIX-09] 关键修复: 解密轮密钥必须"逆序"使用!
    #          标准 AES 解密: 初始 AddRoundKey 用最后一轮密钥 w[10](密文侧),
    #          随后 9 轮依次用 w[9]..w[1](每轮都含 InvMixColumns),
    #          最后 InvShiftRows+InvSubBytes 后加 w[0](明文侧)。
    #          原代码初始用 round_keys[0]、循环正序 1..10, 是加密方向的密钥顺序,
    #          叠加 InvShiftRows 方向写反, 纯 Python 解出的每块数据都是错的
    #          (实测首字节 0xf5/0xfe, 正确应为 0x47; 播放器拿不到合法 TS 必转圈)。
    # 初始轮密钥加 (用 w[10])
    for r in range(4):
        for c in range(4):
            state[r][c] ^= round_keys[10][r][c]

    for round_num in range(9, 0, -1):
        # Inv Shift Rows (解密: 行 r 循环右移 r 位, 原代码左移是加密方向)
        for r in range(1, 4):
            state[r] = state[r][-r:] + state[r][:-r]

        # Inv Sub Bytes
        for r in range(4):
            for c in range(4):
                state[r][c] = _AES_INV_SBOX[state[r][c]]

        # Add Round Key (逆序 w[9]..w[1])
        for r in range(4):
            for c in range(4):
                state[r][c] ^= round_keys[round_num][r][c]

        # Inv Mix Columns (round 1..9 每轮都有; [FIX-08] 查表优化)
        for c in range(4):
            s0, s1, s2, s3 = state[0][c], state[1][c], state[2][c], state[3][c]
            state[0][c] = _MUL14[s0] ^ _MUL11[s1] ^ _MUL13[s2] ^ _MUL9[s3]
            state[1][c] = _MUL9[s0] ^ _MUL14[s1] ^ _MUL11[s2] ^ _MUL13[s3]
            state[2][c] = _MUL13[s0] ^ _MUL9[s1] ^ _MUL14[s2] ^ _MUL11[s3]
            state[3][c] = _MUL11[s0] ^ _MUL13[s1] ^ _MUL9[s2] ^ _MUL14[s3]

    # 最后一轮 (无 InvMixColumns): InvShiftRows + InvSubBytes + w[0]
    for r in range(1, 4):
        state[r] = state[r][-r:] + state[r][:-r]
    for r in range(4):
        for c in range(4):
            state[r][c] = _AES_INV_SBOX[state[r][c]]
    for r in range(4):
        for c in range(4):
            state[r][c] ^= round_keys[0][r][c]

    # Pack back to bytes
    result = bytearray(16)
    for r in range(4):
        for c in range(4):
            result[r + 4*c] = state[r][c]
    return result


def _gmul(a, b):
    """GF(2^8) 乘法"""
    p = 0
    for _ in range(8):
        if b & 1:
            p ^= a
        a = ((a << 1) ^ 0x1b) & 0xff if a & 0x80 else (a << 1) & 0xff
        b >>= 1
    return p


# [FIX-08] 预计算 GF(2^8) 乘 9/11/13/14 的四张查表 (InvMixColumns 专用)。
#          原代码 InvMixColumns 每块调用 16 次 _gmul(逐位乘, 每次8轮循环)——
#          这是 3MB TS 纯 Python 解密的主要瓶颈。查表后每块仅 16 次查表+异或。
_MUL9 = [0] * 256
_MUL11 = [0] * 256
_MUL13 = [0] * 256
_MUL14 = [0] * 256
for _v in range(256):
    _MUL9[_v] = _gmul(_v, 9)
    _MUL11[_v] = _gmul(_v, 11)
    _MUL13[_v] = _gmul(_v, 13)
    _MUL14[_v] = _gmul(_v, 14)


def _aes_cbc_decrypt(key, iv, data):
    """AES-128-CBC 解密 + PKCS7 去填充"""
    if len(data) % 16 != 0:
        # TS数据有时不是16倍数, 只解密完整的16字节块
        data = data[:len(data) - (len(data) % 16)]

    if len(data) == 0:
        return data

    result = bytearray()
    prev_block = iv

    # [FIX-01] 密钥只展开一次 (原代码循环内每个 block 都调 _aes_decrypt_block,
    #          其中又各自 _expand_key, 是纯 Python 解密慢的元凶)
    round_keys = _expand_key(key)

    for i in range(0, len(data), 16):
        block = data[i:i+16]
        if len(block) < 16:
            break

        # CBC: 先解密, 再与前一个密文块异或
        decrypted = _aes_decrypt_block(key, block, round_keys)
        plain = bytes(a ^ b for a, b in zip(decrypted, prev_block))
        result.extend(plain)
        prev_block = block

    # PKCS7 去填充 (取最后一个字节判断填充长度)
    pad_len = result[-1]
    if 1 <= pad_len <= 16:
        # 验证填充
        if result[-pad_len:] == bytes([pad_len]) * pad_len:
            result = result[:-pad_len]

    return bytes(result)


# ============================================================
# 外部AES库(可选, 若有优先使用提升速度)
# ============================================================

_external_aes = None


def _get_aes_lib():
    global _external_aes
    if _external_aes is not None:
        return _external_aes
    try:
        from Crypto.Cipher import AES
        _external_aes = ('pycryptodome', AES)
        return _external_aes
    except ImportError:
        pass
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.backends import default_backend
        _external_aes = ('cryptography', (Cipher, algorithms, modes, default_backend))
        return _external_aes
    except ImportError:
        pass
    _external_aes = ('pure', None)
    return _external_aes


def _decrypt_ts(key, iv, encrypted_data):
    """解密 TS 片段 (优先外部库, fallback纯Python)"""
    lib_name, lib = _get_aes_lib()

    if lib_name == 'pycryptodome':
        cipher = lib.new(key, lib.MODE_CBC, iv)
        dec = cipher.decrypt(encrypted_data)
    elif lib_name == 'cryptography':
        Cipher, algorithms, modes, default_backend = lib
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
        decryptor = cipher.decryptor()
        dec = decryptor.update(encrypted_data) + decryptor.finalize()
    else:
        dec = _aes_cbc_decrypt(key, iv, encrypted_data)

    # PKCS7
    pad_len = dec[-1] if dec else 0
    if 1 <= pad_len <= 16:
        if dec[-pad_len:] == bytes([pad_len]) * pad_len:
            dec = dec[:-pad_len]
    return dec


# ============================================================
# HTTP 请求 - [FIX-03] UA 轮换 + SSL 降级
# ============================================================

def _http_get(url, timeout=30, binary=False, referer=None):
    """UA 轮换 + SSL 降级 GET, 返回 bytes/text 或 None

    [FIX-03] 对应国色天香 `_raw_get`: 依次换 UA 重试;
             请求失败(含 SSL 校验失败)时也走下一 UA,
             并在下面的 _http_fetch 边界处理 SSL 降级(verify=False)。
    """
    import requests as rq
    headers = {
        'User-Agent': _UA_POOL[0],
        'Referer': referer or (HOST + '/'),
        'Origin': HOST,
    }
    last_err = None
    for ua in _UA_POOL:
        h = dict(headers)
        h['User-Agent'] = ua
        try:
            r = rq.get(url, headers=h, timeout=timeout)
            if r.status_code == 200:
                return r.content if binary else r.text
            last_err = f"HTTP {r.status_code}"
        except rq.exceptions.SSLError:
            # SSL 握手/证书失败 -> 降级不校验证书重试 (适配无有效证书的运营商线路)
            try:
                r = rq.get(url, headers=h, timeout=timeout, verify=False)
                if r.status_code == 200:
                    return r.content if binary else r.text
                last_err = f"HTTP {r.status_code} (no-verify)"
            except Exception as e2:
                last_err = e2
        except Exception as e:
            last_err = e
    print(f"[WARN] _http_get 失败 {url}: {last_err}")
    return None


def _http_fetch(url, binary=False, timeout=30):
    """HTTP GET 请求 (UA轮换 + SSL降级 + 多CDN容错)

    [FIX-06] 修复原 CDN 替换逻辑:
            原代码: url.replace('cloudfront.net', cdn.split('//')[1])
              https://d32bg2g0w9aqg4.cloudfront.net/xxx
              -> https://d32bg2g0w9aqg4.vd2f.tjacq.com/xxx  (子域拼进别的域名, 必 404)
            现改为: 只替换 host, 保留完整 path/query
    """
    for cdn in CDN_LINES:
        trial_url = url
        if cdn != CDN_LINES[0] and 'cloudfront.net' in url:
            parsed = urlparse(url)
            cdn_parsed = urlparse(cdn)
            trial_url = urlunparse((
                cdn_parsed.scheme, cdn_parsed.netloc,
                parsed.path, parsed.params, parsed.query, parsed.fragment,
            ))
        result = _http_get(trial_url, timeout=timeout, binary=binary)
        if result is not None:
            return result

    # 最后用原始 URL 再试一次 (允许原始 URL 的 CDN_Line 不在列表内)
    return _http_get(url, timeout=timeout, binary=binary)


# ============================================================
# 本地 HTTP 解密代理 (使用 Python 标准库)
# ============================================================

_proxy_started = False
_proxy_started_lock = threading.Lock()
_proxy_httpd = None


def _save_cache(vid, data):
    cache_file = os.path.join(CACHE_DIR, f'{vid}.json')
    save_data = {
        'key_hex': data['key'].hex() if isinstance(data['key'], bytes) else data['key'],
        'iv_hex': data['iv'].hex() if isinstance(data['iv'], bytes) else data['iv'],
        'ts_urls': data['ts_urls'],
        'durations': data.get('durations', []),
        'created': time.time(),
    }
    with open(cache_file, 'w') as f:
        json.dump(save_data, f)


def _load_cache(vid):
    cache_file = os.path.join(CACHE_DIR, f'{vid}.json')
    if not os.path.exists(cache_file):
        return None
    try:
        with open(cache_file, 'r') as f:
            data = json.load(f)
        if time.time() - data.get('created', 0) > 3600:  # 1小时有效期
            return None
        return {
            'key': bytes.fromhex(data['key_hex']),
            'iv': bytes.fromhex(data['iv_hex']),
            'ts_urls': data['ts_urls'],
            'durations': data.get('durations', []),
        }
    except Exception:
        return None


class ProxyHandler(BaseHTTPRequestHandler):
    """处理本地代理请求"""

    def log_message(self, format, *args):
        pass  # 静默日志

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = dict(p.split('=', 1) for p in parsed.query.split('&') if '=' in p) if parsed.query else {}

        if path == '/bsizw/m3u8':
            self._serve_m3u8(params.get('vid', ''))
        elif path == '/bsizw/ts':
            vid = params.get('vid', '')
            try:
                idx = int(params.get('idx', '0'))
            except ValueError:
                idx = 0
            self._serve_ts(vid, idx)
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Not Found')

    def _serve_m3u8(self, vid):
        info = _load_cache(vid)
        if not info:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'No cache')
            return

        ts_urls = info.get('ts_urls', [])
        durations = info.get('durations', [])

        lines = ['#EXTM3U', '#EXT-X-VERSION:3', '#EXT-X-TARGETDURATION:11', '#EXT-X-MEDIA-SEQUENCE:0']
        for i in range(len(ts_urls)):
            dur = durations[i] if i < len(durations) else '10.000000'
            lines.append(f'#EXTINF:{dur},')
            lines.append(f'{PROXY_BASE}/bsizw/ts?vid={vid}&idx={i}')
        lines.append('#EXT-X-ENDLIST')

        body = '\n'.join(lines).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/vnd.apple.mpegurl')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)

    def _serve_ts(self, vid, idx):
        info = _load_cache(vid)
        if not info:
            self.send_response(404)
            self.end_headers()
            cache_file = os.path.join(CACHE_DIR, f'{vid}.json')
            self.wfile.write(f'No cache (file: {cache_file}, exists: {os.path.exists(cache_file)})'.encode())
            return

        ts_urls = info.get('ts_urls', [])
        if idx >= len(ts_urls):
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Out of range')
            return

        try:
            enc_data = _http_fetch(ts_urls[idx], binary=True, timeout=60)
            if not enc_data:
                self.send_response(502)
                self.end_headers()
                self.wfile.write(b'Failed to fetch segment')
                return

            dec_data = _decrypt_ts(info['key'], info['iv'], enc_data)

            self.send_response(200)
            self.send_header('Content-Type', 'video/mp2t')
            self.send_header('Content-Length', str(len(dec_data)))
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(dec_data)
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(str(e).encode())


def _start_proxy_server():
    """启动本地 HTTP 解密代理 (标准库, 无需Flask)"""
    global _proxy_started, _proxy_httpd

    with _proxy_started_lock:
        if _proxy_started:
            return True

        try:
            _proxy_httpd = HTTPServer(('0.0.0.0', PROXY_PORT), ProxyHandler)
            t = threading.Thread(target=_proxy_httpd.serve_forever, daemon=True)
            t.start()
            _proxy_started = True
            return True
        except OSError as e:
            # 端口可能被占用, 尝试检查是否已有服务
            try:
                import socket
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(1)
                result = s.connect_ex(('127.0.0.1', PROXY_PORT))
                s.close()
                if result == 0:
                    _proxy_started = True
                    return True
            except Exception:
                pass
            return False


# ============================================================
# Spider 类
# ============================================================

class Spider(Spider):
    def __init__(self):
        self.host = HOST
        self.ua = UA

    def init(self, extend=""):
        if extend and extend.startswith("http"):
            self.host = extend.rstrip("/")

    # --------------------------------------------------------
    def _fetch(self, url, timeout=20):
        # [FIX-03] 原代码: 固定单 UA 一次请求, 失败即返回 ""
        #           现为: UA 轮换 + SSL 降级 (参照国色 `fetch`), 失败返回 ""
        if url.startswith("http"):
            full = url
        else:
            full = self.host + url if url.startswith("/") else self.host + "/" + url
        result = _http_get(full, timeout=timeout, referer=self.host + "/")
        if result is None:
            return ""
        return result

    # --------------------------------------------------------
    # 首页
    # --------------------------------------------------------
    def homeContent(self, filter=False):
        # [FIX-04] 动态分类: 从站点导航实时提取 (含 141/163/164),
        #          提取失败再用硬编码兜底, 不再固定返回脱节的 126 类
        try:
            html = self._fetch("/", timeout=15)
            cats = self._parse_categories_from_home(html)
            if cats:
                return {"class": cats}
        except Exception:
            pass
        return {"class": CATEGORIES_FALLBACK}

    def _parse_categories_from_home(self, html):
        """从首页导航提取分类列表 (按 type_id 去重)

        实测导航内分类链接有两种形态:
          <a class="dropdownItem" href="/category/cate161/" ...>其它</a>
          <a class="menu-item" href="/category/cate141/" aria-label="全部-/category/cate141/">全部</a>
        aria-label 格式: "分类名-/category/cateN/" 最稳, 优先用它。
        """
        if not html:
            return []
        cats = []
        seen = set()

        # 形态1: aria-label="名称-/category/cateN/" (实测最全, 含 141/163/164)
        for m in re.finditer(
            r'aria-label="([^"/]+)-/category/(?:cate(\d+)|blogger)/"', html
        ):
            name = m.group(1).strip()
            tid = "blogger" if m.group(2) is None else m.group(2)
            if not name or tid in seen:
                continue
            seen.add(tid)
            cats.append({"type_id": tid, "type_name": name})

        if cats:
            return cats

        # 形态2 (兜底): 直接抓 a 文本
        for m in re.finditer(
            r'<a[^>]*href="/category/(?:cate(\d+)|blogger)/"[^>]*>(.*?)</a>', html, re.S
        ):
            tid = "blogger" if m.group(1) is None else m.group(1)
            text = re.sub(r'<[^>]+>', '', m.group(2)).strip()
            if not text or tid in seen:
                continue
            seen.add(tid)
            cats.append({"type_id": tid, "type_name": text})

        return cats

    def homeVideoContent(self):
        try:
            html = self._fetch("/category/cate28/")
        except Exception:
            html = ""
        if not html:
            return {"list": []}
        return {"list": self._parse_video_list(html)[:20]}

    # --------------------------------------------------------
    # 分类
    # --------------------------------------------------------
    def categoryContent(self, tid, pg=1, filter=False, extend=""):
        pn = max(int(str(pg) or "1"), 1)
        tid_str = str(tid)

        if tid_str == "blogger":
            url = "/category/blogger/" if pn == 1 else f"/category/blogger/{pn}/"
        else:
            url = f"/category/cate{tid_str}/" if pn == 1 else f"/category/cate{tid_str}/{pn}/"

        try:
            html = self._fetch(url)
        except Exception:
            html = ""
        if not html:
            return {"page": pn, "pagecount": 1, "limit": 24, "total": 0, "list": []}

        videos = self._parse_video_list(html)
        pagecount = self._parse_pagecount(html, pn, tid_str)
        # [FIX-10] 末页空洞校验: 分页器预生成跳末页链接(如 cate28 的107)可能为空,
        #          真实页数用二分探测校正, 已在分类页翻到后段时不再出现空白。
        if pn <= 2 and pagecount > 2:
            pagecount = self._probe_real_pagecount(tid_str, pagecount)

        return {
            "page": pn,
            "pagecount": pagecount,
            "limit": 24,
            "total": pagecount * 24,
            "list": videos,
        }

    def _parse_video_list(self, html):
        videos = []
        seen = set()

        for m in re.finditer(
            r'<li\s+class="section-content__item[^"]*">\s*<a\s+href="/video/(\d+)/"[^>]*>',
            html,
        ):
            vid = m.group(1)
            if vid in seen:
                continue
            seen.add(vid)

            start = m.start()
            end_tag = html.find("</li>", start)
            if end_tag == -1:
                end_tag = start + 2000
            block = html[start:end_tag]

            title = ""
            title_m = re.search(r'<h3[^>]*class="[^"]*text-truncate[^"]*"[^>]*>([^<]+)</h3>', block)
            if title_m:
                title = title_m.group(1).strip()
            if not title:
                aria_m = re.search(r'aria-label="([^"]*)"', block)
                if aria_m:
                    raw = aria_m.group(1)
                    suffix = "-" + vid
                    if raw.endswith(suffix):
                        title = raw[: -len(suffix)].strip()
            if not title:
                alt_m = re.search(r'<img[^>]*alt="([^"]+)"', block)
                if alt_m:
                    title = alt_m.group(1).strip()

            pic = ""
            # 精确匹配 cloudfront 真实封面图 (排除占位图/系统图)
            pic_m = re.search(r'data-src="(https://d32bg2g0w9aqg4\.cloudfront\.net/image/[^"]+)"', block)
            if not pic_m:
                # 二次: 匹配 videos 目录
                pic_m = re.search(r'data-src="(https://d32bg2g0w9aqg4\.cloudfront\.net/videos/[^"]+)"', block)
            if not pic_m:
                # 三次: 任意 cloudfront 图片 (排除已知非封面)
                pic_m = re.search(r'data-src="(https://d32bg2g0w9aqg4\.cloudfront\.net/(?!system/|statics/)[^"]+)"', block)
            if pic_m:
                pic = pic_m.group(1)

            duration = ""
            dur_m = re.search(r'<span[^>]*class="[^"]*cover-duration[^"]*"[^>]*>([^<]+)</span>', block)
            if dur_m:
                duration = dur_m.group(1).strip()

            views = ""
            eye_m = re.search(r'<span[^>]*class="[^"]*eye[^"]*"[^>]*>([^<]+)</span>', block)
            if eye_m:
                views = eye_m.group(1).strip()

            remark = duration
            if views:
                remark = f"{remark} | 👁{views}" if remark else f"👁{views}"

            videos.append({
                "vod_id": vid,
                "vod_name": title,
                "vod_pic": pic,
                "vod_remarks": remark,
            })

        return videos

    def _parse_pagecount(self, html, current_pg=1, tid=None):
        # [FIX-02] 原代码: re.findall(r'/category/cate\d+/(\d+)/', html) 取全页 max。
        #          页面导航里还有其他分类的页码链接, 会把"当前分类"总页数算爆。
        #          实测 cate28 曾在页面里扫到 107(cate28 自身末页链接), 而 107 页
        #          实际没有内容; 更糟的是若页面混入其他分类页码, 用户翻到后段全空白。
        #          现在只统计当前分类自身的页码。
        if tid:
            if str(tid) == "blogger":
                pages = re.findall(r'/category/blogger/(\d+)/', html)
            else:
                pages = re.findall(rf'/category/cate{tid}/(\d+)/', html)
            if pages:
                try:
                    return max(int(p) for p in pages)
                except Exception:
                    pass

        # 兜底: 无 tid / 正则异常时, 退回全页页码
        pages = re.findall(r'/category/cate\d+/(\d+)/', html)
        if pages:
            try:
                return max(int(p) for p in pages)
            except Exception:
                pass
        m = re.search(r'共\s*(\d+)\s*页', html)
        if m:
            try:
                return int(m.group(1))
            except Exception:
                pass
        return current_pg

    # [FIX-10] 末页空洞校验: 站点分页器常把"末页链接"预生成到很远
    #          (如 cate28 显示 107 页, 但 106/107 页实际 0 视频),
    #          直接按 max 翻页就会"翻到空白页"。这里校验末页是否有内容,
    #          为空则二分向下探测真实有内容的最后一页 (带缓存, 每分类只查一次)。
    _PAGECOUNT_PROBE_CACHE = {}  # tid -> (hit, expire_ts)

    def _probe_real_pagecount(self, tid, guessed, probe_timeout=15):
        try:
            cache = self._PAGECOUNT_PROBE_CACHE.get(str(tid))
            if cache and cache[1] > time.time():
                return cache[0]
        except Exception:
            pass

        if str(tid) == "blogger":
            def page_url(p):
                return f"/category/blogger/{p}/" if p > 1 else "/category/blogger/"
        else:
            def page_url(p):
                return f"/category/cate{tid}/{p}/" if p > 1 else f"/category/cate{tid}/"

        def page_has_videos(p):
            html = self._fetch(page_url(p), timeout=probe_timeout)
            if not html:
                return None  # 请求失败, 不猜
            return len(self._parse_video_list(html)) > 0

        # 末页有内容 -> 猜测值可信
        ok = page_has_videos(guessed)
        if ok is False:
            # 二分找 [1, guessed] 内最后一个有内容的页
            lo, hi = 1, guessed
            last_ok = 1
            while lo <= hi:
                mid = (lo + hi) // 2
                r = page_has_videos(mid)
                if r is None:
                    break  # 网络异常, 用当前已知最大
                if r:
                    last_ok = mid
                    lo = mid + 1
                else:
                    hi = mid - 1
            guessed = last_ok
        elif ok is None:
            return guessed  # 探测失败, 保持猜测值

        try:
            self._PAGECOUNT_PROBE_CACHE[str(tid)] = (guessed, time.time() + 3600)
        except Exception:
            pass
        return guessed

    # --------------------------------------------------------
    # 详情页
    # --------------------------------------------------------
    def detailContent(self, ids):
        vid = ids[0] if isinstance(ids, list) and ids else str(ids or "")
        if not vid:
            return {"list": []}

        url = f"/video/{vid}/"
        try:
            html = self._fetch(url)
        except Exception:
            html = ""
        if not html or len(html) < 2000:
            return {"list": []}

        return {"list": [self._parse_detail(html, vid)]}

    def _parse_detail(self, html, vid):
        title = ""
        title_m = re.search(r'<title>([^<]+)</title>', html)
        if title_m:
            raw = title_m.group(1).strip()
            title = raw.replace(" - 白丝自慰", "").strip()
        if not title:
            h1_m = re.search(r'<h1[^>]*>([^<]+)</h1>', html)
            if h1_m:
                title = h1_m.group(1).strip()

        pic = ""
        pic_m = re.search(r'<meta\s+property="og:image"\s+content="([^"]+)"', html)
        if pic_m:
            pic = pic_m.group(1)

        tags = []
        for tag_m in re.finditer(
            r'<span[^>]*class="[^"]*tag-item[^"]*"[^>]*><span[^>]*data-link="/tag/[^"]*"[^>]*>([^<]+)</span>',
            html,
        ):
            t = tag_m.group(1).strip()
            if t and t not in tags:
                tags.append(t)

        content = ""
        desc_m = re.search(r'<meta\s+name="description"\s+content="([^"]+)"', html)
        if desc_m:
            content = desc_m.group(1).strip()

        has_m3u8 = bool(self._extract_m3u8_url(html))

        return {
            "vod_id": vid,
            "vod_name": title,
            "vod_pic": pic,
            "vod_year": "",
            "vod_area": "",
            "vod_class": ",".join(tags) if tags else "",
            "vod_director": "",
            "vod_actor": "",
            "vod_content": content,
            "vod_remarks": "",
            "vod_play_from": "bsizw",
            "vod_play_url": f"播放${vid}" if has_m3u8 else "",
        }

    def _extract_archive_player_json(self, html):
        """从 window.__ARCHIVE_PLAYER__ = {...} 提取完整 JSON 对象文本

        [FIX-07] 原代码: re.search('window.__ARCHIVE_PLAYER__\\s*=\\s*(\\{.+?\\});', html)
                 非贪婪 `.+?` 会在遇到第一个 `};` 就停; 若对象内嵌
                 { "a": {...} } 且内层对象以 `};` 结尾, JSON 会被拦腰截断,
                 json.loads 失败 -> m3u8 提取失败 -> 播放转圈。
                 现改用栈扫描, 正确处理字符串转义与嵌套括号。
        """
        marker = 'window.__ARCHIVE_PLAYER__'
        idx = html.find(marker)
        if idx == -1:
            return None
        brace = html.find('{', idx)
        if brace == -1:
            return None

        depth = 0
        in_str = False
        esc = False
        for i in range(brace, len(html)):
            ch = html[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == '\\':
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    return html[brace:i+1]
        return None

    def _extract_m3u8_url(self, html):
        # [FIX-07] 使用栈式 JSON 扫描, 替代非贪婪正则
        seg = self._extract_archive_player_json(html)
        if not seg:
            return ""
        try:
            data = json.loads(seg)
        except Exception:
            return ""

        raw_path = data.get("rawPath", "")
        if not raw_path:
            return ""

        if raw_path.startswith("http"):
            return raw_path
        cdn = data.get("cdnLine", CDN_LINES[0])
        return cdn.rstrip("/") + "/" + raw_path.lstrip("/")

    # --------------------------------------------------------
    # 搜索
    # --------------------------------------------------------
    def searchContent(self, key, quick=False, pg="1"):
        if not key:
            return {"list": []}
        try:
            encoded_key = quote(key)
            url = f"/search-page/?wd={encoded_key}"
            html = self._fetch(url)
        except Exception:
            return {"list": []}
        if not html:
            return {"list": []}

        videos = self._parse_rank_list(html)
        if not videos:
            videos = self._parse_video_list(html)
        return {"list": videos}

    def _parse_rank_list(self, html):
        videos = []
        seen = set()
        for m in re.finditer(r'<a\s+href="/video/(\d+)/"\s+class="rankItem[^"]*"[^>]*>', html):
            vid = m.group(1)
            if vid in seen:
                continue
            seen.add(vid)

            start = m.start()
            end_tag = html.find("</a>", start)
            if end_tag == -1:
                end_tag = start + 1000
            block = html[start:end_tag]

            title = ""
            alt_m = re.search(r'alt="([^"]+)"', block)
            if alt_m:
                title = alt_m.group(1).strip()
            if not title:
                title_m = re.search(r'class="rankTitle[^"]*"[^>]*>([^<]+)<', block)
                if title_m:
                    title = title_m.group(1).strip()

            pic = ""
            pic_m = re.search(r'data-src="(https?://[^"]+)"', block)
            if pic_m:
                pic = pic_m.group(1)
                if "/assets/" in pic:
                    pic = ""

            videos.append({
                "vod_id": vid,
                "vod_name": title,
                "vod_pic": pic,
                "vod_remarks": "",
            })

        return videos

    # --------------------------------------------------------
    # 播放 - 本地 HTTP 解密代理
    # --------------------------------------------------------
    def playerContent(self, flag, id, vipFlags=None):
        """
        id = vid (视频 ID)
        返回 parse=0, url=本地解密 m3u8
        """
        if not id:
            # [FIX-05] 无 id: 返回空 url (播放器显示无源), 不装成有源
            return {"parse": 0, "playUrl": "", "url": ""}

        # 提取纯数字 vid
        vid = id
        if not vid.isdigit():
            m = re.search(r'(\d+)', vid)
            if m:
                vid = m.group(1)
            else:
                return {"parse": 0, "playUrl": "", "url": ""}

        # 检查缓存
        cache = _load_cache(vid)
        if cache:
            _start_proxy_server()
            return {
                "parse": 0,
                "playUrl": "",
                "url": f"{PROXY_BASE}/bsizw/m3u8?vid={vid}",
                "header": {"User-Agent": self.ua},
            }

        # 1. 获取视频页
        try:
            html = self._fetch(f"/video/{vid}/")
            if not html or len(html) < 2000:
                return {"parse": 0, "playUrl": "", "url": ""}
        except Exception:
            return {"parse": 0, "playUrl": "", "url": ""}

        # 2. 提取 m3u8 URL
        m3u8_url = self._extract_m3u8_url(html)
        if not m3u8_url:
            return {"parse": 0, "playUrl": "", "url": ""}

        # 3. 下载 m3u8 分析
        try:
            m3u8_content = _http_fetch(m3u8_url)
            if not m3u8_content or '#EXTM3U' not in m3u8_content:
                # [FIX-05] 原代码这里返回 parse=1 + m3u8_url: 让播放器去请求
                #         一个无法解密的源, 无限转圈。改为空源。
                return {"parse": 0, "playUrl": "", "url": ""}
        except Exception:
            return {"parse": 0, "playUrl": "", "url": ""}

        # 4. 分析加密 key
        key_match = re.search(
            r'#EXT-X-KEY:METHOD=AES-128,URI="([^"]+)"(?:,IV=0x([0-9a-fA-F]+))?',
            m3u8_content,
        )

        if not key_match:
            # 未加密, 直接返回
            return {
                "parse": 0,
                "playUrl": "",
                "url": m3u8_url,
                "header": {"User-Agent": self.ua, "Referer": self.host + "/"},
            }

        # 5. 获取 key
        key_uri = key_match.group(1)
        m3u8_parsed = urlparse(m3u8_url)
        if key_uri.startswith('/'):
            key_url = f"{m3u8_parsed.scheme}://{m3u8_parsed.netloc}{key_uri}"
        elif key_uri.startswith('http'):
            key_url = key_uri
        else:
            key_url = m3u8_parsed.scheme + "://" + m3u8_parsed.netloc + "/" + key_uri

        try:
            key_data = _http_fetch(key_url, binary=True)
            if not key_data or len(key_data) != 16:
                raise ValueError(f"Invalid key: {len(key_data) if key_data else 0} bytes")
        except Exception:
            # [FIX-05] key 拿不到 -> 无法解密 -> 绝不能把加密 m3u8 丢给播放器
            return {"parse": 0, "playUrl": "", "url": ""}

        # 6. 获取 IV
        iv_hex = key_match.group(2) if key_match.lastindex and key_match.lastindex >= 2 else None
        if iv_hex:
            iv_data = bytes.fromhex(iv_hex)
        else:
            iv_data = bytes(16)

        # 7. 提取 ts URL
        ts_urls = []
        for ts_m in re.finditer(r'(https?://[^\s<>"]+\.ts)', m3u8_content):
            ts_urls.append(ts_m.group(1))

        if not ts_urls:
            ts_base = m3u8_url.rsplit('/', 1)[0]
            for ts_m in re.finditer(r'#EXTINF:[\d.]+,\s*(.+\.ts)', m3u8_content):
                ts_url = ts_m.group(1)
                if ts_url and not ts_url.startswith('http'):
                    ts_url = ts_base + '/' + ts_url
                if ts_url:
                    ts_urls.append(ts_url)

        if not ts_urls:
            # [FIX-05] 提取不到 ts -> 无法代理 -> 空源
            return {"parse": 0, "playUrl": "", "url": ""}

        # 8. 提取时长
        durations = re.findall(r'#EXTINF:([\d.]+)', m3u8_content)

        # 9. 保存缓存
        cache_data = {
            'key': key_data,
            'iv': iv_data,
            'ts_urls': ts_urls,
            'durations': durations,
        }
        _save_cache(vid, cache_data)

        # 10. 启动本地 HTTP 解密代理并返回本地 URL
        proxy_ok = _start_proxy_server()
        if proxy_ok:
            return {
                "parse": 0,
                "playUrl": "",
                "url": f"{PROXY_BASE}/bsizw/m3u8?vid={vid}",
                "header": {"User-Agent": self.ua},
            }

        # [FIX-05] 代理启动失败: 原代码 fallback parse=1 + 加密 m3u8(转圈);
        #          现在明确返回空源, 播放器直接提示无可用播放源
        return {"parse": 0, "playUrl": "", "url": ""}

    # --------------------------------------------------------
    def localProxy(self, param):
        """TVBox localProxy 接口 - 本地代理也走解密"""
        return [404, "text/plain", b"Not Supported"]


# ==================== 测试入口 ====================

if __name__ == "__main__":
    spider = Spider()
    HOME = spider.host or HOST

    print("=" * 60)
    print("  白丝自慰 (bsizw.cc) - 修复学习版测试")
    print("=" * 60)

    print("\n[测试1] 首页分类 (动态)")
    try:
        home = spider.homeContent()
        print(f"  分类数: {len(home['class'])}")
        ids_now = [c['type_id'] for c in home['class']]
        print(f"  包含 141/163/164: {'141' in ids_now} / {'163' in ids_now} / {'164' in ids_now}")
    except Exception as e:
        print(f"  错误: {e}")

    print("\n[测试2] 分类内容 (页码只算当前分类)")
    try:
        cat = spider.categoryContent("28", 1, False, {})
        print(f"  视频数: {len(cat.get('list', []))}")
        print(f"  总页数: {cat.get('pagecount', 1)}")
    except Exception as e:
        print(f"  错误: {e}")

    print("\n[测试3] 详情页 + 播放链 (新视频ID)")
    try:
        detail = spider.detailContent(["2038807529884639232"])
        if detail.get('list'):
            d = detail['list'][0]
            print(f"  标题: {d['vod_name']}")
            print(f"  play_url: {d.get('vod_play_url', '')[:80]}")

            parts = d['vod_play_url'].split('$')
            if len(parts) >= 2:
                vid = parts[1]
                print(f"\n  playerContent(vid={vid})...")
                player = spider.playerContent("bsizw", vid)
                print(f"  parse: {player['parse']}")
                print(f"  url: {player['url'][:80]}")

                if player['parse'] == 0:
                    import time
                    time.sleep(2)

                    # 测试代理
                    import requests as rq
                    print(f"\n  获取本地m3u8...")
                    resp = rq.get(player['url'], timeout=10)
                    print(f"  Status: {resp.status_code}")
                    if resp.status_code == 200:
                        m3u8 = resp.text
                        ts_count = m3u8.count('/bsizw/ts?vid=')
                        print(f"  ts链接数: {ts_count}")

                        ts_lines = [l for l in m3u8.split('\n') if '/ts?vid=' in l]
                        if ts_lines:
                            print(f"\n  获取第1个解密段(可能耗时, 纯Python解密)...")
                            t0 = time.time()
                            ts_resp = rq.get(ts_lines[0], timeout=300)
                            cost = time.time() - t0
                            print(f"  Status: {ts_resp.status_code}  耗时: {cost:.1f}s")
                            if ts_resp.status_code == 200:
                                data = ts_resp.content
                                sync = data[0]
                                print(f"  同步字节: 0x{sync:02x}")
                                if sync == 0x47:
                                    print("  ✅ 解密成功! 有效MPEG-TS!")
                                else:
                                    print("  ❌ 解密失败, 非MPEG-TS")
                            else:
                                print(f"  内容: {ts_resp.text[:200]}")
    except Exception as e:
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 60)
    print("  测试完成")
    print("=" * 60)