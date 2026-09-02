#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
企业财报 AI 解读服务层
- sync_reports: 抓取个股近几期财报指标并 upsert（手动/定时共用）
- submit_interpretation: 提交 AI 解读（落库即返、后台 LLM 生成，与 AnalysisExecutor 同模式）
- 持仓自动解读：定时任务收集持仓标的，对最新报告期无成功解读记录的个股提交解读
"""
import asyncio
import logging

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.response.response_code import CustomErrorCode
from core.exception.errors import CustomError
from database.models.business.financial import (
    BusinessFinancialReport,
    BusinessFinancialInterpretation,
    BusinessFinancialConfig,
)
from database.utils.timezone import timezone
from modules.financial.services import financial_fetcher

logger = logging.getLogger(__name__)

# 后台解读整体超时（秒）
INTERPRET_TIMEOUT = 600

# 解读注入的财报期数（最新 1 期 + 前 3 期对比）
INTERPRET_PERIODS = 4

# 后台任务强引用集合（防止 asyncio.Task 被 GC）
_BACKGROUND_TASKS: set[asyncio.Task] = set()

_FINANCIAL_SYSTEM_PROMPT = """你是 SmileX-AI-Stock 平台的 AI 财报分析师，负责对上市公司财报进行解读与业绩预测。

我会直接提供该公司的真实财务指标（最近几期报告期的营收/净利/同比/ROE/毛利率/负债率等），禁止凭空编造数据，分析必须基于所给数据。

