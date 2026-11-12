"""解の更新に依存せず、計算の中止要求を監視する処理。"""
import logging
from collections.abc import Callable
from threading import Event


# 計算が終わるまで中止要求を確認し、要求を受けたら停止処理を呼ぶ。
def watch_cancellation(stop_search: Callable[[], None], finished: Event, should_stop: Callable[[], bool]) -> None:
    while not finished.wait(0.2):
        try:
            if should_stop():
                stop_search()
        except Exception:
            # 一時的な読込失敗を記録し、次の監視で中止確認を再試行する。
            logging.getLogger(__name__).exception("計算の中止要求を確認できませんでした。再試行します。")
