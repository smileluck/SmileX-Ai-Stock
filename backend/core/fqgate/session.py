#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""FQGate 账户与登录（/v1/market/health、/v1/market/session/*）。"""
from core.fqgate import client


async def health() -> dict:
    """登录状态：返回当前行情账户的登录状态。行情账户与交易账户分别登录。"""
    return await client.get("/v1/market/health")


async def logout() -> dict:
    """退出登录：退出当前行情账户。"""
    return await client.delete("/v1/market/session")


async def cached_login(client_path: str) -> dict:
    """本机快捷登录：复用 client_path 指定同花顺安装目录中最近账号已保存的登录凭据。

    client_path 必须是运行 FQGate 电脑上的绝对路径（远航版也接受 bin 目录）；
    当前支持 Windows 远航版的 MD5/临时凭据记录。登录成功后自动保存恢复信息，
    后续行情请求及主程序重启后均自动恢复，无需重复调用。"""
    return await client.post(
        "/v1/market/session/cached-login", {"client_path": client_path}
    )


async def login(username: str, password: str) -> dict:
    """账号密码登录：使用同花顺账号和密码登录行情账户。密码不会在响应中返回。"""
    return await client.post(
        "/v1/market/session/login",
        {"username": username, "password": password},
    )


async def qr_begin() -> dict:
    """App 扫码登录：获取二维码。返回登录二维码和登录流程编号，请使用同花顺 App 扫码并在手机上确认。"""
    return await client.post("/v1/market/session/qr/begin", {})


async def qr_poll(flow_id: int) -> dict:
    """App 扫码登录：查询扫码状态。查询一次扫码登录进度；未完成时可间隔一段时间再次查询。

    flow_id 为创建扫码登录时返回的流程编号。"""
    return await client.post("/v1/market/session/qr/poll", {"flow_id": flow_id})


async def saved_login_remove() -> dict:
    """移除保存的登录信息：移除当前系统用户安全存储中的行情登录信息，不中断当前行情连接。"""
    return await client.delete("/v1/market/session/saved-login")


async def self_stock() -> dict:
    """同花顺自选股：读取当前登录同花顺账号维护的自选股列表。只读；未登录或会话失效时返回错误。"""
    return await client.get("/v1/market/session/self-stock")


async def add_self_stock(
    code: str, market_id: str, group_id: str | None = None
) -> dict:
    """添加到同花顺自选股。需要正式账号登录，请避免短时间重复提交，本接口不自动重试。

    code 为证券代码（如 600519 或 AAPL）；market_id 为同花顺旧市场编号（沪市 17，深市 33）；
    省略 group_id 时写入默认“我的自选”，填写时写入指定自定义分组。"""
    body: dict = {"code": code, "market_id": market_id}
    if group_id is not None:
        body["group_id"] = group_id
    return await client.post("/v1/market/session/self-stock", body)


async def delete_self_stock(
    code: str, market_id: str, group_id: str | None = None
) -> dict:
    """从同花顺自选股删除。需要正式账号登录，请避免短时间重复提交，本接口不自动重试。

    code 为证券代码；market_id 为同花顺旧市场编号（沪市 17，深市 33）；
    省略 group_id 时操作默认自选，填写时操作指定自定义分组。"""
    body: dict = {"code": code, "market_id": market_id}
    if group_id is not None:
        body["group_id"] = group_id
    return await client.delete("/v1/market/session/self-stock", body)


async def self_stock_groups() -> dict:
    """查询同花顺自选股分组：读取分组及分组内证券。内置分组标记为只读；未登录或会话失效时返回错误。"""
    return await client.get("/v1/market/session/self-stock/groups")


async def create_self_stock_group(name: str) -> dict:
    """创建同花顺自选股分组。需要正式账号登录；分组版本由服务自动读取，请避免短时间重复提交。"""
    return await client.post(
        "/v1/market/session/self-stock/groups", {"name": name}
    )


async def delete_self_stock_group(group_id: str) -> dict:
    """删除同花顺自选股分组。内置只读分组不能删除；请避免短时间重复提交。"""
    return await client.delete(
        "/v1/market/session/self-stock/groups", {"group_id": group_id}
    )


async def sms_begin(phone_number: str, country_code: str = "86") -> dict:
    """手机短信登录：获取滑块验证码。返回滑块验证底图、滑块图片及登录流程编号；
    完成滑块后，请使用同一流程编号获取短信验证码。"""
    return await client.post(
        "/v1/market/session/sms/begin",
        {"country_code": country_code, "phone_number": phone_number},
    )


async def sms_complete(flow_id: int, verification_code: str) -> dict:
    """手机短信登录：验证码登录。提交短信验证码并登录行情账户；
    成功后自动为当前系统用户安全保存登录信息。

    flow_id 为开始短信登录时返回的流程编号。"""
    return await client.post(
        "/v1/market/session/sms/complete",
        {"flow_id": flow_id, "verification_code": verification_code},
    )


async def sms_send_code(flow_id: int, relative_x: int, relative_y: int) -> dict:
    """手机短信登录：获取短信验证码。提交滑块拼图相对底图左上角的最终坐标（像素），
    并向登录手机号发送验证码，每次请求发送一条短信。

    relative_x/relative_y 是最终坐标而非相对 initial_x/initial_y 的移动增量；
    仅横向拖动时 relative_y 通常应原样传回 initial_y 而不是 0。"""
    return await client.post(
        "/v1/market/session/sms/send-code",
        {"flow_id": flow_id, "relative_x": relative_x, "relative_y": relative_y},
    )
