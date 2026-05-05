## Environment
 - Python 3.14
 - Apple M1 Pro, 8 cores, 32GB RAM
 - OS: macOS Sequoia, Version 15.3.1 (24D70)
 - no other load

## Initial Benchmark Results (original configuration)
**Config**: service_time=10ms, workers=4, requests=500, saturated_multiplier=3

| Condition  | Workers | Requests | Rejected | Mean(ms)  | p95(ms)  | Throughput  | Duration  |
|---|---------|----------|----------|---|---|---|---|
| Serial  | 1       | 500      | 0        | 12.17  | 14.79  | 81.22 r/s  | 6.156 s  |
| Parallel  | 4       | 500      | 0        | 11.87  |14.82   | 334.11 r/s  | 1.497 s  |
| Saturated  | 4       | 1500     | 0        | 11.92  |14.52   |333.73 r/s   | 4.495 s  |

 - Neither mean nor p95 latency is decreased
 - Throughput increased almost linearly
 - Duration increased linearly
 - L = λ × W = ~4, calculated length of the queue corresponds to the number of workers
 - No saturation effect

## Benchmark modification to simulate saturation
It was discovered experimentally that the configuration and workload needed to be changed:
 - much more workers required
 - number of total requests must be increased
 - saturation multiplier must be increased significantly
 - _runner.py_ should always prefer `pool.run()` to `pool.run_with_arrival_rate()` for the workload generation (`pool.run_with_arrival_rate()` sends queries to the pool too slowly and the queue is drained before it's loaded so it's easier to simulate saturation when all queries are sent at once) 
Then we can simulate saturation.

## Initial Benchmark Results (real saturation configuration)
Config: service_time=10ms, workers=1024, requests=2500, saturated_multiplier=10

| Condition   | Workers | Requests | Rejected | Mean(ms)   | p95(ms)   | Throughput   | Duration  | L   |
|---|---------|----------|----------|---|---|---|---|-----|
| Serial   | 1       | 2500     | 0        | 12.05   | 14.63   | 82.31 r/s  | 30.373 s  | -   |
| Parallel  | 1024    | 2500     | 0        | 12.07   | 14.62  | 24105.62 r/s  | 0.104 s  | 291 |
| Saturated   | 1024    | 2500     | 0        | 70.40   | 420.56  | 11530.56 r/s   | 2.168 s  | 807 |

 - latency is degrading
 - p95 latency is degrading significantly
 - throughput is degrading
 - calculated length of the queue is increasing

## Proposal for optimization
- decrease number of workers to find the concurrency level at which throughput peaks without p95 latency exceeding 2× the serial baseline mean
