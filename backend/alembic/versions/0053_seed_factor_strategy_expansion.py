"""seed: 落地 2026-10-01 因子/策略大扩展（56 因子 + 18 条 rule 策略）

Revision ID: 0053
Revises: 0052
Create Date: 2026-10-02

背景：该批数据 2026-10-01 由临时脚本直接灌库（/tmp/new_factors.sql 54 条因子 +
/tmp/gen_strategies.py 14 条策略，另有 4 条 09-17 手工 rule 策略），未进任何迁移；
新环境 alembic upgrade 后将缺失。本迁移将其落地为正式种子，本迁移即唯一真源。

内容：
1. 56 条预置因子（source=preset）：54 条量价因子（反转/量价/波动/流动性/趋势，
   来源 Alpha101 复现、华泰/开源金工研报、社区经典）+ day_chg/gap_pct 两条
   custom 转 preset（被预置策略引用，保证种子自包含）。
2. 18 条预置 rule 策略（is_preset=True）：14 条 10-01 新增 + 4 条 09-17 手工创建；
   status 镜像 2026-10-01 回测结论（8 启用 / 10 停用）；股票池冻结当时的
   沪深300/中证500 权重前 60 快照（低波红利增强为 20 只红利池）。
   rule_config 的 factor_id 在迁移内按 code 实时解析，查不到即抛错回滚，
   杜绝静默错链。

ID 台账：
- 因子：0034 已用 2942406616009200-9217（17 条）；本迁移自 2942406616009301 起 56 条（至 9356）
- 策略：0016/0027 已用 2942406616009101-9112（12 条）；本迁移自 2942406616009401 起 18 条（至 9418）

幂等：因子按 code、策略按 name 查重跳过——当前环境两者已全量存在，本迁移 no-op。
已知差异（不改写用户数据故意的）：当前环境 18 条策略保持 is_preset=f、
day_chg/gap_pct 保持 source=custom；仅新环境生效为 preset。
"""
from datetime import datetime
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = '0053'
down_revision: Union[str, Sequence[str], None] = '0052'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_FACTOR_ID_BASE = 2942406616009300
_STRATEGY_ID_BASE = 2942406616009400
_DT = datetime(2026, 10, 1, 12, 0, 0)

