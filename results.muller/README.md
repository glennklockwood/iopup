# Muller Testing

## Job Log

Jobid | Primary Workload  | Secondary Workload | PPN(1) | ppn(2) | Clients | Step
------|-------------------|--------------------|--------|--------|---------|------
43239 | write bw (1 MiB)  | write iops         |     16 |     16 |       8 |    2
43449 | write bw (1 MiB)  | write iops         |     32 |     32 |      16 |    2
43470 | write bw (1 MiB)  | write iops         |     64 |     64 |      16 |    2
43470 | write bw (32 MiB) | write iops         |     64 |     64 |      16 |    2
43472 | write bw (32 MiB) | write iops         |     32 |     64 |      16 |    2
43474 | write bw (32 MiB) | write iops         |     32 |    128 |      16 |    2
43477 | write bw (64 MiB) | write iops         |     16 |     64 |      16 |    2
43482 | write bw (64 MiB) | write iops         |     16 |     64 |      16 |    2
43484 | write bw (64 MiB) | write iops         |     16 |     64 |      16 |    2

### 43477

According to the HPE Lustre Benchmarking Best Practices for ClusterStor E1000
technical notes,

* for direct I/O, the ideal write size is 64 MiB
* for buffered I/O, 1 MiB writes are sufficient

Job 43477 reflects the ideal primary workload.

### 43472

This is a re-run of 43477 using iopup that more flexibly supports running
primary and/or secondary workloads in isolation before launching the noisy
one.

### 43477, 43482, 43484

These are the same runs from the file system's perspective but were testing
new features in iopup.
