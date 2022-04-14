#!/usr/bin/env python3

import os
import io
import time
import logging
import argparse
import datetime
import subprocess
import multiprocessing.pool

import yaml

MPIRUN_BIN = "srun"

def load_config(configfile):
    """Reads in all benchmark tools' configurations.

    Expects a config file of the format::

        mpirun: "srun"
        elbencho:
            binary: "/global/u2/g/glock/src/elbencho/bin.cgpu/elbencho"
            common_args: "--threads 1 --sync"
            access_args:
                write:  "--write"
                read:   "--read"
                clean:  "--delfiles"
            pattern_args:
                create: "--block 128m --size 1t"
                bw:     "--size 1t --block 1m"
                iops:   "--size 1t --block 4k --rand"

    where "mpirun" is a hard-coded variable and the remainder (like "elbencho")
    describe the command line arguments for each benchmark tool.

    Args:
        configfile (str): Path to yaml config file.
    """
    with open(configfile, "r") as config_handle:
        config = yaml.safe_load(config_handle)
    return config

class BenchmarkLauncher():
    def __init__(self, hosts, ppn, output_dir, timelimit=0, random_data=False, config=None, test=False, stdout=None, stderr=None, **kwargs):
        """Base class for a benchmark tool launcher.

        Args:
            hosts (list of str): List of nodes on which benchmark application
                should be launched in parallel
            ppn (int): Number of parallel threads or MPI processes to run on
                each node
            output_dir (list of str or str): Path to directory where benchmark
                should perform its I/O
            timelimit (int): Number of seconds benchmark should be allowed to
                run before terminating.  0 indicates no limit
            random_data (bool): Request benchmark tool write randomized
                (incompressible) data instead of a repeating pattern
            config (dict): Configuration parameters returned by load_config()
            test (bool): If true, do not actually run benchmarks but print what
                would be run
            stdout (file): File object where benchmark's stdout will be written
            stderr (file): File object where benchmark's stderr will be written
            kwargs: Additional parameters to pass to benchmark tool as
                command-line arguments
        """
        self._binary = None
        self._hosts = hosts
        self._ppn = ppn
        if isinstance(output_dir, list):
            self._output_dir = output_dir
        else:
            self._output_dir = [output_dir]
        self._timelimit = timelimit
        self._timelimit_args = []
        self._random_data = random_data
        self._random_data_args = []
        self._test = test
        self._kwargs = kwargs
        self._cmdline = []
        self._common_args = []
        self._access_args = {}
        self._pattern_args = {}
        self._access_pattern_args = {}
        self._prepend_cmdline = []
        self._config = config
        self._stdout = stdout
        self._stderr = stderr

        self._logger = logging.getLogger(__name__)

    def _init_args(self, key):
        """Copies this benchmark's CLI args out of the global config.

        This is not idempotent and should only be called once at the end of
        child classes' __init__() methods.  It overwrites the global config
        (stored in self._config) with the benchmark-specific config.

        Args:
            key (str): The name of the benchmark (and key of self._config) whose
                configs should be loaded.
        """
        self._binary = self._config[key]['binary']
        self._common_args = self._config[key]['common_args'].strip().split()
        self._access_args = self._config[key]['access_args'].copy()
        self._pattern_args = self._config[key]['pattern_args'].copy()
        self._access_pattern_args = self._config[key].get('access_pattern_args', {}).copy()
        self._random_data_args = self._config[key].get('random_data_args', "").strip().split()
        self._timelimit_args = self._config[key]['timelimit_args'].strip().split()

        for access in self._access_args:
            self._access_args[access] = self._access_args[access].strip().split()

        for pattern in self._pattern_args:
            self._pattern_args[pattern] = self._pattern_args[pattern].strip().split()

        for access in self._access_pattern_args.keys():
            for pattern in self._access_pattern_args.get(access, {}):
                self._access_pattern_args[access][pattern] = self._access_pattern_args[access][pattern].strip().split()

    def _add_hosts(self):
        """Adds enumeration of hosts to the CLI arguments"""
        if self._hosts is not None:
            raise NotImplementedError

    def _add_timelimit(self):
        """Adds timelimit argument to the CLI arguments"""
        if self._timelimit:
            self._cmdline += self._timelimit_args
            self._cmdline.append(str(self._timelimit))

    def _add_output_dir(self):
        """Adds the output directory argument to the CLI"""
        if self._output_dir:
            raise NotImplementedError

    def _add_random_data(self):
        """Adds the toggle for random data generation to the CLI"""
        if self._random_data:
            self._cmdline += self._random_data_args

    def _add_results_file(self):
        """Adds arguments to route benchmark results to the CLI"""
        return

    def _prep_cmdline(self, access, pattern):
        """Builds the command line arguments required to run the benchmark.

        Args:
            access (str): Desired access mode (e.g., read or write)
            pattern (str): Desired I/O pattern (e.g., bw or iops)
        """
        self._cmdline = []
        if self._prepend_cmdline:
            self._cmdline = self._prepend_cmdline.copy()
        self._cmdline.append(self._binary)
        self._add_hosts()
        self._add_timelimit()
        self._add_random_data()
        self._add_results_file()
        self._cmdline += self._common_args
        self._cmdline += self._access_args[access]
        self._cmdline += self._pattern_args[pattern]
        self._cmdline += self._access_pattern_args.get(access, {}).get(pattern, [])

        if self._kwargs:
            for key, val in self._kwargs.items():
                if isinstance(val, bool) and val:
                    self._cmdline += [f"--{key}"]
                else:
                    self._cmdline += [f"--{key}", str(val)]

        self._add_output_dir()

    def set_stdout(self, stdout):
        """Sets the stdout stream for the benchmark.

        Manipulating this outside of class instantiation allows teardown and
        preflight to also run the benchmark in a different form to, e.g.,
        initialize or delete files without polluting the stdout of the main
        benchmark run.
        """
        self._stdout = stdout

    def get_stdout(self):
        """Returns the stdout stream for the benchmark."""
        return self._stdout

    def set_stderr(self, stderr):
        """Sets the stderr stream for the benchmark.

        Manipulating this outside of class instantiation allows teardown and
        preflight to also run the benchmark in a different form to, e.g.,
        initialize or delete files without polluting the stderr of the main
        benchmark run.
        """
        self._stderr = stderr

    def get_stderr(self):
        """Returns the stderr stream for the benchmark."""
        return self._stderr

    def get_hosts(self):
        """Returns the list of hosts on which the benchmark should run."""
        return self._hosts

    def set_random_data(self, random_data):
        self._random_data = bool(random_data)
        return self._random_data

    def get_random_data(self):
        return self._random_data

    def preflight(self, *args, **kwargs):
        """Defines operations to run before the main benchmark runs.

        It is up to the caller to call preflight/teardown explicitly since
        self.run() does not call it automatically.  Maybe it should.
        """
        return

    def teardown(self, *args, **kwargs):
        """Defines operations to run after the main benchmark runs.

        It is up to the caller to call preflight/teardown explicitly since
        self.run() does not call it automatically.  Maybe it should.
        """
        return

    def run(self, access, pattern, stdout=-94720, stderr=-94720, **kwargs):
        """Runs the benchmark.

        Assembles the command line and runs the benchmark application as a
        subprocess based on the given access mode and I/O pattern.  Allows
        manual override of stdout/stderr streams if -94720 is passed.  This
        method is non-blocking.

        Args:
            access (str): Desired access mode (e.g., read or write)
            pattern (str): Desired I/O pattern (e.g., bw or iops)
            stdout (file or -94720): File where the subprocess's stdout will be
                directed.  If -94720, use self._stdout.
            stderr (file or -94720): File where the subprocess's stderr will be
                directed.  If -94720, use self._stderr.

        Returns:
            subprocess.Popen: The benchmark's process handle.
        """
        self._kwargs.update(kwargs)
        self._prep_cmdline(access, pattern)
        self._logger.info("Executing: " + " ".join(self._cmdline))
        if self._test:
            return None

        # can't reference self as default values for arguments so here we are
        pipes = {
            "stdout": self._stdout if stdout == -94720 else stdout,
            "stderr": self._stderr if stderr == -94720 else stderr,
        }

        for pipe in "stdout", "stderr":
            if not pipes[pipe]:
                self._logger.debug(f"Directing {pipe} to nowhere")
            elif isinstance(pipes[pipe], io.IOBase):
                self._logger.debug("Directing {} to {}".format(pipe, pipes[pipe].name))
            elif pipes[pipe] == subprocess.PIPE:
                self._logger.debug(f"Directing {pipe} to subprocess.PIPE")
            elif pipes[pipe] == subprocess.PIPE:
                self._logger.debug("Directing {} to {}".format(pipe, pipes[pipe]))

        # Run in background and return handle
        proc = subprocess.Popen(
            self._cmdline,
            stdout=pipes['stdout'],
            stderr=pipes['stderr'],
            text=True)
        self._cmdline = []
        return proc

