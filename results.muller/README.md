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

According to the HPE Lustre Benchmarking Best Practices for ClusterStor E1000
technical notes,

* for direct I/O, the ideal write size is 64 MiB
* for buffered I/O, 1 MiB writes are sufficient

Job 43477 reflects the ideal primary workload.
