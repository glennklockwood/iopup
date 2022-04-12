#!/usr/bin/env bash
#SBATCH -N 8
#SBATCH -n 128
#SBATCH -C milan
#SBATCH -q regular
#SBATCH -t 90:00

module swap PrgEnv-gnu
module load python boost

python3 ../iopup.py $SCRATCH/ost1
