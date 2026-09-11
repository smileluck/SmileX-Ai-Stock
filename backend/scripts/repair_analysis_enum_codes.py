"""一次性修复 2026-09-08 22:42 ~ 2026-09-11 期间被错误 sanitize 污染的分析报告。

背景：旧版 _sanitize_report_language 有两个 bug——think 块在前导致 json 块保护失效
（json 内枚举码被替换成中文），且 \b 词边界对中英粘连失效（正文英文码漏替换）。
本脚本对受影响 run：① 将 ai_raw_response json 块与 parsed_result 中被误替换的
枚举值按字段反向映射回英文码（前端 tag 配色依赖）；② 用新版 sanitize 重跑正文
（剥 think + 补替换漏网英文码）。幂等可重复执行。

用法：
    cd backend && ENVIR=dev .venv/bin/python -m scripts.repair_analysis_enum_codes
"""
import asyncio
import copy
import json
import os
import re
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from database.db_manager import init_pool, close_pool
from database.manager.async_manager import get_session
from database.models.business.analysis import BusinessAnalysisRun
from modules.analysis.services.analysis_executor import _sanitize_report_language

# 字段级反向映射（中文值 → 英文码）；退潮按字段区分 ebb/cooling
_FIELD_REVERSE = {
    "stage": {"低位启动": "start", "发酵": "ferment", "高潮": "climax",
              "退潮": "ebb", "蓄势观察": "observe"},
    "action": {"主攻": "attack", "潜伏埋伏": "ambush", "回避": "avoid", "观察": "watch"},
    "signal": {"高低切换": "switching", "分歧": "split", "共振": "resonance",
               "数据不足": "unknown"},
    "status": {"集结升温": "gathering", "发酵走强": "active", "高位过热": "hot",
               "退潮": "cooling", "平静": "flat"},
    "board_type": {"行业": "industry", "概念": "concept"},
}

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _fix_obj(node) -> int:
    """递归修复 dict/list 中的枚举值，返回修复处数"""
    fixed = 0
    if isinstance(node, dict):
        for k, v in node.items():
            if k in _FIELD_REVERSE and isinstance(v, str) and v in _FIELD_REVERSE[k]:
                node[k] = _FIELD_REVERSE[k][v]
                fixed += 1
            else:
                fixed += _fix_obj(v)
    elif isinstance(node, list):
        for item in node:
            fixed += _fix_obj(item)
    return fixed


async def main() -> None:
    await init_pool()
    try:
        async for db in get_session():
            runs = (await db.execute(
                select(BusinessAnalysisRun).where(
                    BusinessAnalysisRun.analysis_type.in_(["rotation", "sector"]),
                    BusinessAnalysisRun.status == "success",
                    BusinessAnalysisRun.run_date >= "2026-09-08",
                    BusinessAnalysisRun.deleted_at.is_(None),
                ).order_by(BusinessAnalysisRun.id)
            )).scalars().all()

            for run in runs:
                raw = run.ai_raw_response or ""
                fixed = 0
                m = _JSON_BLOCK_RE.search(raw)
                if m:
                    try:
                        obj = json.loads(m.group(1))
                    except json.JSONDecodeError:
                        obj = None
                    if obj is not None:
                        fixed = _fix_obj(obj)
                        if fixed:
                            new_block = "```json\n" + json.dumps(
                                obj, ensure_ascii=False, indent=2
                            ) + "\n```"
                            raw = raw[:m.start()] + new_block + raw[m.end():]
                else:
                    print(f"run_id={run.id} json 块缺失/截断，跳过 json 修复")
                if run.parsed_result:
                    # 必须深拷贝：浅拷贝共享嵌套对象，原地修复会同步改掉"原值"，
                    # 重新赋值时 SQLAlchemy 比对相等不标脏，UPDATE 被跳过
                    fixed_obj = copy.deepcopy(run.parsed_result)
                    fixed += _fix_obj(fixed_obj)
                    run.parsed_result = fixed_obj
                # 新版 sanitize 重跑：剥 think + 补正文漏网英文码（json 块已修复会被保护）
                run.ai_raw_response = _sanitize_report_language(raw)[:20000]
                print(f"run_id={run.id} type={run.analysis_type} date={run.run_date} 修复枚举值 {fixed} 处")
            await db.commit()
    finally:
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
