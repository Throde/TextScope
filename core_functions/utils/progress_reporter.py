# progress_reporter.py
from typing import Callable, Optional, Iterable, Iterator, TypeVar, Generic

ProgressFn = Callable[[int, Optional[str]], None]  # (percent, msg)
T = TypeVar("T") # 声明一个可变的“类型参数”

class ProgressReporter(Generic[T]): # 让类支持泛型（参数化类型）
    """
    进度汇报工具：负责把本层 0..100 的进度映射到父层指定的 [start..end] 区间，并向上传递。
    - 支持多层 child() 下传: parent.subrange(10, 40).subrange(0, 50)...
    - report(): 上报本层进度(0..100)与可选信息；
    - wrap(iterable, total=None, start=0, end=100): tqdm 风格包装可迭代对象，并按自身区间更新进度
    """
    __slots__ = ("_sink", "_lo", "_hi", "_span", "_last")

    def __init__(self, sink: ProgressFn, start: int = 0, end: int = 100):
        if end < start:
            raise ValueError("end must be >= start")
        
        # 裁剪父区间到 0..100
        lo = max(0, min(100, int(start)))
        hi = max(0, min(100, int(end)))
        self._lo = lo
        self._hi = hi
        self._span = max(0, hi - lo)
        self._sink = sink
        self._last = -1  # 保证单调不减

    # ---------- 基本上报能力 ----------
    def report(self, p: int, msg: Optional[str] = None) -> None:
        """上报当前层 0..100 的进度与可选消息。"""
        p = max(0, min(100, int(p)))
        mapped = self._lo + (p * self._span) // 100 if self._span > 0 else self._lo
        mapped = max(0, min(100, mapped))

        # 单调不减。若 mapped 未前进，但传了信息，也允许把信息送上去。
        if mapped < self._last:
            mapped = self._last

        if mapped > self._last or (msg and msg != ""):
            self._sink(mapped, msg or "")
            self._last = mapped
    
    # ---------- 多层下传 ----------
    def child(self, start: int, end: int) -> "ProgressReporter":
        """
        在“当前层”的 0..100 之内，再切一段 [start..end] 子区间，返回一个新的 reporter。
        子区间会被线性映射回父区间的绝对位置并继续向上透传。
        """
        if end < start:
            raise ValueError("child: end must be >= start")

        # 先把子层的 [start, end] 映射到“父层绝对 0..100”
        start = max(0, min(100, int(start)))
        end   = max(0, min(100, int(end)))

        # 子层绝对位置（仍在 0..100 空间）
        if self._span > 0:
            abs_lo = self._lo + (start * self._span) // 100
            abs_hi = self._lo + (end   * self._span) // 100
        else:
            abs_lo = self._lo
            abs_hi = self._lo

        return ProgressReporter(self._sink, abs_lo, abs_hi)

    # ---------- tqdm 风格 wrapper ----------
    def wrap(self, iterable: Iterable[T], *, total: Optional[int] = None,
             start: int = 0, end: int = 100, message_each: Optional[str] = None
             ) -> Iterator[T]:
        """
        包裹一个可迭代对象，在当前 reporter 的子区间 [start, end] 内推进进度。
        - total: 总步数，未给时尝试 len(iterable)，再不行则仅在开始(0%)和结束(100%)各上报一次；
        - message_each: 每步的固定状态文本（可选）。
        用法：
            for item in reporter.wrap(items, total=len(items), start=20, end=60, message_each="处理中…"):
                ...
        """
        sub = self.child(start, end)
        # 估计总长度
        if total is None:
            try:
                total = len(iterable)  # type: ignore
            except Exception:
                total = None

        if total is None or total <= 0:
            sub.report(0, message_each)
            for x in iterable:
                yield x
            sub.report(100, message_each)
            return

        # 有已知 total：逐步推进
        count = 0
        sub.report(0, message_each)
        for x in iterable:
            yield x
            count += 1
            # 保证 0..100 的线性推进
            pct = (count * 100) // total
            if pct > 100:
                pct = 100
            sub.report(pct, message_each)
        # 收尾
        sub.report(100, message_each)
