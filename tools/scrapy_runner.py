from typing import Callable, Iterable, Any
import traceback


def run_followings(all_followings: Iterable[Any], build_following: Callable[[Any], Any], run_one: Callable[[Any], None], logger, finished_message: str = "本次任务结束\n\n"):
    """统一抓取入口：构建关注对象 -> 执行单个抓取 -> 统一异常处理与收尾日志。"""
    try:
        for raw in all_followings:
            run_one(build_following(raw))
        logger.info(finished_message)
    except Exception:
        logger.info(traceback.format_exc())
