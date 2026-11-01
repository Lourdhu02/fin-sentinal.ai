import math
import threading
import time
import tracemalloc


def percentile(values, fraction):
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(fraction * len(ordered)) - 1)]


class Resources:
    """Sample this process's RSS, not GPU memory or child processes."""

    def __init__(self, trace_python_heap=False):
        self.trace_python_heap = trace_python_heap

    def __enter__(self):
        self.started = time.perf_counter()
        self.cpu_started = time.process_time()
        self.stop = threading.Event()
        self.peak_rss = None
        self.own_tracing = self.trace_python_heap and not tracemalloc.is_tracing()
        if self.own_tracing:
            tracemalloc.start()
        try:
            import psutil
            self.process = psutil.Process()
        except ImportError:
            self.process = None
        self.sample()
        self.thread = threading.Thread(target=self.poll, daemon=True)
        self.thread.start()
        return self

    def sample(self):
        if self.process is not None:
            try:
                rss = self.process.memory_info().rss
                self.peak_rss = max(self.peak_rss or 0, rss)
            except OSError:
                pass

    def poll(self):
        while not self.stop.wait(0.05):
            self.sample()

    def __exit__(self, *args):
        self.stop.set()
        self.thread.join(timeout=1)
        self.sample()
        heap_peak = tracemalloc.get_traced_memory()[1] if self.own_tracing else None
        self.result = {"wall_seconds": time.perf_counter() - self.started,
                       "process_cpu_seconds": time.process_time() - self.cpu_started,
                       "sampled_peak_rss_bytes": self.peak_rss,
                       "rss_sample_interval_ms": 50,
                       "python_heap_peak_bytes": heap_peak if self.own_tracing else None,
                       "scope": "this process only; RSS is sampled, GPU peak is not measured",
                       "instrumentation": "periodic RSS sampling" + (" plus tracemalloc" if self.own_tracing else ""),
                       "python_heap_tracing": self.own_tracing}
        if self.own_tracing:
            tracemalloc.stop()