# ----------------------------------------------------------------------
# 56 条预置因子（公式经 modules/factor/services/formula.py 白名单校验）
# ----------------------------------------------------------------------
_PRESET_FACTORS = [
    # ===== 反转类 =====
    {
        'seq': 1, 'code': 'rev5', 'name': '5日反转',
        'category': 'reversal',
        'formula': '-SUM(pct_chg, 5)',
        'description': '近5日累计涨幅取负，A股短反转证据强（华泰/开源长期跟踪），值大=超跌',
        'source_url': None,
    },
    {
        'seq': 2, 'code': 'rev20', 'name': '20日反转',
        'category': 'reversal',
        'formula': '-SUM(pct_chg, 20)',
        'description': '近20日累计涨幅取负，经典月度反转，值大=超跌',
        'source_url': None,
    },
    {
        'seq': 3, 'code': 'rev60', 'name': '60日反转',
        'category': 'reversal',
        'formula': '-SUM(pct_chg, 60)',
        'description': '近60日累计涨幅取负，A股中期亦偏反转',
        'source_url': None,
    },
    {
        'seq': 4, 'code': 'ideal_rev_high', 'name': '理想反转-高成交额日',
        'category': 'reversal',
        'formula': '0 - SUM(IF(amount > MA(amount, 20), pct_chg, 0), 20)',
        'description': '开源金工理想反转日线近似：仅高成交额日收益取负求和，放量上涨后回落概率大',
        'source_url': None,
    },
    {
        'seq': 5, 'code': 'ideal_rev_low', 'name': '理想反转-低成交额日',
        'category': 'reversal',
        'formula': 'SUM(IF(amount <= MA(amount, 20), pct_chg, 0), 20)',
        'description': '开源金工理想反转日线近似：仅低成交额日收益求和，与 ideal_rev_high 合成完整理想反转',
        'source_url': None,
    },
    {
        'seq': 6, 'code': 'amt_rev20', 'name': '成交额加权反转',
        'category': 'reversal',
        'formula': '0 - SUM(amount * pct_chg, 20) / (SUM(amount, 20) + 0.001)',
        'description': '放量上涨的未来回落、放量下跌的未来反弹，值大优',
        'source_url': None,
    },
    {
        'seq': 7, 'code': 'overnight_rev20', 'name': '隔夜反转',
        'category': 'reversal',
        'formula': '0 - SUM(open / preclose - 1, 20)',
        'description': '隔夜跳空累计取负，隔夜过热者次日回落',
        'source_url': None,
    },
    {
        'seq': 8, 'code': 'intraday_rev20', 'name': '日内反转',
        'category': 'reversal',
        'formula': '0 - SUM(close / open - 1, 20)',
        'description': '日内实体累计取负，日内拉升过多者回落',
        'source_url': None,
    },
    {
        'seq': 9, 'code': 'up_days10', 'name': '近10日上涨天数',
        'category': 'reversal',
        'formula': 'COUNT(pct_chg > 0, 10)',
        'description': '连涨天数，情绪过热代理，值小优',
        'source_url': None,
    },
    {
        'seq': 10, 'code': 'er20', 'name': '路径效率系数ER',
        'category': 'reversal',
        'formula': 'ABS(SUM(pct_chg, 20)) / (SUM(ABS(pct_chg), 20) + 0.0001)',
        'description': '考夫曼效率系数：净位移/总路径，值小=路径杂乱=反转属性强',
        'source_url': None,
    },
    {
        'seq': 11, 'code': 'high120_dev', 'name': '距120日高点幅度',
        'category': 'reversal',
        'formula': '(close / (MAX(high, 120) + 0.001) - 1) * 100',
        'description': '距120日前高百分比，值小（负大）=反弹空间大',
        'source_url': None,
    },
    {
        'seq': 12, 'code': 'high250_dev', 'name': '距250日高点幅度',
        'category': 'reversal',
        'formula': '(close / (MAX(high, 250) + 0.001) - 1) * 100',
        'description': '52周高点接近度（George-Hwang动量），接近0=贴新高；反转用法值小优',
        'source_url': None,
    },
    {
        'seq': 13, 'code': 'rsi2', 'name': 'RSI2极值',
        'category': 'reversal',
        'formula': 'SUM(IF(pct_chg > 0, pct_chg, 0), 2) / (SUM(ABS(pct_chg), 2) + 0.0001) * 100',
        'description': '2日RSI，极值反转体系（<=5超卖买入，>=70止盈）',
        'source_url': None,
    },
    # ===== 量价类 =====
    {
        'seq': 14, 'code': 'vwap_vol_corr20', 'name': 'VWAP量相关20',
        'category': 'volume_price',
        'formula': 'CORR(vwap, volume, 20)',
        'description': 'VWAP与成交量相关性，负相关（量涨价跌）为佳，Alpha101 A股幸存结构',
        'source_url': None,
    },
    {
        'seq': 15, 'code': 'turn_ret_corr20', 'name': '量比收益相关20',
        'category': 'volume_price',
        'formula': 'CORR(volume / (MA(volume, 20) + 0.001), pct_chg, 20)',
        'description': '换手与收益相关性，负相关为佳',
        'source_url': None,
    },
    {
        'seq': 16, 'code': 'cpv_delta10', 'name': '量价相关变化10',
        'category': 'volume_price',
        'formula': 'DELTA(CORR(close, volume, 10), 10)',
        'description': '量价相关性变化率，走弱=背离修复',
        'source_url': None,
    },
    {
        'seq': 17, 'code': 'mf20', 'name': '资金流强度20',
        'category': 'volume_price',
        'formula': 'SUM(pct_chg * amount, 20) / (SUM(ABS(pct_chg) * amount, 20) + 0.001)',
        'description': '有向资金流占比，[-1,1]，过热（接近1）反转为佳',
        'source_url': None,
    },
    {
        'seq': 18, 'code': 'obv_mom20', 'name': 'OBV动量代理20',
        'category': 'volume_price',
        'formula': 'SUM(SIGN(pct_chg) * volume, 20) / (SUM(volume, 20) + 0.001)',
        'description': '能量潮动量代理，[-1,1]，过热反转为佳',
        'source_url': None,
    },
    {
        'seq': 19, 'code': 'clv10', 'name': '收盘位置累积CLV10',
        'category': 'volume_price',
        'formula': 'SUM((close - low - (high - close)) / (high - low + 0.001), 10)',
        'description': '收盘在日内区间的位置10日累积，值大=持续收强',
        'source_url': None,
    },
    {
        'seq': 20, 'code': 'close_vwap10', 'name': '收盘VWAP强度10',
        'category': 'volume_price',
        'formula': 'MA(close / (vwap + 0.001) - 1, 10)',
        'description': '收盘持续站在VWAP上方的程度，尾盘行为代理，过热回落',
        'source_url': None,
    },
    # ===== 波动类 =====
    {
        'seq': 21, 'code': 'vol60', 'name': '60日波动率',
        'category': 'volatility',
        'formula': 'STD(pct_chg, 60)',
        'description': '60日收益波动率（百分数单位），低波异象，值小优',
        'source_url': None,
    },
    {
        'seq': 22, 'code': 'max_chg20', 'name': '20日最大单日涨幅',
        'category': 'volatility',
        'formula': 'MAX(pct_chg, 20)',
        'description': 'Bali MAX彩票因子，近20日单日暴涨幅度，值小优',
        'source_url': None,
    },
    {
        'seq': 23, 'code': 'down_vol_ratio20', 'name': '下行波动占比20',
        'category': 'volatility',
        'formula': 'STD(IF(pct_chg < 0, pct_chg, 0), 20) / (STD(pct_chg, 20) + 0.0001)',
        'description': '华泰全频段：下行波动占总波动比例，值小优',
        'source_url': None,
    },
    {
        'seq': 24, 'code': 'skew20', 'name': '收益偏度20',
        'category': 'volatility',
        'formula': 'SUM(pct_chg * pct_chg * pct_chg, 20) / (STD(pct_chg, 20) * STD(pct_chg, 20) * STD(pct_chg, 20) * 20 + 0.000001)',
        'description': '三阶矩偏度，博彩偏好代理，值小优',
        'source_url': None,
    },
    {
        'seq': 25, 'code': 'amp_high20', 'name': '理想振幅-高价态',
        'category': 'volatility',
        'formula': 'SUM(IF(close > MA(close, 20), (high - low) / preclose * 100, 0), 20)',
        'description': '开源理想振幅日线近似：高价态振幅累计，放振幅=出货特征，值小优',
        'source_url': None,
    },
    {
        'seq': 26, 'code': 'amp_low20', 'name': '理想振幅-低价态',
        'category': 'volatility',
        'formula': 'SUM(IF(close <= MA(close, 20), (high - low) / preclose * 100, 0), 20)',
        'description': '开源理想振幅日线近似：低价态振幅累计',
        'source_url': None,
    },
    {
        'seq': 27, 'code': 'amp_diff20', 'name': '理想振幅差',
        'category': 'volatility',
        'formula': 'SUM(IF(close > MA(close, 20), (high - low) / preclose * 100, 0), 20) - SUM(IF(close <= MA(close, 20), (high - low) / preclose * 100, 0), 20)',
        'description': '高价态-低价态振幅差，值小优',
        'source_url': None,
    },
    {
        'seq': 28, 'code': 'upper_shadow20', 'name': '平均上影线20',
        'category': 'volatility',
        'formula': 'MA((high - IF(open > close, open, close)) / preclose * 100, 20)',
        'description': '冲高回落幅度均值，抛压代理，值小优',
        'source_url': None,
    },
    {
        'seq': 29, 'code': 'lower_shadow20', 'name': '平均下影线20',
        'category': 'volatility',
        'formula': 'MA((IF(open < close, open, close) - low) / preclose * 100, 20)',
        'description': '下探回升幅度均值，承接力代理，值大优',
        'source_url': None,
    },
    {
        'seq': 30, 'code': 'gap_freq20', 'name': '跳空频率20',
        'category': 'volatility',
        'formula': 'SUM(ABS(open / preclose - 1) * 100, 20)',
        'description': '跳空缺口幅度累计（百分数），值小优',
        'source_url': None,
    },
    {
        'seq': 31, 'code': 'hl_vol20', 'name': '高低价比波动20',
        'category': 'volatility',
        'formula': 'STD(high / (low + 0.001), 20)',
        'description': '日内高低价比值的波动，值小优',
        'source_url': None,
    },
    # ===== 流动性/换手代理类 =====
    {
        'seq': 32, 'code': 'vr20', 'name': '20日量比',
        'category': 'liquidity',
        'formula': 'volume / (MA(volume, 20) + 0.001)',
        'description': '成交量/20日均量，换手代理，缩量（值小）为佳',
        'source_url': None,
    },
    {
        'seq': 33, 'code': 'bias_turn', 'name': '换手乖离bias_turn',
        'category': 'liquidity',
        'formula': 'MA(volume, 5) / (MA(volume, 20) + 0.001)',
        'description': '华泰换手率乖离（5日/20日均量），值小优',
        'source_url': None,
    },
    {
        'seq': 34, 'code': 'std_turn20', 'name': '换手波动std_turn20',
        'category': 'liquidity',
        'formula': 'STD(volume / (MA(volume, 20) + 0.001), 20)',
        'description': '华泰换手率波动，值小优',
        'source_url': None,
    },
    {
        'seq': 35, 'code': 'vr120', 'name': '长期量比120',
        'category': 'liquidity',
        'formula': 'MA(volume, 20) / (MA(volume, 120) + 0.001)',
        'description': '20日均量/120日均量，长期活跃度变化，值小优',
        'source_url': None,
    },
    {
        'seq': 36, 'code': 'high_vol_days20', 'name': '放量天数占比20',
        'category': 'liquidity',
        'formula': 'COUNT(volume > MA(volume, 20), 20) / 20',
        'description': '近20日放量（量>20均量）天数占比，值小优',
        'source_url': None,
    },
    {
        'seq': 37, 'code': 'amihud20', 'name': 'Amihud非流动性20',
        'category': 'liquidity',
        'formula': 'MA(ABS(pct_chg) / (amount + 1), 20) * 100000000',
        'description': 'Amihud非流动性（流动性溢价），值大优但与规模共线',
        'source_url': None,
    },
    {
        'seq': 38, 'code': 'amt_size20', 'name': '成交额规模20',
        'category': 'liquidity',
        'formula': 'LOG(MA(amount, 20) + 1)',
        'description': '20日均成交额对数，规模代理，值小=小票溢价',
        'source_url': None,
    },
    # ===== 趋势/动量类 =====
    {
        'seq': 39, 'code': 'ir_mom60', 'name': '信息比率动量60',
        'category': 'momentum',
        'formula': 'SUM(pct_chg, 60) / (STD(pct_chg, 60) + 0.0001)',
        'description': '收益/波动的动量质量（残差动量日线近似），趋势策略值大优',
        'source_url': None,
    },
    {
        'seq': 40, 'code': 'rsv20', 'name': '20日价格位置RSV',
        'category': 'momentum',
        'formula': '(close - MIN(low, 20)) / (MAX(high, 20) - MIN(low, 20) + 0.001)',
        'description': '收盘在20日区间的位置[0,1]，低位反转用法值小优',
        'source_url': None,
    },
    {
        'seq': 41, 'code': 'cgo60', 'name': '获利盘代理CGO60',
        'category': 'momentum',
        'formula': '(close / (MA(vwap, 60) + 0.001) - 1) * 100',
        'description': '现价相对60日VWAP均价的浮盈（处置效应代理），值大=抛压重',
        'source_url': None,
    },
    # ===== trend =====
    {
        'seq': 42, 'code': 'ma60_dev', 'name': '60线乖离',
        'category': 'trend',
        'formula': '(close - MA(close, 60)) / MA(close, 60) * 100',
        'description': '收盘价相对60日均线乖离百分比',
        'source_url': None,
    },
    {
        'seq': 43, 'code': 'ma250_dev', 'name': '年线乖离',
        'category': 'trend',
        'formula': '(close - MA(close, 250)) / MA(close, 250) * 100',
        'description': '收盘价相对250日均线乖离百分比，>0=长期多头',
        'source_url': None,
    },
    {
        'seq': 44, 'code': 'ma_bull', 'name': '均线多头排列',
        'category': 'trend',
        'formula': 'IF(MA(close, 5) > MA(close, 20), IF(MA(close, 20) > MA(close, 60), 1, 0), 0)',
        'description': 'MA5>MA20>MA60 多头排列取1，否则0',
        'source_url': None,
    },
    {
        'seq': 45, 'code': 'ma20_slope', 'name': '20线斜率',
        'category': 'trend',
        'formula': '(MA(close, 20) - REF(MA(close, 20), 5)) / (REF(MA(close, 20), 5) + 0.001) * 100',
        'description': '20日均线5日斜率百分比，>0=中期趋势向上',
        'source_url': None,
    },
    {
        'seq': 46, 'code': 'ma60_slope', 'name': '60线斜率',
        'category': 'trend',
        'formula': '(MA(close, 60) - REF(MA(close, 60), 20)) / (REF(MA(close, 60), 20) + 0.001) * 100',
        'description': '60日均线20日斜率百分比，>0=季线向上',
        'source_url': None,
    },
    {
        'seq': 47, 'code': 'box_amp30', 'name': '30日箱体振幅',
        'category': 'trend',
        'formula': '(MAX(high, 30) - MIN(low, 30)) / (MIN(low, 30) + 0.001) * 100',
        'description': '30日高低点区间振幅百分比，值小=平台整理',
        'source_url': None,
    },
    {
        'seq': 48, 'code': 'donchian_break20', 'name': '20日突破度',
        'category': 'trend',
        'formula': '(close / (REF(MAX(high, 20), 1) + 0.001) - 1) * 100',
        'description': '收盘相对前20日最高价（不含当日）突破百分比，>0=唐奇安突破',
        'source_url': None,
    },
    {
        'seq': 49, 'code': 'donchian_break30', 'name': '30日突破度',
        'category': 'trend',
        'formula': '(close / (REF(MAX(high, 30), 1) + 0.001) - 1) * 100',
        'description': '收盘相对前30日最高价（不含当日）突破百分比',
        'source_url': None,
    },
    {
        'seq': 50, 'code': 'limit_up_days15', 'name': '近15日涨停天数',
        'category': 'trend',
        'formula': 'COUNT(pct_chg >= 9.5, 15)',
        'description': '近15日涨幅>=9.5%的天数（涨停计数）',
        'source_url': None,
    },
    {
        'seq': 51, 'code': 'bias13', 'name': '13线乖离',
        'category': 'trend',
        'formula': '(close - MA(close, 13)) / MA(close, 13) * 100',
        'description': '收盘价相对13日均线乖离百分比（龙回头回踩用）',
        'source_url': None,
    },
    # ===== 趋势/动量类 =====
    {
        'seq': 52, 'code': 'roc15', 'name': '15日涨幅',
        'category': 'momentum',
        'formula': 'DELTA(close, 15) / (REF(close, 15) + 0.001) * 100',
        'description': '近15日累计涨幅百分比',
        'source_url': None,
    },
    # ===== trend =====
    {
        'seq': 53, 'code': 'ma5_dev', 'name': '5线乖离',
        'category': 'trend',
        'formula': '(close - MA(close, 5)) / MA(close, 5) * 100',
        'description': '收盘价相对5日均线乖离百分比',
        'source_url': None,
    },
    # ===== 趋势/动量类 =====
    {
        'seq': 54, 'code': 'max_chg10', 'name': '近10日最大涨幅',
        'category': 'momentum',
        'formula': 'MAX(pct_chg, 10)',
        'description': '近10日最大单日涨幅（强度确认用）',
        'source_url': None,
    },
    # ===== custom 转 preset（被预置策略引用）=====
    {
        'seq': 55, 'code': 'day_chg', 'name': '当日涨幅',
        'category': 'price',
        'formula': 'pct_chg',
        'description': '当日涨跌幅%（DSL 内置字段 pct_chg 直引），用于防追高类条件',
        'source_url': None,
    },
    {
        'seq': 56, 'code': 'gap_pct', 'name': '跳空缺口幅度',
        'category': 'price',
        'formula': '(open - preclose) / preclose * 100',
        'description': '当日开盘相对昨收的跳空幅度%，负值为向下跳空',
        'source_url': None,
    },
]

