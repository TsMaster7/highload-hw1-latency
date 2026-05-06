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
| Saturated   | 1024    | 25000    | 0        | 70.40   | 420.56  | 11530.56 r/s   | 2.168 s  | 807 |

 - latency is degrading
 - p95 latency is degrading significantly
 - throughput is degrading
 - calculated length of the queue is increasing
 - non-linear duration scaling (10 times more requests -> 20 times longer the execution time)

## Proposal for optimization
- decrease number of workers to find the concurrency level at which throughput peaks without p95 latency exceeding 2× the serial baseline mean

## Optimization results
As a result of experiments it was discovered that the optimal number of workers is 256.
Further reduction of workers pool can give us a bit better p95 latency, but it decreases throughput. 

**Optimized configuration:** service_time=10ms, workers=256, requests=2500, saturated_multiplier=10

**Benchmark results for the optimized configuration:**

| Condition  | Workers | Requests | Rejected | Mean(ms)   | p95(ms)   |Throughput   |Duration   |
|---|---------|----------|----------|---|---|---|---|
| Serial   | 1       | 2500     | 0        | 11.93  | 14.64   | 83.09 r/s   | 30.088 s  |
| Parallel   | 256     | 2500     | 0        | 12.18  | 16.66   | 17393.01 r/s  | 0.144 s  |
| Saturated   | 256     | 25000    | 0        | 12.20   | 14.82  | 20463.10 r/s  | 1.222 s  |

**Comparative table:**

(first 2 rows actually represent the same configuration)

| Condition   | Version  | Mean Latency (ms)  | p95 Latency (ms)  | Throughput (req/s)  | Workers |
|---|---|---|---|---|---------|
| Serial  | Baseline  | 12.05  | 14.63  | 82.31 r/s  | 1       |
| Serial  |Improved   | 11.93  |14.64   | 83.09 r/s  | 1       |
| Parallel  | Baseline  |12.07   | 14.62  | 24105.62 r/s  | 1024    |
| Parallel  | Improved  | 12.18  |  16.66 | 17393.01 r/s  | 256     |
| Saturated  |Baseline   |70.40   | 420.56  | 11530.56 r/s  | 1024    |
| Saturated  | Improved  | 12.20  | 14.82  | 20463.10 r/s  | 256     |

- latency got back to normal values
- no saturation effect seen anymore
- throughput slightly decreased for the 2500 requests workload, but significantly increased for the 25000 requests workload

## Experimental analysis and criticism
**The main conclusion:** Too Many Workers = Performance Degradation

We solved it reducing the number of workers.
But:
- Enormous extension of the workers pool creates artificial latency
- It looks like saturation but is actually over-provisioning overhead
- Currently, the benchmark only shows contention-based degradation (1024 workers), not queue-depth-based degradation (which should
  also happen with fewer workers + massive load).
- Now we measure only request handling time (_WorkerPool->_handle_request_ start-to-finish time), not the time which request waits in the queue
- We need to fix the latency measurement to include queue wait time.
- Then we can simulate and tackle queue-depth-based degradation

## Extended Metrics: Queue Wait Time vs Service Time

After implementing queue wait time measurement, we can now see the real source of latency under saturation.

**Configuration:** service_time=10ms, workers=24, requests=1000, saturated_multiplier=10

### Benchmark Results with Queue Breakdown

| Condition | Workers | Requests | Rejected | Total Mean(ms) | Total p95(ms) | Throughput | Duration |
|-----------|---------|----------|----------|----------------|---------------|------------|----------|
| Serial | 1 | 1000 | 0 | 6,120.69 | 11,620.33 | 81.79 r/s | 12.226 s |
| Parallel | 24 | 1000 | 0 | 249.15 | 467.28 | 2,030.33 r/s | 0.493 s |
| Saturated | 24 | 10000 | 0 | 2,468.96 | 4,694.03 | 2,022.93 r/s | 4.943 s |

### Latency Breakdown: Queue Wait + Service Time

| Condition | Queue Mean | Queue p95 | Service Mean | Service p95 | Total Mean | Total p95 | Queue % |
|-----------|------------|-----------|--------------|-------------|------------|-----------|---------|
| Serial | 6,108.49ms | 11,606.35ms | 12.20ms | 14.79ms | 6,120.69ms | 11,620.33ms | **99.8%** |
| Parallel | 237.50ms | 455.73ms | 11.65ms | 14.24ms | 249.15ms | 467.28ms | **95.3%** |
| Saturated | 2,457.13ms | 4,682.59ms | 11.83ms | 14.54ms | 2,468.96ms | 4,694.03ms | **99.5%** |

### Key Findings

**Comparative Summary Table (Mean / p95):**

| Condition | Total Latency | Queue Latency | Service Time | Throughput | Queue % |
|-----------|---------------|---------------|--------------|------------|---------|
| **Serial** | 6,120ms / 11,620ms | 6,108ms / 11,606ms | 12ms / 15ms | 82 r/s | 99.8% |
| **Parallel** | 249ms / 467ms | 238ms / 456ms | 12ms / 14ms | 2,030 r/s | 95.3% |
| **Saturated** | 2,469ms / 4,694ms | 2,457ms / 4,683ms | 12ms / 15ms | 2,023 r/s | **99.5%** |

**1. Queue Wait Dominates Under Saturation**
- In the saturated condition, **99.5% of latency is queue wait time**
- Service time remains stable at ~12ms across all conditions
- p95 queue wait: **4.68 seconds** - requests wait almost 5 seconds in queue!

**2. Real Saturation Now Visible**
- Serial: Each request waits for all previous requests (6.1s average)
- Parallel: 238ms average queue wait with 1,000 requests
- Saturated: 2.46s average queue wait with 10,000 requests
- Queue wait time increases **10×** from parallel to saturated mode

**3. Service Time Stability**
- Service time consistent at 11-12ms mean, 14-15ms p95
- No degradation under load - workers are efficient
- Bottleneck is clearly the queue, not processing capacity

**4. Throughput Analysis**
- Theoretical capacity: 24 workers / 0.01s = 2,400 r/s
- Actual saturated throughput: 2,023 r/s (84% of theoretical)
- Parallel vs Saturated throughput nearly identical (2,030 vs 2,023 r/s)
- System is operating at capacity, queue continues to grow

### Saturation Profile

The system exhibits classic queue saturation behavior:
- **Queue length grows unbounded** - 10,000 requests submitted instantly
- **Wait time dominates** - 208:1 ratio of queue time to service time (2,457ms / 11.83ms)
- **Throughput plateaus** - cannot exceed ~2,000 r/s regardless of load
- **Tail latency explodes** - p95 of 4.69 seconds vs 467ms in parallel mode

### Optimization Target

Current baseline shows clear opportunity for improvement:
- **Target metric:** Reduce p95 latency from **4,694ms → <500ms**
- **Strategy:** Bounded queue with load shedding
  - Reject excess requests immediately (HTTP 429)
  - Prevent 4+ second wait times
  - Fast failure is better than slow failure
- **Expected outcome:**
  - Successful requests: p95 < 500ms
  - Rejected requests: 50-80% under extreme load
  - Overall system stability maintained