class ElbenchoLauncher(BenchmarkLauncher):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._init_args("elbencho")
        idx = 0
        if "-t" in self._common_args:
            idx = self._common_args.index("-t")
        elif "--threads" in self._common_args:
            idx = self._common_args.index("--threads")

        self._common_args[idx + 1] = str(self._ppn)
        self._livecsv = False

    def _add_hosts(self):
        if self._hosts is not None:
            self._cmdline += [
                "--hosts",
                ",".join(self._hosts),
            ]

    def _add_output_dir(self):
        if self._output_dir:
            self._cmdline += self._output_dir

    def _add_results_file(self):
        stdout = self.get_stdout()
        if stdout and isinstance(stdout, io.IOBase):
            stdout = stdout.name
            if os.path.isfile(stdout):
                self._cmdline += ["--resfile", stdout + ".results"]
                self._cmdline += ["--csvfile", stdout + ".csv"]
                if self._livecsv:
                    self._cmdline += ["--livecsv", stdout + ".live.csv"]

    def set_livecsv(self, livecsv):
        self._livecsv = bool(livecsv)
        return self._livecsv

    def get_livecsv(self):
        return self._livecsv

    def preflight(self, *args, **kwargs):
        self._logger.info("Launching preflight")
        self._cmdline = [
            MPIRUN_BIN,
            "-N", str(len(self._hosts)), # Slurm-ism
            "-n", str(len(self._hosts)), # Slurm-ism
            "--nodelist",               # Slurm-ism
            ",".join(self._hosts),       # Slurm-ism
            self._binary,
            "--service",
            "--foreground"
        ]
        self._logger.info(" ".join(self._cmdline))
        if self._test:
            return None
        subprocess.Popen(self._cmdline, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self._cmdline = []
        time.sleep(5)
        return None # don't return subprocess so preflight doesn't block

    def teardown(self, access, pattern, *args, **kwargs):
        self._logger.info("Launching teardown - file cleanup")
        stdout = self.get_stdout() 
        stderr = self.get_stderr()
        self.set_stdout(None) # avoid having teardown wipe out our results files
        self.set_stderr(None)
        proc = self.run(access='clean', pattern=pattern, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs)
        self.set_stdout(stdout)
        self.set_stderr(stderr)
        # wait for clean to complete before shutting down the service
        if proc:
            proc.wait()

        self._logger.info("Launching teardown - service shutdown")
        self._cmdline = [self._binary, "--quit"]
        self._add_hosts()
        self._logger.info(" ".join(self._cmdline))
        if self._test:
            return None
        pservice = subprocess.Popen(self._cmdline, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self._cmdline = []
        time.sleep(5)
        return pservice

class IorLauncher(BenchmarkLauncher):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._init_args("ior")

        self._prepend_cmdline = [
            MPIRUN_BIN,
            "-N", str(len(self._hosts)),
            "-n", str(len(self._hosts) * self._ppn),
        ]

    def _add_hosts(self):
        if self._hosts is not None:
            if self._cmdline[0] == MPIRUN_BIN:
                self._cmdline.insert(1, "--nodelist") # Slurm-ism
                self._cmdline.insert(2, ",".join(self._hosts))
            else:
                raise ValueError(f"Can't find {MPIRUN_BIN} to insert nodelist")

    def _add_output_dir(self):
        if self._output_dir:
            # IOR doesn't support multiple output dirs, so just take the first
            self._cmdline += ["-o", self._output_dir[0]]

class MdworkbenchLauncher(BenchmarkLauncher):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._init_args("md-workbench")

        self._prepend_cmdline = [
            MPIRUN_BIN,
            "-N", str(len(self._hosts)),
            "-n", str(len(self._hosts) * self._ppn),
        ]

    def _add_hosts(self):
        if self._hosts is not None:
            if self._cmdline[0] == MPIRUN_BIN:
                self._cmdline.insert(1, "--nodelist") # Slurm-ism
                self._cmdline.insert(2, ",".join(self._hosts))
            else:
                raise ValueError(f"Can't find {MPIRUN_BIN} to insert nodelist")

    def _add_output_dir(self):
        if self._output_dir:
            self._cmdline += ["-o", self._output_dir[0]]

    def preflight(self, *args, **kwargs):
        self._logger.info("Launching preflight")
        self._cmdline = [
            MPIRUN_BIN,
            "-N", str(len(self._hosts)), # Slurm-ism
            "-n", str(len(self._hosts)), # Slurm-ism
            "--nodelist",                # Slurm-ism
            ",".join(self._hosts),       # Slurm-ism
            self._binary,
            "-1",
        ]
        self._cmdline += self._common_args
        self._logger.info(" ".join(self._cmdline))
        if self._test:
            return None
        pservice = subprocess.Popen(self._cmdline, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self._cmdline = []
        return pservice

    def teardown(self, access, pattern, *args, **kwargs):
        self._logger.info("Launching teardown - file cleanup")
        self._cmdline = [
            MPIRUN_BIN,
            "-N", str(len(self._hosts)), # Slurm-ism
            "-n", str(len(self._hosts)), # Slurm-ism
            "--nodelist",                # Slurm-ism
            ",".join(self._hosts),       # Slurm-ism
            self._binary,
            "-3",
        ]
        self._cmdline += self._common_args
        self._logger.info(" ".join(self._cmdline))
        if self._test:
            return None
        pservice = subprocess.Popen(self._cmdline, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self._cmdline = []
        time.sleep(5)
        return pservice

def get_nodes():
    if os.environ.get("SLURM_JOB_NODELIST"):
        return subprocess.check_output([
            "scontrol",
            "show",
            "hostnames",
            os.environ.get("SLURM_JOB_NODELIST")
        ], text=True).splitlines()
    return [f"cgpu{i:02d}" for i in range(8)]

def _run_and_wait_after_delay(workload, delay):
    time.sleep(delay)
    proc = workload["launcher"].run(access=workload["access"], pattern=workload["pattern"])
    time0 = time.time()
    if proc:
        proc.wait()
    timef = time.time()
    return (time0, timef)

def run_launchers(*workloads, delay=0):
    """Runs one or more benchmarks with preflight and teardown.

    Runs a complete preflights-benchmarks-teardowns cycle with one or more
    benchmarks.  Designed to allow preflights and teardowns to happen serially
    but actual benchmarks to run asynchronously to handle both contending
    benchmarks (when two or more workloads are specified) or non-contending
    benchmarks (only one workload is specified).

    Expects a list of dictionaries of the form::

        {
            "launcher": BenchmarkLauncher,
            "access": "read/write",
            "pattern": "bw/iops",
        }

    Args:
        delay (int): Seconds to wait after launching each workload before
            starting the next.
        workloads (list of dict): List of dictionaries that describe a workload
            and contain the appropriate BenchmarkLauncher.

    Returns:
        list of (float, float): Start and end time of each process.  Order
        matches that of the workloads input arg.
    """
    procs = []

    # run all preflights serially
    for workload in workloads:
        prep_p = workload["launcher"].preflight()
        if prep_p:
            prep_p.wait()

    # run all actual workloads asynchronously
    with multiprocessing.pool.ThreadPool(len(workloads)) as pool:
        results = pool.starmap(_run_and_wait_after_delay, [(workload, delay * idx) for idx, workload in enumerate(workloads)])
    time.sleep(5)

    # run all teardowns serially (could be async though)
    for workload in workloads:
        prep_p = workload["launcher"].teardown(access=workload['access'], pattern=workload['pattern'])
        if prep_p:
            prep_p.wait()

    return results

def run_symmetric_interference(*workloads):
    """Runs two benchmarks in isolation and then at the same time.

    Runs each workload independently, then runs all workloads overlapping.
    Currently supports only two workloads.

    Expects a list of dictionaries of the form::

        {
            "launcher": BenchmarkLauncher,
            "access": "read/write",
            "pattern": "bw/iops",
        }

    These input dictionaries are mutated to include more metadata from the
    environment and launchers.  This function also sets up the appropriate
    output filenames for each benchmark.

    Args:
        workloads (list of dict): List of dictionaries that describe a workload
            and contain the appropriate BenchmarkLauncher.
    """
    logger = logging.getLogger(__name__)
    OUTPUT_FILENAME = "{workload}_{contention}.{pnodes:d}p-{snodes:d}s.{jobid}.out"

    # Initialize labels
    for workload in workloads:
        workload["jobid"] = os.environ.get("SLURM_JOBID", str(int(time.time()))) # Slurm-ism
        workload["nnodes"] = len(workload["launcher"].get_hosts())

    if len(workloads) > 2:
        raise NotImplementedError("more than two workloads provided")

    # Run workload in isolation
    for workload in workloads:
        workload["pnodes"] = workloads[0]["nnodes"]
        workload["snodes"] = workloads[1]["nnodes"]
        workload["contention"] = "quiet"
        logger.info("Launching {contention} {access} {pattern} on {nnodes} {workload} nodes".format(**workload))
        workload["launcher"].set_stdout(open(OUTPUT_FILENAME.format(**workload), "a"))
        workload["launcher"].set_stderr(workload["launcher"].get_stdout())
        timestamps = run_launchers(workload)
        logger.info("Finished quiet workload; ran from {} to {} ({:.1f} seconds)".format(
            datetime.datetime.fromtimestamp(timestamps[0][0]),
            datetime.datetime.fromtimestamp(timestamps[0][1]),
            timestamps[0][1] - timestamps[0][0]))

    # Set up appropriate labels for noisy workloads
    for workload in workloads:
        workload["contention"] = "noisy"
        logger.info("Launching {contention} {access} {pattern} on {nnodes} {workload} nodes".format(**workload))
        workload["launcher"].set_stdout(open(OUTPUT_FILENAME.format(**workload), "a"))
        workload["launcher"].set_stderr(workload["launcher"].get_stdout())

    # Run noisy workloads in parallel
    timestamps = run_launchers(*workloads)
    for index, timestamp in enumerate(timestamps):
        logger.info("Finished noisy workload {}; ran from {} to {} ({:.1f} seconds)".format(
            index,
            datetime.datetime.fromtimestamp(timestamp[0]),
            datetime.datetime.fromtimestamp(timestamp[1]),
            timestamp[1] - timestamp[0]))


def run_interference(primary, secondary, delay=15, isolate='s'):
    """Runs a secondary benchmark in isolation and against a sustained primary.

    Runs the secondary workload in isolation, then runs it in the presence of a
    primary background workload to see how well this secondary workload performs
    under contention.  It is assumed that the primary is a sustained workload
    whose performance is not of interest; if it is, use
    run_symmetric_interference().

    Expects a list of dictionaries of the form::

        {
            "launcher": BenchmarkLauncher,
            "access": "read/write",
            "pattern": "bw/iops",
        }

    These input dictionaries are mutated to include more metadata from the
    environment and launchers.  This function also sets up the appropriate
    output filenames for each benchmark.

    Args:
        primary (dict): Description of the primary (sustained) workload.
        secondary (dict): Description of the secondary (probe) workload.
        delay (int): Seconds to wait after launching the primary workload before
            secondary workload is started.
        isolate (str): "primary" to run the primary in isolation, "secondary" to
            run secondary in isolation, or "both" to run both in isolation
            before running the noisy case.
    """
    logger = logging.getLogger(__name__)
    OUTPUT_FILENAME = "{workload}_{contention}.{pnodes:d}p-{snodes:d}s.{jobid}.out"

    isolate = isolate.lower()[0]
    isolated_runs = None
    if isolate == 'b':
        isolated_runs = [primary, secondary]
    elif isolate == 'p':
        isolated_runs = [primary]
    elif isolate == 's':
        isolated_runs = [secondary]
    if isolated_runs is None:
        raise ValueError("isolate must be one of: primary secondary both")

    # Initialize labels
    for workload in (primary, secondary):
        workload["jobid"] = os.environ.get("SLURM_JOBID", str(int(time.time()))) # Slurm-ism
        workload["nnodes"] = len(workload["launcher"].get_hosts())

    for workload in (primary, secondary):
        workload["pnodes"] = primary["nnodes"]
        workload["snodes"] = secondary["nnodes"]

    # Run workload(s) in isolation
    for workload in isolated_runs:
        workload["contention"] = "quiet"
        logger.info("Launching {contention} {access} {pattern} on {nnodes} {workload} nodes".format(**workload))
        workload["launcher"].set_stdout(open(OUTPUT_FILENAME.format(**workload), "a"))
        workload["launcher"].set_stderr(workload["launcher"].get_stdout())
        timestamps = run_launchers(workload)
        logger.info("Finished {} workload; ran from {} to {} ({:.1f} seconds)".format(
            workload["contention"],
            datetime.datetime.fromtimestamp(timestamps[0][0]),
            datetime.datetime.fromtimestamp(timestamps[0][1]),
            timestamps[0][1] - timestamps[0][0]))

    # Set up appropriate labels for noisy workloads
    for workload in (primary, secondary):
        workload["contention"] = "noisy"
        logger.info("Launching {contention} {access} {pattern} on {nnodes} {workload} nodes".format(**workload))
        workload["launcher"].set_stdout(open(OUTPUT_FILENAME.format(**workload), "a"))
        workload["launcher"].set_stderr(workload["launcher"].get_stdout())

    # Run noisy workloads in parallel
    timestamps = run_launchers(primary, secondary, delay=delay)
    for index, timestamp in enumerate(timestamps):
        logger.info("Finished noisy workload {}; ran from {} to {} ({:.1f} seconds)".format(
            index,
            datetime.datetime.fromtimestamp(timestamp[0]),
            datetime.datetime.fromtimestamp(timestamp[1]),
            timestamp[1] - timestamp[0]))

def main(argv=None):
    WORKLOADS = {
        "ior": IorLauncher,
        "elbencho": ElbenchoLauncher,
        "md-workbench": MdworkbenchLauncher,
    }
    parser = argparse.ArgumentParser()
    parser.add_argument("output_dir", type=str, help="Perform I/O in this directory")
    parser.add_argument("-t", "--test", action="store_true", help="Don't actually run jobs (dry run)")
    parser.add_argument("-p", "--ppn", type=int, default=None, help="Processes per node (default: detect)")
    parser.add_argument("-c", "--config", type=str, default="config.yml", help="Path to iopup config.yml")
    parser.add_argument("-s", "--step", type=int, default=1, help="Step between successive client count tests (default: 1)")
    parser.add_argument("--isolate-both", action="store_true", help="Run both primary and secondary in isolation (default: only run secondary)")
    parser.add_argument("--primary-ppn", type=int, default=None, help="Processes per node for primary workload (default: use --ppn)")
    parser.add_argument("--secondary-ppn", type=int, default=None, help="Processes per node for secondary workload (default: use --ppn)")
    parser.add_argument("--primary-timelimit", type=int, default=90,  help="Seconds to run primary workload (default: 90)")
    parser.add_argument("--secondary-timelimit", type=int, default=45,  help="Seconds to run secondary workload (default: 45)")
    parser.add_argument("--primary-workload", type=str, default="ior", help="Primary workload: (default: ior)".format(" ".join(list(WORKLOADS.keys()))))
    parser.add_argument("--secondary-workload", type=str, default="ior", help="Secondary workload: (default: ior)".format(" ".join(list(WORKLOADS.keys()))))
    parser.add_argument("--primary-access", type=str, default="write", help="Primary access mode: (default: write)")
    parser.add_argument("--secondary-access", type=str, default="write", help="Secondary access mode: (default: write)".format(" ".join(list(WORKLOADS.keys()))))
    parser.add_argument("--primary-pattern", type=str, default="bw", help="Primary I/O pattern: (default: bw)")
    parser.add_argument("--secondary-pattern", type=str, default="iops", help="Primary I/O pattern: (default: iops)")
    parser.add_argument("--delay", type=int, default=15, help="Seconds to wait after launching primary before secondary is started (default: 15)")
    args = parser.parse_args()
    global MPIRUN_BIN

    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

    config = load_config(args.config)
    MPIRUN_BIN = config.get("mpirun", None)

    node_list = get_nodes()
    num_nodes = len(node_list)
    node_step = -1 * args.step
    isolate = "both" if args.isolate_both else "secondary"

    # PPN selection
    ppn = args.ppn
    if ppn is None:
        slurm_ntasks = os.environ.get("SLURM_NTASKS")           # Slurm-ism
        slurm_nnodes = os.environ.get("SLURM_JOB_NUM_NODES")    # Slurm-ism
        if slurm_ntasks and slurm_nnodes:                       # Slurm-ism
            ppn = int(slurm_ntasks) // int(slurm_nnodes)        # Slurm-ism
    ppn_1 = ppn
    ppn_2 = ppn
    if args.primary_ppn is not None:
        ppn_1 = args.primary_ppn
    if args.secondary_ppn is not None:
        ppn_2 = args.secondary_ppn

    # Workload selection
    workload_1 = WORKLOADS[args.primary_workload]
    workload_2 = WORKLOADS[args.secondary_workload]

    for num_primary in range(num_nodes + node_step, 0, node_step):
        nodes_1 = node_list[:num_primary]
        nodes_2 = node_list[num_primary:]

        output_dir_1 = os.path.join(args.output_dir, "data-primary.{}.out".format(os.environ.get("SLURM_JOBID", os.getpid())))
        output_dir_2 = os.path.join(args.output_dir, "data-secondary.{}.out".format(os.environ.get("SLURM_JOBID", os.getpid())))

        primary = workload_1(
            output_dir=output_dir_1,
            config=config,
            hosts=nodes_1,
            ppn=ppn_1,
            timelimit=args.primary_timelimit,
            random_data=True,
            test=args.test)

        secondary = workload_2(
            output_dir=output_dir_2,
            config=config,
            hosts=nodes_2,
            ppn=ppn_2,
            timelimit=args.secondary_timelimit,
            random_data=True,
            test=args.test)

        run_interference(
            primary=dict(launcher=primary, workload="primary", access=args.primary_access, pattern=args.primary_pattern),
            secondary=dict(launcher=secondary, workload="secondary", access=args.secondary_access, pattern=args.secondary_pattern),
            isolate=isolate,
            delay=args.delay)

if __name__ == "__main__":
    main()