# ----------------------------------------------------------------------
# 18 条预置 rule 策略
# 条件元组：(factor_code, op, value)；risk = (止损%, 止盈%, 回撤%, 最大持仓)
# 股票池为 2026-10-01 沪深300/中证500 权重前 60 快照（红利池为 20 只）
# ----------------------------------------------------------------------
_PRESET_STRATEGIES = [
    {
        'seq': 1, 'name': '唐奇安趋势突破',
        'description': '突破前20日最高价+均线多头+放量确认，趋势跟踪（海龟日线简化）',
        'buy': [('donchian_break20', 'gt', 0), ('ma_bull', 'gte', 1), ('vr20', 'gte', 1.2), ('ir_mom60', 'gt', 0)],
        'sell': [('ma20_slope', 'lt', 0)],
        'risk': (8.0000, 40.0000, 15.0000, 4),
        'status': False,
        'pool_size': 60,
        'pool': ['600900', '600905', '600918', '600919', '600926', '600930', '600938', '600941', '600958', '600989', '600999', '601006', '601009', '601012', '601018', '601021', '601058', '601059', '601066', '601077', '601088', '601100', '601111', '601117', '601127', '601136', '601138', '601166', '601169', '601186', '601211', '601225', '601229', '601238', '601288', '601318', '601319', '601328', '601336', '601360', '601377', '601390', '601398', '601456', '601600', '601601', '601607', '601618', '601628', '601633', '601658', '601668', '601669', '601688', '601689', '601698', '601727', '601728', '601766', '600893'],
    },
    {
        'seq': 2, 'name': '平台放量突破',
        'description': '均线多头+30日箱体振幅<=15%+放量突破平台，变盘确认',
        'buy': [('ma_bull', 'gte', 1), ('box_amp30', 'lte', 20), ('donchian_break30', 'gt', 0), ('vr20', 'gte', 1.5)],
        'sell': [('ma20_slope', 'lt', 0)],
        'risk': (6.0000, 30.0000, 12.0000, 4),
        'status': False,
        'pool_size': 60,
        'pool': ['600008', '600021', '600032', '600038', '600060', '600062', '600095', '600098', '600100', '600105', '600109', '600126', '600131', '600132', '600141', '600143', '600153', '600157', '600161', '600166', '600170', '600171', '600177', '600208', '600256', '600282', '600292', '600295', '600298', '600299', '600312', '600316', '600329', '600332', '600339', '600348', '600350', '600352', '600363', '600369', '600377', '600378', '600380', '600390', '600392', '600398', '600435', '600483', '600486', '600497', '600498', '600499', '600511', '600516', '600517', '600521', '600535', '600536', '600546', '600004'],
    },
    {
        'seq': 3, 'name': '52周新高动量',
        'description': '贴近250日高点+季线向上，George-Hwang动量A股版',
        'buy': [('high250_dev', 'gte', -5), ('ma60_dev', 'gt', 0), ('ma60_slope', 'gt', 0)],
        'sell': [('high250_dev', 'lt', -15)],
        'risk': (10.0000, 50.0000, 18.0000, 4),
        'status': True,
        'pool_size': 60,
        'pool': ['600900', '600905', '600918', '600919', '600926', '600930', '600938', '600941', '600958', '600989', '600999', '601006', '601009', '601012', '601018', '601021', '601058', '601059', '601066', '601077', '601088', '601100', '601111', '601117', '601127', '601136', '601138', '601166', '601169', '601186', '601211', '601225', '601229', '601238', '601288', '601318', '601319', '601328', '601336', '601360', '601377', '601390', '601398', '601456', '601600', '601601', '601607', '601618', '601628', '601633', '601658', '601668', '601669', '601688', '601689', '601698', '601727', '601728', '601766', '600893'],
    },
    {
        'seq': 4, 'name': '缩量回踩20线',
        'description': '多头排列+20线向上+回踩20线±3%+缩量，趋势回调介入',
        'buy': [('ma_bull', 'gte', 1), ('ma20_slope', 'gt', 0), ('ma60_slope', 'gt', 0), ('ir_mom60', 'gt', 0), ('bias20', 'gte', -3), ('bias20', 'lte', 3), ('vr20', 'lte', 0.6), ('ma60_dev', 'gt', 0)],
        'sell': [('ma60_dev', 'lt', 0)],
        'risk': (5.0000, 25.0000, 10.0000, 5),
        'status': False,
        'pool_size': 60,
        'pool': ['600008', '600021', '600032', '600038', '600060', '600062', '600095', '600098', '600100', '600105', '600109', '600126', '600131', '600132', '600141', '600143', '600153', '600157', '600161', '600166', '600170', '600171', '600177', '600208', '600256', '600282', '600292', '600295', '600298', '600299', '600312', '600316', '600329', '600332', '600339', '600348', '600350', '600352', '600363', '600369', '600377', '600378', '600380', '600390', '600392', '600398', '600435', '600483', '600486', '600497', '600498', '600499', '600511', '600516', '600517', '600521', '600535', '600536', '600546', '600004'],
    },
    {
        'seq': 5, 'name': '龙回头-涨停回踩13线',
        'description': '近10日有大阳(>=8%)+缩量回踩13线±2%+中期多头，强势股二次介入',
        'buy': [('max_chg10', 'gte', 8), ('ma60_dev', 'gt', 0), ('bias13', 'gte', -2), ('bias13', 'lte', 2), ('vr20', 'lte', 0.6)],
        'sell': [('bias13', 'lt', -8)],
        'risk': (7.0000, 20.0000, 10.0000, 4),
        'status': True,
        'pool_size': 60,
        'pool': ['600008', '600021', '600032', '600038', '600060', '600062', '600095', '600098', '600100', '600105', '600109', '600126', '600131', '600132', '600141', '600143', '600153', '600157', '600161', '600166', '600170', '600171', '600177', '600208', '600256', '600282', '600292', '600295', '600298', '600299', '600312', '600316', '600329', '600332', '600339', '600348', '600350', '600352', '600363', '600369', '600377', '600378', '600380', '600390', '600392', '600398', '600435', '600483', '600486', '600497', '600498', '600499', '600511', '600516', '600517', '600521', '600535', '600536', '600546', '600004'],
    },
    {
        'seq': 6, 'name': '龙头首阴',
        'description': '15日涨幅>=40%+近15日2次涨停+首阴不破5线+量能未失控，博反包（高风险）',
        'buy': [('roc15', 'gte', 40), ('limit_up_days15', 'gte', 2), ('day_chg', 'lt', 0), ('ma5_dev', 'gt', 0), ('vr20', 'lte', 2)],
        'sell': [('ma5_dev', 'lt', -3)],
        'risk': (8.0000, 20.0000, 8.0000, 3),
        'status': False,
        'pool_size': 60,
        'pool': ['600008', '600021', '600032', '600038', '600060', '600062', '600095', '600098', '600100', '600105', '600109', '600126', '600131', '600132', '600141', '600143', '600153', '600157', '600161', '600166', '600170', '600171', '600177', '600208', '600256', '600282', '600292', '600295', '600298', '600299', '600312', '600316', '600329', '600332', '600339', '600348', '600350', '600352', '600363', '600369', '600377', '600378', '600380', '600390', '600392', '600398', '600435', '600483', '600486', '600497', '600498', '600499', '600511', '600516', '600517', '600521', '600535', '600536', '600546', '600004'],
    },
    {
        'seq': 7, 'name': '动量轮动-沪深300',
        'description': '20日动量>0+季线上+动量质量为正，动量转弱即空仓',
        'buy': [('roc20', 'gt', 0), ('ma60_dev', 'gt', 0), ('ir_mom60', 'gt', 0), ('ma20_slope', 'gt', 0)],
        'sell': [('roc20', 'lte', 0)],
        'risk': (10.0000, 60.0000, 18.0000, 4),
        'status': False,
        'pool_size': 60,
        'pool': ['600900', '600905', '600918', '600919', '600926', '600930', '600938', '600941', '600958', '600989', '600999', '601006', '601009', '601012', '601018', '601021', '601058', '601059', '601066', '601077', '601088', '601100', '601111', '601117', '601127', '601136', '601138', '601166', '601169', '601186', '601211', '601225', '601229', '601238', '601288', '601318', '601319', '601328', '601336', '601360', '601377', '601390', '601398', '601456', '601600', '601601', '601607', '601618', '601628', '601633', '601658', '601668', '601669', '601688', '601689', '601698', '601727', '601728', '601766', '600893'],
    },
    {
        'seq': 8, 'name': '动量轮动-中证500',
        'description': '20日动量>0+季线上+动量质量为正，动量转弱即空仓',
        'buy': [('roc20', 'gt', 0), ('ma60_dev', 'gt', 0), ('ir_mom60', 'gt', 0), ('ma20_slope', 'gt', 0)],
        'sell': [('roc20', 'lte', 0)],
        'risk': (10.0000, 60.0000, 18.0000, 4),
        'status': False,
        'pool_size': 60,
        'pool': ['600008', '600021', '600032', '600038', '600060', '600062', '600095', '600098', '600100', '600105', '600109', '600126', '600131', '600132', '600141', '600143', '600153', '600157', '600161', '600166', '600170', '600171', '600177', '600208', '600256', '600282', '600292', '600295', '600298', '600299', '600312', '600316', '600329', '600332', '600339', '600348', '600350', '600352', '600363', '600369', '600377', '600378', '600380', '600390', '600392', '600398', '600435', '600483', '600486', '600497', '600498', '600499', '600511', '600516', '600517', '600521', '600535', '600536', '600546', '600004'],
    },
    {
        'seq': 9, 'name': '低波稳健增强',
        'description': '60日低波+年线上+季线向上+下行波动占比低，红利低波纯量价代理',
        'buy': [('vol60', 'lte', 1.5), ('ma250_dev', 'gt', 0), ('ma60_slope', 'gt', 0), ('down_vol_ratio20', 'lte', 0.7)],
        'sell': [('ma250_dev', 'lt', 0)],
        'risk': (10.0000, 50.0000, 20.0000, 5),
        'status': True,
        'pool_size': 60,
        'pool': ['600900', '600905', '600918', '600919', '600926', '600930', '600938', '600941', '600958', '600989', '600999', '601006', '601009', '601012', '601018', '601021', '601058', '601059', '601066', '601077', '601088', '601100', '601111', '601117', '601127', '601136', '601138', '601166', '601169', '601186', '601211', '601225', '601229', '601238', '601288', '601318', '601319', '601328', '601336', '601360', '601377', '601390', '601398', '601456', '601600', '601601', '601607', '601618', '601628', '601633', '601658', '601668', '601669', '601688', '601689', '601698', '601727', '601728', '601766', '600893'],
    },
    {
        'seq': 10, 'name': '深度乖离反弹',
        'description': '20线乖离<=-12+年线上+当日收阳+缩量，均值回归（排除下跌通道）',
        'buy': [('bias20', 'lte', -8), ('ma250_dev', 'gt', -10), ('day_chg', 'gt', 0), ('vr20', 'lte', 1.2)],
        'sell': [('bias20', 'gte', -2)],
        'risk': (6.0000, 15.0000, 8.0000, 5),
        'status': False,
        'pool_size': 60,
        'pool': ['600900', '600905', '600918', '600919', '600926', '600930', '600938', '600941', '600958', '600989', '600999', '601006', '601009', '601012', '601018', '601021', '601058', '601059', '601066', '601077', '601088', '601100', '601111', '601117', '601127', '601136', '601138', '601166', '601169', '601186', '601211', '601225', '601229', '601238', '601288', '601318', '601319', '601328', '601336', '601360', '601377', '601390', '601398', '601456', '601600', '601601', '601607', '601618', '601628', '601633', '601658', '601668', '601669', '601688', '601689', '601698', '601727', '601728', '601766', '600893'],
    },
    {
        'seq': 11, 'name': 'RSI极值反转',
        'description': 'RSI2<=5极值超卖+季线上+当日收阳，短线均值回归',
        'buy': [('rsi2', 'lte', 3), ('ma60_dev', 'gt', 0), ('day_chg', 'gt', 0), ('vr20', 'lte', 1.2)],
        'sell': [('rsi2', 'gte', 70)],
        'risk': (5.0000, 12.0000, 6.0000, 5),
        'status': False,
        'pool_size': 60,
        'pool': ['600900', '600905', '600918', '600919', '600926', '600930', '600938', '600941', '600958', '600989', '600999', '601006', '601009', '601012', '601018', '601021', '601058', '601059', '601066', '601077', '601088', '601100', '601111', '601117', '601127', '601136', '601138', '601166', '601169', '601186', '601211', '601225', '601229', '601238', '601288', '601318', '601319', '601328', '601336', '601360', '601377', '601390', '601398', '601456', '601600', '601601', '601607', '601618', '601628', '601633', '601658', '601668', '601669', '601688', '601689', '601698', '601727', '601728', '601766', '600893'],
    },
    {
        'seq': 12, 'name': '理想反转低吸',
        'description': '高成交额日累计跌幅>=5%+低价态不弱+年线上+20日超跌，开源理想反转日线版',
        'buy': [('ideal_rev_high', 'gte', 3), ('rev20', 'gte', 6), ('ma250_dev', 'gt', 0)],
        'sell': [('rev20', 'lte', 0)],
        'risk': (6.0000, 18.0000, 8.0000, 5),
        'status': False,
        'pool_size': 60,
        'pool': ['600008', '600021', '600032', '600038', '600060', '600062', '600095', '600098', '600100', '600105', '600109', '600126', '600131', '600132', '600141', '600143', '600153', '600157', '600161', '600166', '600170', '600171', '600177', '600208', '600256', '600282', '600292', '600295', '600298', '600299', '600312', '600316', '600329', '600332', '600339', '600348', '600350', '600352', '600363', '600369', '600377', '600378', '600380', '600390', '600392', '600398', '600435', '600483', '600486', '600497', '600498', '600499', '600511', '600516', '600517', '600521', '600535', '600536', '600546', '600004'],
    },
    {
        'seq': 13, 'name': '趋势成长动量',
        'description': '距年高<25%+动量质量强+季线上+20线向上，CANSLIM纯量价代理',
        'buy': [('high250_dev', 'gte', -15), ('ir_mom60', 'gte', 6), ('ma60_dev', 'gt', 0), ('ma20_slope', 'gt', 0)],
        'sell': [('ma60_dev', 'lt', 0)],
        'risk': (8.0000, 60.0000, 15.0000, 4),
        'status': False,
        'pool_size': 60,
        'pool': ['600008', '600021', '600032', '600038', '600060', '600062', '600095', '600098', '600100', '600105', '600109', '600126', '600131', '600132', '600141', '600143', '600153', '600157', '600161', '600166', '600170', '600171', '600177', '600208', '600256', '600282', '600292', '600295', '600298', '600299', '600312', '600316', '600329', '600332', '600339', '600348', '600350', '600352', '600363', '600369', '600377', '600378', '600380', '600390', '600392', '600398', '600435', '600483', '600486', '600497', '600498', '600499', '600511', '600516', '600517', '600521', '600535', '600536', '600546', '600004'],
    },
    {
        'seq': 14, 'name': '超跌反转Pro',
        'description': '20日超跌>=10%+RSI14<=35+路径杂乱+年线上+当日收阳',
        'buy': [('rev20', 'gte', 6), ('rsi14', 'lte', 35), ('ma250_dev', 'gt', -10)],
        'sell': [('rev20', 'lte', 0)],
        'risk': (5.0000, 15.0000, 7.0000, 5),
        'status': True,
        'pool_size': 60,
        'pool': ['600900', '600905', '600918', '600919', '600926', '600930', '600938', '600941', '600958', '600989', '600999', '601006', '601009', '601012', '601018', '601021', '601058', '601059', '601066', '601077', '601088', '601100', '601111', '601117', '601127', '601136', '601138', '601166', '601169', '601186', '601211', '601225', '601229', '601238', '601288', '601318', '601319', '601328', '601336', '601360', '601377', '601390', '601398', '601456', '601600', '601601', '601607', '601618', '601628', '601633', '601658', '601668', '601669', '601688', '601689', '601698', '601727', '601728', '601766', '600893'],
    },
    {
        'seq': 15, 'name': '超跌反转',
        'description': '规则型：bias20<-6 且 rsi14<35 深度超跌买入，bias20>0 回归均线上方卖出（HS300 权重前60）',
        'buy': [('bias20', 'lt', -8.0), ('rsi14', 'lt', 35.0), ('gap_pct', 'gt', 0)],
        'sell': [('bias20', 'gt', 0.0)],
        'risk': (6.0000, 12.0000, 6.0000, 5),
        'status': True,
        'pool_size': 60,
        'pool': ['000001', '000002', '000063', '000100', '000157', '000166', '000301', '000333', '000338', '000408', '000425', '000538', '000568', '000596', '000617', '000625', '000630', '000651', '000657', '000708', '000725', '000768', '000776', '000792', '000807', '000858', '000895', '000938', '000963', '000975', '000977', '000988', '000999', '001280', '001391', '001965', '001979', '002001', '002027', '002028', '002049', '002050', '002074', '002142', '002179', '002202', '002230', '002236', '002241', '002304', '002311', '002352', '002353', '002371', '002384', '002415', '002422', '002460', '002463', '002466'],
    },
    {
        'seq': 16, 'name': '趋势动量',
        'description': '规则型：roc20>5 且量价正相关且 bias10<8 的趋势股买入，roc20<0 趋势破坏卖出（HS300 权重前60）',
        'buy': [('roc20', 'gt', 5.0), ('vol_price_corr20', 'gt', 0.0), ('bias10', 'lt', 8.0)],
        'sell': [('roc5', 'lt', -5)],
        'risk': (6.0000, 20.0000, 5.0000, 5),
        'status': True,
        'pool_size': 60,
        'pool': ['000001', '000002', '000063', '000100', '000157', '000166', '000301', '000333', '000338', '000408', '000425', '000538', '000568', '000596', '000617', '000625', '000630', '000651', '000657', '000708', '000725', '000768', '000776', '000792', '000807', '000858', '000895', '000938', '000963', '000975', '000977', '000988', '000999', '001280', '001391', '001965', '001979', '002001', '002027', '002028', '002049', '002050', '002074', '002142', '002179', '002202', '002230', '002236', '002241', '002304', '002311', '002352', '002353', '002371', '002384', '002415', '002422', '002460', '002463', '002466'],
    },
    {
        'seq': 17, 'name': '放量突破',
        'description': '规则型：vr5>2 放量 + 距20日高点3%内 + 日内强势买入，bias5>8 短线过热卖出（中证500 权重前60）',
        'buy': [('vr5', 'gt', 2.0), ('high20_dev', 'gt', -3.0), ('alpha101_101', 'gt', 0.0), ('day_chg', 'lt', 5.0)],
        'sell': [('bias5', 'gt', 8.0)],
        'risk': (3.0000, 8.0000, 5.0000, 5),
        'status': True,
        'pool_size': 60,
        'pool': ['000009', '000021', '000027', '000032', '000034', '000039', '000050', '000060', '000062', '000088', '000155', '000400', '000415', '000423', '000429', '000513', '000519', '000528', '000537', '000539', '000559', '000582', '000591', '000598', '000623', '000629', '000661', '000683', '000703', '000709', '000723', '000728', '000729', '000733', '000737', '000738', '000739', '000750', '000783', '000785', '000786', '000800', '000825', '000830', '000831', '000878', '000883', '000887', '000893', '000898', '000921', '000932', '000937', '000951', '000959', '000960', '000967', '000983', '000987', '000997'],
    },
    {
        'seq': 18, 'name': '低波红利增强',
        'description': '规则型：vol20<1.5 低波 + 抗跌(high20_dev>-8) + 未大涨(bias20<3) 买入，bias20>6 过热卖出（红利池复制自 9108）',
        'buy': [('vol20', 'lt', 2.0), ('high20_dev', 'gt', -8.0), ('bias20', 'lt', 3.0)],
        'sell': [('bias20', 'gt', 6.0)],
        'risk': (4.0000, 12.0000, 5.0000, 5),
        'status': True,
        'pool_size': 20,
        'pool': ['601398', '601939', '601288', '601988', '600036', '601318', '601088', '601898', '600900', '600886', '600023', '600011', '600941', '601728', '601006', '600019', '601111', '600028', '601857', '000895'],
    },
]

