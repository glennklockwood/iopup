#!/usr/bin/env bash
#SBATCH -N 16
#SBATCH -n 1024
#SBATCH -C milan
#SBATCH -q regular
#SBATCH -t 90:00

module use "/global/common/software/nersc/pm-2022.03.1/extra_modulefiles"
module load PrgEnv-gnu boost python
conda activate iopup

mkdir $SLURM_JOBID
cd $SLURM_JOBID
python3 ../../bin/iopup.py \
    --config ../config.yml \
    --isolate-both \
    --primary-ppn 16 \
    --secondary-ppn 64 \
    --step 2 \
    --primary-timelimit 60 \
    --secondary-timelimit 60 \
    --delay 0 \
    $SCRATCH/ost1
