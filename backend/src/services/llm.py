import asyncio
import logging
import os
import time

from openai import APITimeoutError, AsyncOpenAI

logger = logging.getLogger("deep-research.llm")


def setting(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip().strip("'").strip('"')


async def chat(messages: list[dict[str, str]], phase: str) -> str:
    base_url = setting("LLM_BASE_URL").rstrip("/")
    timeout = float(setting("LLM_PLAN_TIMEOUT" if phase == "planning" else "LLM_TASK_TIMEOUT" if phase == "summarizing" else "LLM_REPORT_TIMEOUT", setting("LLM_TIMEOUT", "120")))
    max_tokens = int(setting("LLM_PLAN_MAX_TOKENS" if phase == "planning" else "LLM_TASK_MAX_TOKENS" if phase == "summarizing" else "LLM_REPORT_MAX_TOKENS", setting("LLM_MAX_TOKENS", "2500")))
    retries = int(setting("UPSTREAM_RETRIES", "2"))
    logger.info("LLM started phase=%s model=%s url=%s timeout=%ss max_tokens=%s", phase, setting("LLM_MODEL_ID"), f"{base_url}/chat/completions", timeout, max_tokens)
    started = time.perf_counter()

    for attempt in range(retries + 1):
        client = AsyncOpenAI(api_key=setting("LLM_API_KEY"), base_url=base_url, timeout=timeout, max_retries=0)
        try:
            response = await asyncio.wait_for(client.chat.completions.create(model=setting("LLM_MODEL_ID"), messages=messages, temperature=float(setting("LLM_TEMPERATURE", "0.2")), max_tokens=max_tokens), timeout=timeout + 5)
            content = response.choices[0].message.content or ""
            logger.info("LLM completed phase=%s chars=%s elapsed=%.2fs attempt=%s", phase, len(content), time.perf_counter() - started, attempt + 1)
            return content
        except (APITimeoutError, TimeoutError, asyncio.TimeoutError) as exc:
            logger.warning("LLM timeout phase=%s attempt=%s/%s", phase, attempt + 1, retries + 1)
            if attempt >= retries:
                raise TimeoutError(f"LLM {phase} 阶段超时（单次 {timeout:g} 秒，重试 {retries} 次）") from exc
        except Exception as exc:
            logger.exception("LLM failed phase=%s error_type=%s error=%s", phase, type(exc).__name__, exc)
            raise
        finally:
            await client.close()
        await asyncio.sleep(min(2**attempt, 8))
    raise RuntimeError("LLM 未返回结果")