输出要求（严格按以下顺序，两部分缺一不可）：
1. 先输出一个 JSON 对象（包在 ```json 代码块中），必须包含以下全部 6 个字段，不得省略任何字段：
```json
{
  "quality_rating": "良好",           // 本期财报质量评级：优秀 / 良好 / 一般 / 较差（必填）
  "next_quality_rating": "良好",      // 下一报告期预测评级：优秀 / 良好 / 一般 / 较差（必填，基于趋势预判给出，不可为空）
  "highlights": ["亮点1", "亮点2"],   // 2-4 条核心亮点
  "risks": ["风险1", "风险2"],        // 2-4 条风险点
  "forecast": {
    "direction": "改善",              // 下一报告期业绩方向：改善 / 持平 / 恶化
    "summary": "一句话预测（40字内），须包含核心依据",
    "drivers": ["驱动因素1", "驱动因素2"]  // 2-4 条下期盈利增长预测的来源分析（产品量价/产能投放/成本变化/并购并表/基数效应等具体依据）
  }
}
```
2. 再输出完整的 markdown 财报解读报告，结构建议：
   ## 业绩概览（营收/净利/同比表现点评）
   ## 盈利质量（ROE/毛利率/费用结构分析）
   ## 财务健康度（负债率/流动性/现金流代理指标）
   ## 趋势研判（多期对比：改善还是恶化，拐点信号）
   ## 下期展望（下一报告期业绩预测与关注信号）

报告使用中文，条理清晰，总长度控制在 800 字以内。不构成投资建议的免责声明无需输出。
"""


class FinancialService:

    # ------------------------------------------------------------------
    # 分析策略配置（单行，空则使用内置默认策略）
    # ------------------------------------------------------------------
    @staticmethod
    async def get_config(db: AsyncSession) -> BusinessFinancialConfig | None:
        result = await db.execute(
            select(BusinessFinancialConfig)
            .where(BusinessFinancialConfig.deleted_at.is_(None))
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def update_config(
        db: AsyncSession, prompt_template: str | None,
    ) -> BusinessFinancialConfig:
        """保存分析策略（upsert：已有记录则更新，否则新建）"""
        config = await FinancialService.get_config(db)
        if config is None:
            config = BusinessFinancialConfig(prompt_template=prompt_template)
            db.add(config)
            logger.info("新建财报解读分析策略配置")
        else:
            config.prompt_template = prompt_template
            config.updated_at = timezone.now()
        await db.commit()
        return config

    # ------------------------------------------------------------------
    # 财报抓取
    # ------------------------------------------------------------------
    @staticmethod
    async def sync_reports(db: AsyncSession, stock_code: str) -> int:
        """抓取个股近几期财报指标并 upsert，返回入库条数"""
        items = await financial_fetcher.fetch_financial_reports(stock_code)
        now = timezone.now()
        saved = 0
        for it in items:
            result = await db.execute(
                select(BusinessFinancialReport.id).where(
                    BusinessFinancialReport.stock_code == it["stock_code"],
                    BusinessFinancialReport.report_period == it["report_period"],
                    BusinessFinancialReport.deleted_at.is_(None),
                ).limit(1)
            )
            existing_id = result.scalar_one_or_none()
            values = {
                "stock_name": it["stock_name"],
                "metrics": it["metrics"],
                "fetched_at": now,
            }
            if existing_id is not None:
                await db.execute(
                    BusinessFinancialReport.__table__.update()
                    .where(BusinessFinancialReport.id == existing_id)
                    .values(**values)
                )
            else:
                db.add(BusinessFinancialReport(
                    stock_code=it["stock_code"],
                    report_period=it["report_period"],
                    **values,
                ))
            saved += 1
        await db.commit()
        return saved

    @staticmethod
    async def get_reports(
        db: AsyncSession, stock_code: str, limit: int = 8,
    ) -> list[BusinessFinancialReport]:
        """取个股近几期财报（report_period 倒序）"""
        from modules.financial.services.financial_fetcher import _norm_code

        code = _norm_code(stock_code)
        result = await db.execute(
            select(BusinessFinancialReport)
            .where(
                BusinessFinancialReport.stock_code == code,
                BusinessFinancialReport.deleted_at.is_(None),
            )
            .order_by(BusinessFinancialReport.report_period.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # 股票元信息（名称/行业）
    # ------------------------------------------------------------------
    @staticmethod
    async def _fetch_stock_meta_em(code: str) -> tuple[str | None, str | None]:
        """东财 push2 个股信息兜底：一次请求同时取名称与所属行业（主源限流时走延时源）"""
        import httpx

        market = "1" if code.startswith(("6", "9", "5")) else "0"
        for host in ("push2.eastmoney.com", "push2delay.eastmoney.com"):
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.get(
                        f"https://{host}/api/qt/stock/get",
                        params={"secid": f"{market}.{code}", "fields": "f57,f58,f127"},
                        headers={"Referer": "https://quote.eastmoney.com/"},
                    )
                data = (resp.json() or {}).get("data") or {}
                name = str(data.get("f58") or "").strip() or None
                industry = str(data.get("f127") or "").strip() or None
                if name or industry:
                    return name, industry
            except Exception:  # noqa: BLE001
                logger.warning("东财 push2 取个股信息失败: %s host=%s", code, host, exc_info=True)
        return None, None

    @staticmethod
    async def _resolve_stock_meta(
        db: AsyncSession, code: str,
    ) -> tuple[str | None, str | None]:
        """解析股票名称与所属行业：研报表最新记录优先；
        名称走新浪行情兜底，行业走东财个股信息兜底（均失败返回 None）"""
        from database.models.business.research import BusinessResearchReport

        result = await db.execute(
            select(BusinessResearchReport.stock_name)
            .where(
                BusinessResearchReport.stock_code == code,
                BusinessResearchReport.stock_name.is_not(None),
                BusinessResearchReport.deleted_at.is_(None),
            )
            .order_by(
                BusinessResearchReport.published_date.desc().nullslast(),
                BusinessResearchReport.fetched_at.desc(),
            )
            .limit(1)
        )
        name = result.scalar_one_or_none()

        result = await db.execute(
            select(BusinessResearchReport.industry)
            .where(
                BusinessResearchReport.stock_code == code,
                BusinessResearchReport.industry.is_not(None),
                BusinessResearchReport.deleted_at.is_(None),
            )
            .order_by(
                BusinessResearchReport.published_date.desc().nullslast(),
                BusinessResearchReport.fetched_at.desc(),
            )
            .limit(1)
        )
        industry = result.scalar_one_or_none()

        from modules.financial.services.financial_fetcher import _fetch_stock_name
        if not name or not industry:
            em_name, em_industry = await FinancialService._fetch_stock_meta_em(code)
            name = name or em_name
            industry = industry or em_industry
        if not name:
            name = await _fetch_stock_name(code)  # 新浪行情最终兜底
        return name, industry

    @staticmethod
    async def get_latest_research_briefs(
        db: AsyncSession, codes: list[str],
    ) -> dict[str, dict]:
        """按代码批量取每股最新一条研报摘要（评级/机构/盈利预测），供解读列表对照展示"""
        if not codes:
            return {}
        from database.models.business.research import BusinessResearchReport

        result = await db.execute(
            select(
                BusinessResearchReport.stock_code,
                BusinessResearchReport.org_name,
                BusinessResearchReport.rating,
                BusinessResearchReport.published_date,
                BusinessResearchReport.forecast,
            )
            .where(
                BusinessResearchReport.stock_code.in_(codes),
                BusinessResearchReport.deleted_at.is_(None),
            )
            .order_by(
                BusinessResearchReport.stock_code,
                BusinessResearchReport.published_date.desc().nullslast(),
                BusinessResearchReport.fetched_at.desc(),
            )
        )
        briefs: dict[str, dict] = {}
        for code, org_name, rating, published_date, forecast in result.all():
            if code in briefs:
                continue  # 每股只取排序后的第一条
            briefs[code] = {
                "org_name": org_name,
                "rating": rating,
                "published_date": published_date.isoformat() if published_date else None,
                "forecast": forecast,
            }
        return briefs

    # ------------------------------------------------------------------
    # AI 解读（异步提交模式，与 AnalysisExecutor 一致）
    # ------------------------------------------------------------------
    @staticmethod
    async def submit_interpretation(
        db: AsyncSession, stock_code: str, trigger_type: str = "manual",
        auto_fetch: bool = True,
    ) -> int:
        """提交一次财报 AI 解读：抓取/读取财报 → 创建 running 记录并立即返回，
        LLM 解读在后台 asyncio 任务中进行。

        并发守卫：同股票已有 running 解读记录时抛 FINANCIAL_ALREADY_RUNNING。
        """
        from modules.financial.services.financial_fetcher import _norm_code

        code = _norm_code(stock_code)
        if not code:
            raise CustomError(
                error=CustomErrorCode.FINANCIAL_REPORT_FETCH_FAILED,
                msg="股票代码非法",
            )

        # 确保库内有该股最新财报（手动触发时可自动抓取补齐）
        reports = await FinancialService.get_reports(db, code)
        if auto_fetch and not reports:
            await FinancialService.sync_reports(db, code)
            reports = await FinancialService.get_reports(db, code)
        if not reports:
            raise CustomError(
                error=CustomErrorCode.FINANCIAL_REPORT_NOT_FOUND,
                msg=f"未获取到股票 {code} 的财报数据",
            )
        latest = reports[0]

        dup = await db.execute(
            select(BusinessFinancialInterpretation.id).where(
                BusinessFinancialInterpretation.stock_code == code,
                BusinessFinancialInterpretation.status == "running",
                BusinessFinancialInterpretation.deleted_at.is_(None),
            ).limit(1)
        )
        if dup.scalar_one_or_none() is not None:
            raise CustomError(
                error=CustomErrorCode.FINANCIAL_ALREADY_RUNNING,
                msg=f"股票 {code} 的财报解读正在进行中，请稍后再试",
            )

        now = timezone.now()
        stock_name, industry = await FinancialService._resolve_stock_meta(db, code)
        if not stock_name:
            stock_name = latest.stock_name
        interp = BusinessFinancialInterpretation(
            stock_code=code,
            stock_name=stock_name,
            industry=industry,
            report_period=latest.report_period,
            run_date=now.strftime("%Y-%m-%d"),
            trigger_type=trigger_type,
            status="running",
        )
        db.add(interp)
        await db.commit()

        task = asyncio.create_task(
            FinancialService._execute_interpretation(interp.id, code)
        )
        _BACKGROUND_TASKS.add(task)
        task.add_done_callback(_BACKGROUND_TASKS.discard)
        logger.info(
            "已提交 AI 财报解读: code=%s interpretation_id=%s trigger=%s",
            code, interp.id, trigger_type,
        )
        return interp.id

    @staticmethod
    async def _execute_interpretation(interpretation_id: int, stock_code: str) -> None:
        """后台解读入口：独立 session + 整体超时兜底，任何异常回写失败状态"""
        from database.db_manager import get_session

        async for db in get_session():
            try:
                await asyncio.wait_for(
                    FinancialService._interpret(db, interpretation_id, stock_code),
                    timeout=INTERPRET_TIMEOUT,
                )
            except Exception as exc:  # noqa: BLE001  含 TimeoutError
                if isinstance(exc, asyncio.TimeoutError):
                    err_text = f"财报解读执行超时（超过 {INTERPRET_TIMEOUT} 秒）"
                else:
                    err_text = str(getattr(exc, "msg", None) or exc)
                logger.warning("AI 后台财报解读失败: id=%s error=%s", interpretation_id, err_text)
                try:
                    await db.rollback()
                    await db.execute(
                        update(BusinessFinancialInterpretation)
                        .where(BusinessFinancialInterpretation.id == interpretation_id)
                        .values(status="failed", error_msg=err_text[:1000])
                        .execution_options(synchronize_session=False)
                    )
                    await db.commit()
                except Exception:  # noqa: BLE001
                    logger.exception("回写失败解读记录异常: id=%s", interpretation_id)

    @staticmethod
    async def _interpret(db: AsyncSession, interpretation_id: int, stock_code: str) -> None:
        """解读主体：读取财报指标 → LLM 生成解读 → 解析 JSON 摘要 → 回写成功"""
        from modules.analysis.services.analysis_executor import _extract_json_object, _run_llm

        result = await db.execute(
            select(BusinessFinancialInterpretation).where(
                BusinessFinancialInterpretation.id == interpretation_id,
                BusinessFinancialInterpretation.deleted_at.is_(None),
            )
        )
        interp = result.scalar_one_or_none()
        if interp is None:
            logger.warning("财报解读记录不存在，放弃解读: id=%s", interpretation_id)
            return

        reports = await FinancialService.get_reports(db, stock_code, INTERPRET_PERIODS)
        if not reports:
            interp.status = "failed"
            interp.error_msg = f"股票 {stock_code} 无财报数据"
            await db.commit()
            return

        import json
        lines = [f"当前时间：{timezone.now().strftime('%Y-%m-%d %H:%M')}"]
        if interp.industry:
            lines.append(f"所属行业：{interp.industry}")
        for r in reports:
            lines.append(
                f"报告期 {r.report_period}（{r.stock_name or r.stock_code}）：\n"
                + json.dumps(r.metrics or {}, ensure_ascii=False)
            )
        lines.append("请基于以上真实财务指标输出 JSON 摘要与 markdown 财报解读报告（最新报告期在最前）。")
        strategy = await FinancialService.get_config(db)
        if strategy and strategy.prompt_template and strategy.prompt_template.strip():
            lines.append(
                f"分析策略要求（用户定制，生成时必须遵循）：\n{strategy.prompt_template.strip()}"
            )
        user_prompt = "\n\n".join(lines)

        raw_text = await _run_llm(
            db, "financial", _FINANCIAL_SYSTEM_PROMPT, user_prompt,
        )
        interp.ai_raw_response = raw_text[:20000]
        parsed = _extract_json_object(raw_text)
        interp.parsed_result = parsed
        interp.status = "success"
        await db.commit()
        logger.info(
            "AI 财报解读完成: code=%s id=%s parsed=%s",
            stock_code, interpretation_id, parsed is not None,
        )

    # ------------------------------------------------------------------
    # 持仓自动解读（定时任务用）
    # ------------------------------------------------------------------
    @staticmethod
    async def auto_interpret_holding_codes(db: AsyncSession) -> dict:
        """收集持仓标的，对最新报告期尚无成功解读的个股提交解读（同日去重）"""
        from datetime import timedelta

        from database.models.business.strategy import (
            BusinessStrategyPosition, BusinessStrategySignal,
        )

        result = await db.execute(
            select(BusinessStrategyPosition.stock_code)
            .where(
                BusinessStrategyPosition.status == "holding",
                BusinessStrategyPosition.deleted_at.is_(None),
            )
            .distinct()
        )
        codes = {row[0] for row in result.all() if row[0]}
        result = await db.execute(
            select(BusinessStrategySignal.stock_code)
            .where(
                BusinessStrategySignal.deleted_at.is_(None),
                BusinessStrategySignal.created_at >= timezone.now() - timedelta(days=30),
            )
            .distinct()
        )
        codes |= {row[0] for row in result.all() if row[0]}

        total = {"codes": len(codes), "submitted": 0, "skipped": 0, "rejected": 0, "no_report": 0}
        for code in sorted(codes):
            # 库内无财报先补抓一次（财报季新披露的在此进入）
            reports = await FinancialService.get_reports(db, code, limit=1)
            if not reports:
                try:
                    await FinancialService.sync_reports(db, code)
                except Exception:  # noqa: BLE001
                    logger.warning("持仓财报补抓失败: %s", code, exc_info=True)
                reports = await FinancialService.get_reports(db, code, limit=1)
            if not reports:
                total["no_report"] += 1
                continue
            latest_period = reports[0].report_period
            done = await db.execute(
                select(BusinessFinancialInterpretation.id).where(
                    BusinessFinancialInterpretation.stock_code == code,
                    BusinessFinancialInterpretation.status == "success",
                    BusinessFinancialInterpretation.report_period == latest_period,
                    BusinessFinancialInterpretation.deleted_at.is_(None),
                ).limit(1)
            )
            if done.scalar_one_or_none() is not None:
                total["skipped"] += 1
                continue
            try:
                await FinancialService.submit_interpretation(
                    db, code, trigger_type="schedule",
                )
                total["submitted"] += 1
            except CustomError:
                total["rejected"] += 1
        return total
