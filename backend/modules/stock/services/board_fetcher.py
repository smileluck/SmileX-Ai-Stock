#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
行业/概念板块抓取层
数据源降级链：
- 行业：akshare-东财（主源，含换手率/涨跌家数）→ 腾讯板块排行（兜底，含换手率/成交额/净流入/涨跌家数）→ 同花顺（末级兜底，无换手率）
- 概念：akshare-东财（主源）→ 腾讯板块排行（兜底，同花顺无概念行情列表）
- 东财 push2 接口对高频请求有 IP 级封禁，异常/限流时自动降级
- 腾讯板块排行（getRank）字段完整但分类体系为申万行业（hy2=申万二级）/腾讯概念，
  与东财板块代码体系不同，跨源快照不可混用对比
"""
import asyncio
import io
import logging

import httpx

from modules.stock.services._common import num, normalize_code
from modules.stock.services.market_fetcher import FUND_FLOW_RETRY_DELAY

logger = logging.getLogger(__name__)

_QQ_GETRANK_URL = "https://proxy.finance.qq.com/cgi/cgi-bin/rank/pt/getRank"
_QQ_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
}
_EM_CLIST_HOSTS = (
    "push2.eastmoney.com",       # 实时行情（主）
    "push2delay.eastmoney.com",  # 延时行情（实时源 IP 限流时降级，收盘后同步数据无差异）
)
# 板块内个股涨幅榜并发上限与单请求间隔：push2 对高频请求有 IP 级封禁，概念板块量大需限速
_EM_TOP_STOCKS_CONCURRENCY = 5
_EM_TOP_STOCKS_INTERVAL = 0.1
_THS_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/89.0.4389.90 Safari/537.36"
)
_THS_RANK_URL = "http://q.10jqka.com.cn/thshy/index/field/199112/order/desc/page/{page}/ajax/1/"


def _pick(row, *keys):
    """从 DataFrame 行中按候选列名取第一个非空值"""
    for k in keys:
        if k in row and row[k] is not None:
            return row[k]
    return None


def _single_leading_item(code, name, change_pct) -> list[dict]:
    """兜底数据源只提供单只领涨股时，包装为 leading_stocks 单元素列表"""
    if not name:
        return []
    return [{"code": code or None, "name": name, "change_pct": change_pct}]


async def _pick_em_clist_url(client: httpx.AsyncClient) -> str:
    """探测可用的东财行情 clist 接口地址：逐域名试探，实时源被 IP 限流时降级延时源"""
    params = {"pn": 1, "pz": 1, "po": 1, "np": 1, "fltt": 2, "invt": 2,
              "fid": "f3", "fs": "b:BK0475", "fields": "f12"}
    last_error: Exception | None = None
    for host in _EM_CLIST_HOSTS:
        url = f"https://{host}/api/qt/clist/get"
        try:
            resp = await client.get(url, params=params)
            if resp.json().get("rc") == 0:
                return url
        except Exception as e:  # noqa: BLE001
            last_error = e
    raise RuntimeError(f"东财 clist 接口全部不可用: {last_error}")


async def _fetch_board_leading_stocks_em(
    client: httpx.AsyncClient, clist_url: str, board_code: str, top_n: int = 3
) -> list[dict]:
    """东财 push2 板块内个股涨幅榜，返回前 top_n 名 [{code, name, change_pct}]

    板块列表接口的领涨股列只有名称无代码，需按板块逐个补抓成分涨幅前三。
    """
    resp = await client.get(
        clist_url,
        params={
            "pn": 1,
            "pz": top_n,
            "po": 1,
            "np": 1,
            "fltt": 2,
            "invt": 2,
            "fid": "f3",  # 按涨跌幅降序
            "fs": f"b:{board_code}",
            "fields": "f12,f14,f3",
        },
    )
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("rc") != 0:
        raise RuntimeError(f"东财板块个股榜返回错误: {payload.get('rt')}")
    diff = (payload.get("data") or {}).get("diff") or []
    items = []
    for d in diff:
        name = str(d.get("f14", "")).strip()
        if not name:
            continue
        items.append({
            "code": normalize_code(d.get("f12")) or None,
            "name": name,
            "change_pct": num(d.get("f3")),
        })
    return items


async def _enrich_leading_stocks(items: list[dict]) -> None:
    """为东财板块列表补抓每个板块的领涨股前三名（含代码）

    单板块失败不影响整体，回退为列表自带单只领涨股（名称无代码）；
    补抓成功时用 top1 回填旧三字段，补齐东财源缺失的领涨股代码。
    """
    sem = asyncio.Semaphore(_EM_TOP_STOCKS_CONCURRENCY)

    async with httpx.AsyncClient(timeout=10, headers=_QQ_HEADERS) as client:
        # 域名探测一次：实时源被限流时整批切到延时源，避免逐板块重复探测
        clist_url = await _pick_em_clist_url(client)

        async def _enrich_one(it: dict) -> None:
            async with sem:
                try:
                    leading = await _fetch_board_leading_stocks_em(client, clist_url, it["board_code"])
                except Exception as e:
                    logger.warning(
                        "板块领涨股前三名抓取失败(%s %s): %s",
                        it["board_code"], it["board_name"], e,
                    )
                    leading = []
                await asyncio.sleep(_EM_TOP_STOCKS_INTERVAL)
            if leading:
                it["leading_stocks"] = leading
                top1 = leading[0]
                it["leading_stock_code"] = top1["code"]
                it["leading_stock_name"] = top1["name"]
                it["leading_stock_change_pct"] = top1["change_pct"]
            else:
                it["leading_stocks"] = _single_leading_item(
                    it.get("leading_stock_code"),
                    it.get("leading_stock_name"),
                    it.get("leading_stock_change_pct"),
                )

        await asyncio.gather(*(_enrich_one(it) for it in items))


async def fetch_board_list(board_type: str) -> list[dict]:
    """抓取板块列表（行业或概念），按降级链自动切换数据源

    Args:
        board_type: "industry" 或 "concept"
    """
    try:
        return await _fetch_board_list_em(board_type)
    except Exception as e:
        logger.warning("东财板块列表抓取失败(%s)，降级腾讯板块排行: %s", board_type, e)
    try:
        return await _fetch_board_list_qq(board_type)
    except Exception as e:
        logger.warning("腾讯板块排行抓取失败(%s)，尝试降级: %s", board_type, e)
    if board_type == "industry":
        return await _fetch_board_list_ths()
    raise RuntimeError(f"板块列表数据源全部不可用({board_type})")


async def _fetch_board_list_em(board_type: str) -> list[dict]:
    """东财主源：板块实时行情列表（akshare stock_board_*_name_em）"""
    import akshare as ak

    if board_type == "industry":
        df = await asyncio.to_thread(ak.stock_board_industry_name_em)
    else:
        df = await asyncio.to_thread(ak.stock_board_concept_name_em)

    items = []
    for _, row in df.iterrows():
        board_code = str(row.get("板块代码", row.get("排名", ""))).strip()
        board_name = str(row.get("板块名称", "")).strip()
        if not board_code:
            board_code = board_name

        items.append({
            "board_type": board_type,
            "board_code": board_code,
            "board_name": board_name,
            "change_pct": num(row.get("涨跌幅")),
            # 东财板块列表接口不提供成交额/成交量，置空而非错用总市值
            "turnover": None,
            "turnover_rate": num(row.get("换手率")),
            "volume": None,
            "rising_count": num(row.get("上涨家数")),
            "falling_count": num(row.get("下跌家数")),
            # 领涨股票列是名称不是代码，代码字段留空，随后 _enrich_leading_stocks 补齐
            "leading_stock_code": None,
            "leading_stock_name": str(row.get("领涨股票", "")).strip() or None,
            "leading_stock_change_pct": num(row.get("领涨股票-涨跌幅")),
        })
    if not items:
        raise RuntimeError(f"东财板块列表为空({board_type})")

    # 逐板块补抓领涨股前三名（含代码），失败时回退列表自带单只领涨股
    await _enrich_leading_stocks(items)
    return items


def _ths_v_code() -> str:
    """执行同花顺反爬 JS 生成 v cookie（hexin-v）"""
    import py_mini_racer
    from akshare.datasets import get_ths_js

    js = py_mini_racer.MiniRacer()
    with open(get_ths_js("ths.js"), encoding="utf-8") as f:
        js.eval(f.read())
    return js.call("v")


def _fetch_board_list_ths_sync() -> list[dict]:
    """同花顺行业板块一览表（同步实现，供 asyncio.to_thread 调用）

    页面含成交额/净流入/上涨家数/下跌家数/领涨股，无换手率与股票代码。
    同花顺对 v cookie 校验严格，必须走 http 且每次请求刷新 v 值。
    """
    import pandas as pd
    from bs4 import BeautifulSoup

    import akshare as ak

    name_code_map = {
        str(r["name"]).strip(): str(r["code"]).strip()
        for _, r in ak.stock_board_industry_name_ths().iterrows()
    }

    def _get(page: int) -> str:
        v = _ths_v_code()
        resp = httpx.get(
            _THS_RANK_URL.format(page=page),
            headers={"User-Agent": _THS_UA, "Cookie": f"v={v}"},
            timeout=15,
            follow_redirects=True,
        )
        resp.raise_for_status()
        return resp.text

    first_html = _get(1)
    page_info = BeautifulSoup(first_html, features="lxml").find(
        name="span", attrs={"class": "page_info"}
    )
    total_pages = int(page_info.text.split("/")[1]) if page_info else 1

    frames = [pd.read_html(io.StringIO(first_html))[0]]
    for page in range(2, total_pages + 1):
        frames.append(pd.read_html(io.StringIO(_get(page)))[0])
    df = pd.concat(frames, ignore_index=True)
    # pandas 对重名列自动加 .1 后缀：涨跌幅(%).1 是领涨股涨跌幅
    df.columns = [str(c).strip() for c in df.columns]

    items = []
    for _, row in df.iterrows():
        board_name = str(row.get("板块", "")).strip()
        if not board_name:
            continue
        turnover = num(row.get("总成交额（亿元）"))
        net_inflow = num(row.get("净流入（亿元）"))
        volume = num(row.get("总成交量（万手）"))
        leading_name = str(row.get("领涨股", "")).strip() or None
        leading_pct = num(row.get("涨跌幅(%).1"))
        items.append({
            "board_type": "industry",
            "board_code": name_code_map.get(board_name, board_name),
            "board_name": board_name,
            "change_pct": num(row.get("涨跌幅(%)")),
            "turnover": turnover * 1e8 if turnover is not None else None,
            # 同花顺列表无换手率
            "turnover_rate": None,
            "volume": volume * 1e4 if volume is not None else None,
            "net_inflow": net_inflow * 1e8 if net_inflow is not None else None,
            "rising_count": num(row.get("上涨家数")),
            "falling_count": num(row.get("下跌家数")),
            "leading_stock_code": None,
            "leading_stock_name": leading_name,
            "leading_stock_change_pct": leading_pct,
            # 同花顺列表领涨股仅名称无代码
            "leading_stocks": _single_leading_item(None, leading_name, leading_pct),
        })
    if not items:
        raise RuntimeError("同花顺行业板块列表为空")
    return items


async def _fetch_board_list_ths() -> list[dict]:
    return await asyncio.to_thread(_fetch_board_list_ths_sync)


async def _fetch_board_list_qq(board_type: str) -> list[dict]:
    """腾讯板块排行兜底：getRank 接口（行业 hy2=申万二级 / 概念 gn）

    字段比 mktHs 行情排行完整：换手率(hsl)/成交额(turnover)/成交量(volume)/
    主力净流入(zljlr)/涨跌家数(zgb "涨/跌")/领涨股(lzg)。
    金额单位为万元，入库前换算为元；成交量单位为手。
    """
    qq_board_type = "hy2" if board_type == "industry" else "gn"

    items: list[dict] = []
    async with httpx.AsyncClient(timeout=15, headers=_QQ_HEADERS) as client:
        offset = 0
        page_size = 100
        while True:
            resp = await client.get(
                _QQ_GETRANK_URL,
                params={
                    "board_type": qq_board_type,
                    "sort_type": "turnover",
                    "direct": "down",
                    "offset": offset,
                    "count": page_size,
                },
            )
            resp.raise_for_status()
            payload = resp.json()
            data = payload.get("data") or {}
            if payload.get("code") != 0 or not isinstance(data, dict):
                raise RuntimeError(f"腾讯板块排行返回错误: {payload.get('msg')}")
            rows = data.get("rank_list") or []
            for row in rows:
                board_code = str(row.get("code", "")).strip()
                board_name = str(row.get("name", "")).strip()
                if not board_code or not board_name:
                    continue
                turnover = num(row.get("turnover"))
                net_inflow = num(row.get("zljlr"))
                rising_count, falling_count = None, None
                breadth = str(row.get("zgb") or "")
                if "/" in breadth:
                    up, down = breadth.split("/", 1)
                    rising_count, falling_count = num(up), num(down)
                leading = row.get("lzg") or {}
                leading_code = normalize_code(leading.get("code")) or None
                leading_name = str(leading.get("name", "")).strip() or None
                leading_pct = num(leading.get("zdf"))
                items.append({
                    "board_type": board_type,
                    "board_code": board_code,
                    "board_name": board_name,
                    "change_pct": num(row.get("zdf")),
                    "turnover": turnover * 1e4 if turnover is not None else None,
                    "turnover_rate": num(row.get("hsl")),
                    "volume": num(row.get("volume")),
                    "net_inflow": net_inflow * 1e4 if net_inflow is not None else None,
                    "rising_count": int(rising_count) if rising_count is not None else None,
                    "falling_count": int(falling_count) if falling_count is not None else None,
                    "leading_stock_code": leading_code,
                    "leading_stock_name": leading_name,
                    "leading_stock_change_pct": leading_pct,
                    # 腾讯源领涨股仅单只，但自带代码
                    "leading_stocks": _single_leading_item(leading_code, leading_name, leading_pct),
                })
            offset += len(rows)
            total = num(data.get("total")) or 0
            if not rows or offset >= total:
                break
            await asyncio.sleep(0.5)

    if not items:
        raise RuntimeError(f"腾讯板块排行为空({board_type})")
    return items


async def fetch_board_fund_flow(board_type: str) -> dict[str, float | None]:
    """抓取板块资金流排行，返回 {board_name: net_inflow} 映射

    东财单源无兜底，被限流时退避重试一次，仍失败返回空映射（净流入留空）
    """
    import akshare as ak

    indicator = "今日"
    sector_type = "行业资金流" if board_type == "industry" else "概念资金流"

    df = None
    last_exc: Exception | None = None
    for attempt in range(2):
        try:
            df = await asyncio.to_thread(
                ak.stock_sector_fund_flow_rank,
                indicator=indicator,
                sector_type=sector_type,
            )
            break
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt == 0:
                logger.warning("板块资金流抓取失败(%s)，%ds 后重试一次", sector_type, FUND_FLOW_RETRY_DELAY)
                await asyncio.sleep(FUND_FLOW_RETRY_DELAY)
    if df is None:
        logger.warning("板块资金流抓取最终失败(%s): %s", sector_type, last_exc)
        return {}

    result = {}
    flow_col = "今日主力净流入-净额" if "今日主力净流入-净额" in df.columns else "主力净流入-净额"
    for _, row in df.iterrows():
        name = str(row.get("名称", "")).strip()
        if name:
            result[name] = num(row.get(flow_col))
    return result


# ------------------------------------------------------------------
# 轮动分析扩展：板块历史日K（回填）+ 板块全部成分股（高低切换数据源）
# ------------------------------------------------------------------
# push2his 主域名存在 IP 级限流（直接断连），编号 CDN 域名与延时源为逃生通道
_EM_KLINE_HOSTS = (
    "push2his.eastmoney.com",
    "44.push2his.eastmoney.com",
    "12.push2his.eastmoney.com",
)
# 板块名->代码映射分页拉取间隔：映射页单页 100 条，快速连发易触发限流
_EM_BOARD_MAP_INTERVAL = 0.5


async def _em_request_with_hosts(
    client: httpx.AsyncClient, path: str, params: dict,
    hosts: tuple[str, ...], attempts_per_host: int = 2,
) -> dict:
    """东财行情请求：逐域名 + 逐次退避重试，统一校验 rc==0

    IP 级限流表现为直接断连且时好时坏，单次域名探测不足以覆盖整个批次，
    因此每个请求都在实时源失败后自动降级延时源/编号 CDN 域名。
    """
    last_error: Exception | None = None
    for host in hosts:
        url = f"https://{host}{path}"
        for i in range(attempts_per_host):
            try:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                payload = resp.json()
                if payload.get("rc") != 0:
                    raise RuntimeError(f"东财接口返回错误: {payload.get('rt')}")
                return payload
            except Exception as e:  # noqa: BLE001
                last_error = e
                if i < attempts_per_host - 1:
                    await asyncio.sleep(0.5 * (i + 1))
    raise last_error  # type: ignore[misc]


def _em_clist_get(client: httpx.AsyncClient, params: dict) -> dict:
    """clist 行情请求（实时源 -> 延时源自动降级）"""
    return _em_request_with_hosts(
        client, "/api/qt/clist/get", params, _EM_CLIST_HOSTS,
    )


def _em_kline_get(client: httpx.AsyncClient, params: dict) -> dict:
    """板块日K请求（主域名 -> 编号 CDN 域名自动降级）"""
    return _em_request_with_hosts(
        client, "/api/qt/stock/kline/get", params, _EM_KLINE_HOSTS,
    )


def _norm_board_name(name: str) -> str:
    """板块名归一化：全角罗马数字/括号转半角、去空白，供跨数据源名称匹配"""
    s = str(name)
    for a, b in (("Ⅱ", "II"), ("Ⅰ", "I"), ("（", "("), ("）", ")"), (" ", ""), ("\u3000", "")):
        s = s.replace(a, b)
    return s.lower()


def _strip_board_name_suffix(norm: str) -> str:
    """去除归一化板块名的层级后缀（Ⅱ/I、(二级)等），作为名称匹配兜底"""
    for suf in ("ii", "i", "(一级)", "(二级)", "(三级)", "(申万)"):
        if norm.endswith(suf) and len(norm) > len(suf):
            return norm[: -len(suf)]
    return norm


async def _fetch_em_board_code_map(
    client: httpx.AsyncClient, board_type: str,
) -> dict[str, str]:
    """东财板块名 -> 板块代码(BKxxxx)映射（含归一化名键）

    business_board_daily 的 board_code 跟随当日板块列表源：东财主源为 BKxxxx，
    腾讯兜底源为 pt0xxxxx；而成分股/板块日K接口只认东财代码，需按名称解析。
    """
    fs = "m:90+t:2" if board_type == "industry" else "m:90+t:3"
    name_map: dict[str, str] = {}
    page, page_size = 1, 100
    while True:
        payload = await _em_clist_get(
            client,
            {
                "pn": page,
                "pz": page_size,
                "po": 1,
                "np": 1,
                "fltt": 2,
                "invt": 2,
                "fid": "f3",
                "fs": fs,
                "fields": "f12,f14",
            },
        )
        data = payload.get("data") or {}
        diff = data.get("diff") or []
        for d in diff:
            code = str(d.get("f12", "")).strip()
            name = str(d.get("f14", "")).strip()
            if code and name:
                name_map[name] = code
                norm = _norm_board_name(name)
                name_map.setdefault(norm, code)
                stripped = _strip_board_name_suffix(norm)
                if stripped != norm:
                    name_map.setdefault(stripped, code)
        total = num(data.get("total")) or 0
        if not diff or page * page_size >= total:
            break
        page += 1
        await asyncio.sleep(_EM_BOARD_MAP_INTERVAL)
    return name_map


def _resolve_em_board_code(board: dict, name_map: dict[str, str]) -> str:
    """板块字典 -> 东财板块代码：已是 BK 代码直接用，否则按板块名解析"""
    code = str(board.get("board_code", "")).strip()
    if code.upper().startswith("BK"):
        return code
    name = str(board.get("board_name", "")).strip()
    norm = _norm_board_name(name)
    return (
        name_map.get(name) or name_map.get(norm)
        or name_map.get(_strip_board_name_suffix(norm)) or ""
    )


async def _fetch_board_kline_paged(
    client: httpx.AsyncClient, board_code: str, days: int
) -> list[dict]:
    """东财 push2his 板块日K（行业/概念板块统一 90 市场），返回升序列表

    用于回填 business_board_daily 历史缺失日期：日K只含行情字段，
    净流入/涨跌家数/领涨股等快照字段历史无法补齐，回填行留空。
    返回 [{date, change_pct, turnover, volume, turnover_rate}]。
    """
    payload = await _em_kline_get(
        client,
        {
            "secid": f"90.{board_code}",
            "klt": 101,   # 日K
            "fqt": 1,     # 前复权
            "lmt": days,
            "end": "20500101",
            "fields1": "f1,f2,f3,f4,f5,f6",
            # f51-日期, f52-开, f53-收, f54-高, f55-低, f56-量(手), f57-额(元),
            # f58-振幅, f59-涨跌幅, f60-涨跌额, f61-换手率
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        },
    )
    klines = ((payload.get("data") or {}).get("klines")) or []
    items = []
    for row in klines:
        parts = str(row).split(",")
        if len(parts) < 11:
            continue
        items.append({
            "date": parts[0],
            "change_pct": num(parts[8]),
            "turnover": num(parts[6]),
            "volume": num(parts[5]),
            "turnover_rate": num(parts[10]),
        })
    return items


async def fetch_board_history_kline(board_code: str, days: int = 60) -> list[dict]:
    """东财 push2his 板块日K（独立连接版，单板块调用）"""
    async with httpx.AsyncClient(timeout=10, headers=_QQ_HEADERS) as client:
        return await _fetch_board_kline_paged(client, board_code, days)


async def _fetch_board_constituents_paged(
    client: httpx.AsyncClient, board_code: str
) -> list[dict]:
    """东财 push2 板块全部成分股（分页拉全，按涨跌幅降序），复用调用方传入的连接

    返回 [{stock_code, stock_name, price, change_pct, amount, turnover_rate,
    gain_5d, gain_10d}]；gain_5d/gain_10d 为数据源近5/10日涨跌幅（f109/f160），
    源未提供时为 None，由查询侧按成分股日快照自累计兜底。
    """
    items: list[dict] = []
    page, page_size = 1, 100
    while True:
        payload = await _em_clist_get(
            client,
            {
                "pn": page,
                "pz": page_size,
                "po": 1,
                "np": 1,
                "fltt": 2,
                "invt": 2,
                "fid": "f3",  # 按涨跌幅降序
                "fs": f"b:{board_code}",
                # f12-代码, f14-名称, f2-最新价, f3-涨跌幅, f6-成交额, f8-换手率,
                # f109-近5日涨跌幅, f160-近10日涨跌幅
                "fields": "f12,f14,f2,f3,f6,f8,f109,f160",
            },
        )
        data = payload.get("data") or {}
        diff = data.get("diff") or []
        for d in diff:
            code = normalize_code(d.get("f12")) or None
            name = str(d.get("f14", "")).strip()
            if not code or not name:
                continue
            items.append({
                "stock_code": code,
                "stock_name": name,
                "price": num(d.get("f2")),
                "change_pct": num(d.get("f3")),
                "amount": num(d.get("f6")),
                "turnover_rate": num(d.get("f8")),
                "gain_5d": num(d.get("f109")),
                "gain_10d": num(d.get("f160")),
            })
        total = num(data.get("total")) or 0
        if not diff or page * page_size >= total:
            break
        page += 1
        await asyncio.sleep(_EM_TOP_STOCKS_INTERVAL)
    return items


async def fetch_board_constituents(board_type: str, board_code: str) -> list[dict]:
    """东财 push2 板块全部成分股（独立连接版，单板块调用）"""
    async with httpx.AsyncClient(timeout=10, headers=_QQ_HEADERS) as client:
        return await _fetch_board_constituents_paged(client, board_code)


async def fetch_boards_constituents_batch(
    boards: list[dict],
) -> list[tuple[dict, list[dict]]]:
    """批量抓取多板块全部成分股（共享连接与域名探测，单板块失败不影响整体）

    boards 为 [{board_type, board_code, board_name, ...}]，返回与入参顺序一致的
    [(board, stocks)]，失败板块的 stocks 为空列表。
    board_code 非 BK 前缀（腾讯兜底源 pt0xxxxx 等）时按板块名解析东财代码。
    """
    sem = asyncio.Semaphore(_EM_TOP_STOCKS_CONCURRENCY)

    async with httpx.AsyncClient(timeout=10, headers=_QQ_HEADERS) as client:
        name_maps = {
            bt: await _fetch_em_board_code_map(client, bt)
            for bt in {str(b.get("board_type") or "industry") for b in boards}
        }

        async def _one(board: dict) -> list[dict]:
            async with sem:
                try:
                    em_code = _resolve_em_board_code(
                        board, name_maps.get(str(board.get("board_type") or "industry"), {}),
                    )
                    if not em_code:
                        raise RuntimeError("按板块名未匹配到东财板块代码")
                    return await _fetch_board_constituents_paged(client, em_code)
                except Exception as e:  # noqa: BLE001
                    logger.warning(
                        "板块成分股抓取失败(%s %s): %s",
                        board["board_code"], board["board_name"], e,
                    )
                    return []
                finally:
                    await asyncio.sleep(_EM_TOP_STOCKS_INTERVAL)

        stocks_list = await asyncio.gather(*(_one(b) for b in boards))
    return list(zip(boards, stocks_list))


async def fetch_boards_history_batch(
    boards: list[dict], days: int = 60, concurrency: int = 2, interval: float = 0.5
) -> list[tuple[dict, list[dict]]]:
    """批量抓取多板块历史日K（共享连接，单板块失败不影响整体）

    用于历史回填，并发与间隔比实时接口更保守（push2his 存在 IP 级限流
    断连，过高的请求密度会触发整段封锁）。返回与入参顺序一致的
    [(board, klines)]，失败板块的 klines 为空列表。
    board_code 非 BK 前缀（腾讯兜底源 pt0xxxxx 等）时按板块名解析东财代码。
    """
    sem = asyncio.Semaphore(concurrency)

    async with httpx.AsyncClient(timeout=10, headers=_QQ_HEADERS) as client:
        name_maps = {
            bt: await _fetch_em_board_code_map(client, bt)
            for bt in {str(b.get("board_type") or "industry") for b in boards}
        }

        async def _one(board: dict) -> list[dict]:
            async with sem:
                try:
                    em_code = _resolve_em_board_code(
                        board, name_maps.get(str(board.get("board_type") or "industry"), {}),
                    )
                    if not em_code:
                        raise RuntimeError("按板块名未匹配到东财板块代码")
                    return await _fetch_board_kline_paged(client, em_code, days)
                except Exception as e:  # noqa: BLE001
                    logger.warning(
                        "板块历史日K抓取失败(%s %s): %s",
                        board["board_code"], board["board_name"], e,
                    )
                    return []
                finally:
                    await asyncio.sleep(interval)

        klines_list = await asyncio.gather(*(_one(b) for b in boards))
    return list(zip(boards, klines_list))
