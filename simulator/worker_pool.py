"""Worker pool that processes simulated requests using a thread pool.

The baseline implementation has NO queue bound, NO timeout, and NO load
shedding.  This is intentional -- the saturated workload will demonstrate
unbounded queue growth.  Students improve this in their homework.
"""

from __future__ import annotations

import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from simulator.metrics import MetricsCollector


class WorkerPool:
    """Fixed-size thread pool that simulates request processing."""

    def __init__(self, workers: int, service_time_ms: float) -> None:
        self.workers = workers
        self.service_time_s = service_time_ms / 1000.0

    def _handle_request(self, request_id: int, submit_time: float | None = None) -> tuple[float, float]:
        """Simulate processing a single request.

        Returns a tuple of (queue_time_ms, service_time_ms).
        If submit_time is None, queue_time will be 0.0 (for backward compatibility).
        Adds +/-20 % jitter to the base service time so that latency
        distributions are realistic (not all identical).
        """
        # Calculate queue wait time
        pickup_time = time.monotonic()
        if submit_time is not None:
            queue_time_ms = (pickup_time - submit_time) * 1000.0
        else:
            queue_time_ms = 0.0

        # Simulate service time
        jitter = random.uniform(0.8, 1.2)
        sleep_time = self.service_time_s * jitter
        time.sleep(sleep_time)
        service_time_ms = (time.monotonic() - pickup_time) * 1000.0

        return queue_time_ms, service_time_ms

    def run(
        self,
        request_ids: list[int],
        collector: MetricsCollector,
    ) -> None:
        """Submit all requests to the pool and record latencies.

        Requests are submitted as fast as possible (no arrival-rate
        shaping here).  Queue depth is unbounded in the baseline.
        """
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            submit_time = time.monotonic()
            futures = {
                pool.submit(self._handle_request, rid, submit_time): rid
                for rid in request_ids
            }
            for future in as_completed(futures):
                queue_time_ms, service_time_ms = future.result()
                collector.record_times(queue_time_ms, service_time_ms)

    # for my env using of this workload generator makes opposite effect and prevent the queue from overloading,
    # so I don't use it for now
    def run_with_arrival_rate(
        self,
        request_ids: list[int],
        collector: MetricsCollector,
        inter_arrival_ms: float,
    ) -> None:
        """Submit requests at a controlled arrival rate.

        This models a saturated workload where requests keep arriving
        faster than the pool can drain them, causing queue buildup.
        """
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            futures: dict = {}
            for rid in request_ids:
                submit_time = time.monotonic()
                futures[pool.submit(self._handle_request, rid, submit_time)] = rid
                time.sleep(inter_arrival_ms / 1000.0)

            for future in as_completed(futures):
                queue_time_ms, service_time_ms = future.result()
                collector.record_times(queue_time_ms, service_time_ms)
