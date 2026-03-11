from typing import Callable, Iterable, Any
import traceback


def run_followings(all_followings: Iterable[Any], build_following: Callable[[Any], Any], run_one: Callable[[Any], None], logger, finished_message: str = "本次任务结束\n\n"):
    """
    统一抓取入口：
    - build_following: 将数据库行转换为 Following/Profile 对象
    - run_one: 执行单账号抓取和处理
    - logger: 统一异常与结束日志输出
    """
    try:
        for raw in all_followings:
            run_one(build_following(raw))
        logger.info(finished_message)
    except Exception:
        logger.info(traceback.format_exc())