_FACTOR_TABLE = sa.table(
    'business_factor',
    sa.column('id', sa.BigInteger),
    sa.column('deleted_at', sa.DateTime),
    sa.column('created_at', sa.DateTime),
    sa.column('updated_at', sa.DateTime),
    sa.column('name', sa.String),
    sa.column('code', sa.String),
    sa.column('formula', sa.Text),
    sa.column('category', sa.String),
    sa.column('description', sa.String),
    sa.column('source', sa.String),
    sa.column('source_url', sa.String),
    sa.column('params', sa.JSON),
    sa.column('status', sa.Boolean),
)

_STRATEGY_TABLE = sa.table(
    'business_ai_strategy',
    sa.column('id', sa.BigInteger),
    sa.column('deleted_at', sa.DateTime),
    sa.column('created_at', sa.DateTime),
    sa.column('updated_at', sa.DateTime),
    sa.column('name', sa.String),
    sa.column('description', sa.String),
    sa.column('category', sa.String),
    sa.column('is_preset', sa.Boolean),
    sa.column('is_template', sa.Boolean),
    sa.column('strategy_type', sa.String),
    sa.column('rule_config', sa.JSON),
    sa.column('stock_pool', sa.JSON),
    sa.column('execute_periods', sa.JSON),
    sa.column('max_positions', sa.Integer),
    sa.column('stop_loss_pct', sa.Numeric),
    sa.column('take_profit_pct', sa.Numeric),
    sa.column('trailing_drawdown_pct', sa.Numeric),
    sa.column('status', sa.Boolean),
)


