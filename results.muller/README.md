# Muller Testing

## Job Log

Jobid | Primary Workload  | Secondary Workload | PPN(1) | ppn(2) | Clients | Step
------|-------------------|--------------------|--------|--------|---------|------
43239 | write bw (1 MiB)  | write iops         |     16 |     16 |       8 |    2
43449 | write bw (1 MiB)  | write iops         |     32 |     32 |      16 |    2
43470 | write bw (1 MiB)  | write iops         |     64 |     64 |      16 |    2
43470 | write bw (32 MiB) | write iops         |     64 |     64 |      16 |    2
43472 | write bw (32 MiB) | write iops         |     32 |     64 |      16 |    2