def upgrade() -> None:
    conn = op.get_bind()

    # ================================================================
    # 1. 幂等插入 56 条预置因子（按 code 查重，默认启用）
    # ================================================================
    existing_codes = {
        row[0] for row in conn.execute(
            sa.text("SELECT code FROM business_factor WHERE deleted_at IS NULL")
        )
    }
    factor_rows = []
    for item in _PRESET_FACTORS:
        if item['code'] in existing_codes:
            continue
        # 所有行必须带相同键集合（多行 INSERT 按首行键编译列清单）
        factor_rows.append({
            'id': _FACTOR_ID_BASE + item['seq'],
            'deleted_at': None,
            'created_at': _DT,
            'updated_at': None,
            'name': item['name'],
            'code': item['code'],
            'formula': item['formula'],
            'category': item['category'],
            'description': item['description'],
            'source': 'preset',
            'source_url': item['source_url'],
            'params': None,
            'status': True,
        })
    if factor_rows:
        op.bulk_insert(_FACTOR_TABLE, factor_rows)

    # ================================================================
    # 2. code -> id 解析（库存量 + 本迁移种子固定 ID）
    # ================================================================
    id_by_code = {
        row[1]: row[0] for row in conn.execute(
            sa.text("SELECT id, code FROM business_factor WHERE deleted_at IS NULL")
        )
    }
    for item in _PRESET_FACTORS:
        id_by_code.setdefault(item['code'], _FACTOR_ID_BASE + item['seq'])

    def _cond(code, operator, value):
        # 查不到即抛错回滚：宁可迁移失败，不可静默错链
        if code not in id_by_code:
            raise RuntimeError(f"预置策略因子引用无法解析: {code}")
        return {'factor_id': id_by_code[code], 'op': operator, 'value': value}

    # ================================================================
    # 3. 幂等插入 18 条预置 rule 策略（按 name 查重；status 镜像回测结论）
    # ================================================================
    existing_names = {
        row[0] for row in conn.execute(
            sa.text("SELECT name FROM business_ai_strategy WHERE deleted_at IS NULL")
        )
    }
    strategy_rows = []
    for item in _PRESET_STRATEGIES:
        if item['name'] in existing_names:
            continue
        stop_loss, take_profit, trailing, max_positions = item['risk']
        strategy_rows.append({
            'id': _STRATEGY_ID_BASE + item['seq'],
            'deleted_at': None,
            'created_at': _DT,
            'updated_at': None,
            'name': item['name'],
            'description': item['description'],
            'category': 'general',
            'is_preset': True,
            'is_template': False,
            'strategy_type': 'rule',
            'rule_config': {
                'buy_conditions': [_cond(*c) for c in item['buy']],
                'sell_conditions': [_cond(*c) for c in item['sell']],
            },
            'stock_pool': {'codes': list(item['pool'])},
            'execute_periods': ['post_close'],
            'max_positions': max_positions,
            'stop_loss_pct': stop_loss,
            'take_profit_pct': take_profit,
            'trailing_drawdown_pct': trailing,
            'status': item['status'],
        })
    if strategy_rows:
        op.bulk_insert(_STRATEGY_TABLE, strategy_rows)
        # 统一校验一次种子引用完整性（防御性，正常不应触发）
        for row in strategy_rows:
            for cond in row['rule_config']['buy_conditions'] + row['rule_config']['sell_conditions']:
                if not isinstance(cond['factor_id'], int):
                    raise RuntimeError(f"策略 {row['name']} 因子引用解析异常")


def downgrade() -> None:
    # 先删策略（引用因子）再删因子；限定 preset 防误删用户数据
    factor_ids = ', '.join(str(_FACTOR_ID_BASE + i['seq']) for i in _PRESET_FACTORS)
    strategy_ids = ', '.join(str(_STRATEGY_ID_BASE + i['seq']) for i in _PRESET_STRATEGIES)
    op.execute(
        f"DELETE FROM business_ai_strategy WHERE id IN ({strategy_ids}) AND is_preset = TRUE"
    )
    op.execute(
        f"DELETE FROM business_factor WHERE id IN ({factor_ids}) AND source = 'preset'"
    )
